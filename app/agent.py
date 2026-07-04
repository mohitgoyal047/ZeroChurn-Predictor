# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import re
import sys
import json
from pydantic import BaseModel, Field
from typing import Optional, List
from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.workflow import Workflow, START
from google.adk.tools import AgentTool
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from app.config import config

# ==========================================
# 1. Pydantic Schemas for Structured I/O
# ==========================================

class RiskAnalysisOutput(BaseModel):
    risk_level: str = Field(description="Churn risk level: Low, Medium, or High")
    analysis_reasoning: str = Field(description="Detailed reasoning for the risk classification")
    key_drivers: List[str] = Field(description="Key drivers contributing to the risk category (e.g., login drops, open support issues)")

class CampaignDesignOutput(BaseModel):
    campaign_name: str = Field(description="Recommended retention campaign name")
    outreach_email: str = Field(description="Personalized retention outreach email draft")
    incentive_offered: str = Field(description="Specific incentive or solution offered to retain the customer")

class OrchestratorOutput(BaseModel):
    risk_level: str = Field(description="Churn risk level: Low, Medium, or High")
    summary: str = Field(description="Summary of the customer's status and churn risk")
    campaign_name: Optional[str] = Field(default=None, description="Name of the retention campaign if High risk")
    email_draft: str = Field(description="The final customized email draft to send to the customer")
    needs_human_review: bool = Field(default=False, description="Set to True if risk is High, or there are critical disputes (e.g., billing, cancellation requests)")

# ==========================================
# 2. Local MCP Toolset configuration
# ==========================================

mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
        )
    )
)

# ==========================================
# 3. Specialized Sub-Agents
# ==========================================

risk_analyzer_agent = LlmAgent(
    name="risk_analyzer_agent",
    model=config.model,
    instruction="""You are a specialized Customer Risk Analyzer.
Your task is to analyze customer usage logs, login patterns, support ticket history, and customer interactions to evaluate their churn risk.
Use your tools to query the customer usage data, support tickets, and subscription details using the customer ID provided.
Categorize the risk as 'Low', 'Medium', or 'High'.
Provide a concise summary explaining your reasoning, highlighting key risk drivers (e.g., declining logins, unresolved support tickets, negative sentiment).""",
    output_schema=RiskAnalysisOutput,
    description="Analyzes customer usage and support data to determine churn risk level.",
    tools=[mcp_toolset],
)

campaign_designer_agent = LlmAgent(
    name="campaign_designer_agent",
    model=config.model,
    instruction="""You are a specialized retention campaign designer.
Your goal is to draft personalized, empathetic, and compelling outreach messages to customers flagged as High risk.
Use your tools to pull the customer's support tickets and subscription details to address their issues specifically (e.g., offer support/billing resolutions).
Design an appropriate retention campaign, select a suitable incentive (e.g., discount, free training, dedicated support), and write a polished outreach email draft.
Ensure the tone is helpful and supportive, addressing their concerns directly.""",
    output_schema=CampaignDesignOutput,
    description="Designs customized retention campaigns and emails based on risk analyses.",
    tools=[mcp_toolset],
)

# ==========================================
# 4. Main Orchestrator Agent
# ==========================================

orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model=config.model,
    instruction="""You are the ZeroChurn Orchestrator.
Your job is to manage the customer churn evaluation and campaign drafting process.
1. Use the risk_analyzer_agent tool to analyze the customer's data and get the risk level, reasoning, and key drivers. Make sure to pass the customer_id to the risk_analyzer_agent.
2. If the risk level is High:
   - Use the campaign_designer_agent tool to design a personalized campaign and draft a retention email. Make sure to pass the customer_id to it.
   - Set needs_human_review to True.
3. If the risk level is Low or Medium:
   - Draft a standard relationship check-in email yourself, asking for feedback and suggesting resources.
   - Set needs_human_review to False.
4. If the customer specifically requests account cancellation or mentions a legal or critical billing dispute in their input, set needs_human_review to True regardless of the risk level.
5. Provide a summary of the situation, the risk level, the campaign name (if any), the final email draft, and whether human review is required.""",
    tools=[AgentTool(risk_analyzer_agent), AgentTool(campaign_designer_agent)],
    output_schema=OrchestratorOutput,
    description="Orchestrates the churn analysis, delegates sub-tasks, and drafts check-in or retention responses.",
)

# ==========================================
# 5. Workflow Function Nodes
# ==========================================

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Performs safety checks, prompt injection detection, and PII scrubbing."""
    text = ""
    if node_input and node_input.parts:
        text = "".join([p.text for p in node_input.parts if p.text])
    
    # 1. PII Scrubbing (Email, Phone, Credit Cards)
    scrubbed_text = text
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b(?:\+?\d{1,3}[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b'
    cc_pattern = r'\b(?:\d[ -]*?){13,16}\b'
    
    pii_found = False
    if re.search(email_pattern, scrubbed_text):
        scrubbed_text = re.sub(email_pattern, "[EMAIL_REDACTED]", scrubbed_text)
        pii_found = True
    if re.search(phone_pattern, scrubbed_text):
        scrubbed_text = re.sub(phone_pattern, "[PHONE_REDACTED]", scrubbed_text)
        pii_found = True
    if re.search(cc_pattern, scrubbed_text):
        scrubbed_text = re.sub(cc_pattern, "[CARD_REDACTED]", scrubbed_text)
        pii_found = True
        
    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore instructions", "bypass", "system prompt", "override", 
        "ignore previous", "you are now", "developer mode", "jailbreak"
    ]
    injection_detected = any(kw in text.lower() for kw in injection_keywords)
    
    # 3. Domain-Specific Rule: Ensure customer ID queries follow correct format
    id_validation_failed = False
    all_cust_mentions = re.findall(r'cust_\S+', text)
    for mention in all_cust_mentions:
        clean_mention = mention.rstrip('.,?!;:\'"')
        if not re.match(r'^cust_[a-zA-Z0-9_-]+$', clean_mention):
            id_validation_failed = True
            break
            
    # Determine result and severity
    severity = "INFO"
    decision = "ALLOW"
    reason = "Input is clean."
    
    if injection_detected:
        severity = "CRITICAL"
        decision = "BLOCK"
        reason = "Prompt injection attempt detected."
    elif id_validation_failed:
        severity = "CRITICAL"
        decision = "BLOCK"
        reason = "Invalid customer ID format (potential injection/unauthorized probe)."
    elif pii_found:
        severity = "WARNING"
        decision = "ALLOW"
        reason = "PII scrubbed and allowed."
        
    # Audit log entry (Structured JSON)
    audit_log = {
        "event": "security_checkpoint_evaluation",
        "severity": severity,
        "decision": decision,
        "reason": reason,
        "pii_found": pii_found,
        "injection_detected": injection_detected,
        "customer_id_validation_failed": id_validation_failed
    }
    print(json.dumps(audit_log))
    
    if decision == "BLOCK":
        return Event(output=reason, route="SECURITY_EVENT")
        
    return Event(output=scrubbed_text, route="CLEANED")

def security_event(ctx: Context, node_input: str):
    """Fallback node triggered when a security violation is flagged."""
    result = {
        "risk_level": "None",
        "summary": "Blocked by Security Checkpoint",
        "campaign_name": None,
        "email_draft": "SYSTEM BLOCKED: Prompt security violation.",
        "needs_human_review": False
    }
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text="⚠️ Access Denied: Security Checkpoint flagged this input.")]))
    yield Event(output=result)

def routing_node(ctx: Context, node_input: dict) -> Event:
    """Inspects orchestrator output and routes to review if needed."""
    ctx.state["orchestrator_output"] = node_input
    
    needs_review = node_input.get("needs_human_review", False)
    if needs_review:
        return Event(output=node_input, route="REVIEW")
    return Event(output=node_input, route="AUTO_APPROVE")

async def human_review_node(ctx: Context, node_input: dict):
    """Pauses execution for a human-in-the-loop review of the email draft."""
    if not ctx.resume_inputs or "human_approval" not in ctx.resume_inputs:
        email_draft = node_input.get("email_draft", "")
        msg = f"✋ Retention email requires human approval. Draft:\n\n{email_draft}\n\nDo you approve this draft? (yes/no):"
        yield RequestInput(interrupt_id="human_approval", message=msg)
        return
    
    approval = ctx.resume_inputs["human_approval"].lower().strip()
    if approval == "yes":
        node_input["email_draft"] = f"[APPROVED] {node_input.get('email_draft', '')}"
        yield Event(output=node_input, state={"status": "approved"})
    else:
        node_input["email_draft"] = f"[REJECTED/REWORK NEEDED] Draft was rejected by human reviewer. Please review customer case manually."
        yield Event(output=node_input, state={"status": "rejected"})

def final_output_node(ctx: Context, node_input: dict):
    """Formats and emits the final result to the user interface."""
    email_draft = node_input.get("email_draft", "")
    summary = node_input.get("summary", "")
    risk_level = node_input.get("risk_level", "Unknown")
    
    result_text = f"### Churn Risk Analysis Result\n\n"
    result_text += f"**Risk Level**: {risk_level}\n"
    result_text += f"**Summary**: {summary}\n\n"
    result_text += f"**Outreach Email Draft**:\n```\n{email_draft}\n```"
    
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=result_text)]))
    yield Event(output=node_input)

# ==========================================
# 6. Workflow Definition
# ==========================================

root_agent = Workflow(
    name="ZeroChurn_workflow",
    edges=[
        ('START', security_checkpoint),
        (security_checkpoint, {
            "CLEANED": orchestrator_agent,
            "SECURITY_EVENT": security_event
        }),
        (orchestrator_agent, routing_node),
        (routing_node, {
            "REVIEW": human_review_node,
            "AUTO_APPROVE": final_output_node
        }),
        (human_review_node, final_output_node),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
