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

import json
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("ZeroChurnServer")

# Mock database mapping customer_id to their respective profiles
MOCK_CUSTOMERS = {
    "cust_101": {
        "usage": {
            "monthly_active_hours": 120,
            "weekly_login_count": 28,
            "feature_adoption_rate": "85%",
            "usage_trend": "increasing"
        },
        "tickets": [
            {"id": "t1", "subject": "How to export customer data as CSV?", "status": "resolved", "priority": "low", "sentiment": "neutral"}
        ],
        "subscription": {
            "tier": "Enterprise",
            "monthly_spend": 2499,
            "payment_failures_ytd": 0,
            "contract_end_date": "2027-12-31"
        }
    },
    "cust_102": {
        "usage": {
            "monthly_active_hours": 12,
            "weekly_login_count": 2,
            "feature_adoption_rate": "15%",
            "usage_trend": "critical_drop_80%"
        },
        "tickets": [
            {"id": "t2", "subject": "Billing issue - double charge on invoice #9021", "status": "open", "priority": "high", "sentiment": "angry"},
            {"id": "t3", "subject": "API endpoints returning 500 errors periodically", "status": "open", "priority": "critical", "sentiment": "frustrated"},
            {"id": "t4", "subject": "Request refund and account cancellation instructions", "status": "open", "priority": "high", "sentiment": "angry"}
        ],
        "subscription": {
            "tier": "Professional",
            "monthly_spend": 499,
            "payment_failures_ytd": 2,
            "contract_end_date": "2026-08-31"
        }
    },
    "cust_103": {
        "usage": {
            "monthly_active_hours": 45,
            "weekly_login_count": 10,
            "feature_adoption_rate": "50%",
            "usage_trend": "stable"
        },
        "tickets": [
            {"id": "t5", "subject": "Feature request: dark mode support for desktop client", "status": "open", "priority": "low", "sentiment": "neutral"},
            {"id": "t6", "subject": "Cannot upload custom profile picture avatar", "status": "resolved", "priority": "low", "sentiment": "neutral"}
        ],
        "subscription": {
            "tier": "Basic",
            "monthly_spend": 99,
            "payment_failures_ytd": 0,
            "contract_end_date": "2026-10-31"
        }
    }
}

@mcp.tool()
def get_customer_usage_data(customer_id: str) -> str:
    """Fetches customer login patterns, feature adoption, and usage trends.
    
    Args:
        customer_id: The unique ID of the customer (e.g., cust_101, cust_102, cust_103).
        
    Returns:
        JSON string containing usage metrics or an error message.
    """
    if customer_id not in MOCK_CUSTOMERS:
        return json.dumps({"error": f"Customer ID {customer_id} not found."})
    return json.dumps(MOCK_CUSTOMERS[customer_id]["usage"])

@mcp.tool()
def get_customer_support_tickets(customer_id: str) -> str:
    """Fetches the support ticket history, status, priorities, and sentiments.
    
    Args:
        customer_id: The unique ID of the customer (e.g., cust_101, cust_102, cust_103).
        
    Returns:
        JSON string containing the ticket list or an error message.
    """
    if customer_id not in MOCK_CUSTOMERS:
        return json.dumps({"error": f"Customer ID {customer_id} not found."})
    return json.dumps(MOCK_CUSTOMERS[customer_id]["tickets"])

@mcp.tool()
def get_customer_subscription_details(customer_id: str) -> str:
    """Fetches subscription tier, monthly spend, contract end date, and billing issues.
    
    Args:
        customer_id: The unique ID of the customer (e.g., cust_101, cust_102, cust_103).
        
    Returns:
        JSON string containing subscription info or an error message.
    """
    if customer_id not in MOCK_CUSTOMERS:
        return json.dumps({"error": f"Customer ID {customer_id} not found."})
    return json.dumps(MOCK_CUSTOMERS[customer_id]["subscription"])

if __name__ == "__main__":
    mcp.run(transport="stdio")
