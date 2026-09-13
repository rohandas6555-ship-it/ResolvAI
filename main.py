import os
import json
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from .env
load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")

gemini_client = genai.Client(api_key=LLM_API_KEY) if LLM_API_KEY else None

app = FastAPI(title="Autonomous Customer Resolution Agent")

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# ================= MOCK ENTERPRISE DATABASE =================
DATABASE = {
    "customers": {
        "CUST-001": {"name": "Aman Sharma", "tier": "Gold", "email": "aman@example.com"}
    },
    "orders": {
        "ORD-9901": {
            "customer_id": "CUST-001",
            "item_id": "ITEM-LAPTOP-BAG",
            "item_name": "Premium Laptop Bag",
            "price": 2499,
            "status": "DELIVERED",
            "delivery_date": "2025-05-10"
        }
    },
    "inventory": {
        "ITEM-LAPTOP-BAG": {"stock": 0}  # SIMULATING OUT OF STOCK TO FORCE REPLANNING!
    },
    "policies": {
        "replacement": "Allowed within 7 days of delivery if damaged and item is in stock.",
        "refund": "If item is damaged and out of stock, full refund is permitted up to Rs 10,000.",
        "escalation": "Escalate to human if refund > Rs 10,000 or customer threatens legal action."
    }
}

# ================= TOOL EXECUTION ENGINE =================
def get_order_details(order_id: str):
    """Retrieve details of an order."""
    return DATABASE["orders"].get(order_id, {"error": "Order not found"})

def check_inventory(item_id: str):
    """Check remaining stock for an item."""
    item = DATABASE["inventory"].get(item_id)
    if item:
        return {"item_id": item_id, "stock": item["stock"]}
    return {"error": "Item not found"}

def query_policy(query: str):
    """Check enterprise policies for returns, refunds, replacements."""
    return DATABASE["policies"]

def execute_replacement(order_id: str):
    """Attempt replacement. Will fail if stock is 0."""
    order = DATABASE["orders"].get(order_id)
    if not order:
        return {"status": "FAILED", "reason": "Invalid order"}
    
    item_id = order["item_id"]
    if DATABASE["inventory"].get(item_id, {}).get("stock", 0) <= 0:
        return {"status": "BLOCKED", "reason": "Item out of stock. Cannot replace."}
    
    # State change
    order["status"] = "REPLACEMENT_DISPATCHED"
    DATABASE["inventory"][item_id]["stock"] -= 1
    return {"status": "SUCCESS", "new_status": "REPLACEMENT_DISPATCHED"}

def execute_refund(order_id: str, amount: int):
    """Execute refund state change."""
    order = DATABASE["orders"].get(order_id)
    if not order:
        return {"status": "FAILED", "reason": "Invalid order"}
    
    # State change
    order["status"] = "REFUND_PROCESSED"
    return {"status": "SUCCESS", "refunded_amount": amount, "new_status": "REFUND_PROCESSED"}

def verify_order_state(order_id: str):
    """Verify the real-time database state after state change."""
    return {"verified_state": DATABASE["orders"].get(order_id)}

def escalate_to_human(order_id: str, reason: str):
    """Escalate to human agent."""
    return {"status": "ESCALATED", "ticket_id": "TICK-HUMAN-99", "reason": reason}

TOOL_MAPPING = {
    "get_order_details": get_order_details,
    "check_inventory": check_inventory,
    "query_policy": query_policy,
    "execute_replacement": execute_replacement,
    "execute_refund": execute_refund,
    "verify_order_state": verify_order_state,
    "escalate_to_human": escalate_to_human
}

# Gemini function-declaration schema for each tool (used for real LLM-driven tool calling)
GEMINI_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_order_details",
        description="Retrieve details of an order by order ID.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"order_id": types.Schema(type="STRING")},
            required=["order_id"]
        )
    ),
    types.FunctionDeclaration(
        name="check_inventory",
        description="Check remaining stock for an item by item ID.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"item_id": types.Schema(type="STRING")},
            required=["item_id"]
        )
    ),
    types.FunctionDeclaration(
        name="query_policy",
        description="Look up enterprise return, refund, and escalation policies.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"query": types.Schema(type="STRING")},
            required=["query"]
        )
    ),
    types.FunctionDeclaration(
        name="execute_replacement",
        description="Attempt to dispatch a replacement item for an order. Fails if out of stock.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"order_id": types.Schema(type="STRING")},
            required=["order_id"]
        )
    ),
    types.FunctionDeclaration(
        name="execute_refund",
        description="Process a full refund for an order.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "order_id": types.Schema(type="STRING"),
                "amount": types.Schema(type="INTEGER")
            },
            required=["order_id", "amount"]
        )
    ),
    types.FunctionDeclaration(
        name="verify_order_state",
        description="Read back the current database state of an order to confirm a mutation succeeded.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"order_id": types.Schema(type="STRING")},
            required=["order_id"]
        )
    ),
    types.FunctionDeclaration(
        name="escalate_to_human",
        description="Escalate the case to a human agent when no automated resolution is possible.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "order_id": types.Schema(type="STRING"),
                "reason": types.Schema(type="STRING")
            },
            required=["order_id", "reason"]
        )
    )
])

SYSTEM_INSTRUCTION_TEMPLATE = """You are an Autonomous Enterprise Customer Resolution Agent.
Your goal is to RESOLVE customer issues by modifying system states, not merely chatting.
Workflow:
1. Inspect order and policy data using tools.
2. Try to fulfill user intent (e.g. replace if damaged).
3. If an action is BLOCKED (e.g. out of stock), REPLAN immediately using policy (e.g., fallback to refund).
4. Execute state-changing action.
5. CRITICAL: Always VERIFY the database state after calling an action.
6. Escalate ONLY if unresolvable, or if a refund would exceed policy limits.
Current customer order under review: {order_id}
Respond to the customer in a warm, concise closing message once resolution is complete.
"""

# ================= AGENT ORCHESTRATOR =================
class ChatRequest(BaseModel):
    message: str
    order_id: str = "ORD-9901"
    model_provider: str = "gemini"

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.post("/api/toggle-stock")
def toggle_stock(request: Request):
    """Toggle stock to demo Replanning live"""
    current = DATABASE["inventory"]["ITEM-LAPTOP-BAG"]["stock"]
    DATABASE["inventory"]["ITEM-LAPTOP-BAG"]["stock"] = 5 if current == 0 else 0
    return {"new_stock": DATABASE["inventory"]["ITEM-LAPTOP-BAG"]["stock"]}

def run_deterministic_fallback(order_id: str, execution_logs: List[Dict[str, Any]]):
    """Deterministic simulation used when the live Gemini call is unavailable or fails.
    Guarantees the demo always resolves correctly even without API access."""
    execution_logs.append({"step": "Plan", "detail": f"Retrieving order {order_id} and checking policies."})
    order_data = get_order_details(order_id)
    execution_logs.append({"step": "Tool Call", "tool": "get_order_details", "output": order_data})

    policy_data = query_policy("refund and replacement rules")
    execution_logs.append({"step": "Tool Call", "tool": "query_policy", "output": policy_data})

    execution_logs.append({"step": "Plan", "detail": "User reported damaged item. Attempting replacement check."})
    stock_data = check_inventory(order_data["item_id"])
    execution_logs.append({"step": "Tool Call", "tool": "check_inventory", "output": stock_data})

    if stock_data.get("stock", 0) <= 0:
        execution_logs.append({"step": "Replanning Triggered ⚠️", "detail": "Item is OUT OF STOCK. Replacement impossible. Replanning to: Full Refund via Policy."})
        action_res = execute_refund(order_id, order_data["price"])
        execution_logs.append({"step": "Action Execution", "tool": "execute_refund", "output": action_res})
        v_res = verify_order_state(order_id)
        execution_logs.append({"step": "State Verification ✅", "tool": "verify_order_state", "output": v_res})
        reply = f"Hello {DATABASE['customers']['CUST-001']['name']}, I noticed your item was damaged. Since it is currently out of stock, I have autonomously processed a full refund of ₹{order_data['price']} to your original payment method. Order status verified: REFUND_PROCESSED."
    else:
        action_res = execute_replacement(order_id)
        execution_logs.append({"step": "Action Execution", "tool": "execute_replacement", "output": action_res})
        v_res = verify_order_state(order_id)
        execution_logs.append({"step": "State Verification ✅", "tool": "verify_order_state", "output": v_res})
        reply = f"Hello {DATABASE['customers']['CUST-001']['name']}, I have verified your damaged item request. A replacement has been successfully booked and dispatched! Order status verified: REPLACEMENT_DISPATCHED."

    return reply


def run_gemini_agent(message: str, order_id: str, execution_logs: List[Dict[str, Any]]):
    """Real autonomous loop: Gemini 3.8 Flash decides which tools to call, sees the
    results, and replans on its own when a tool reports a blocked/failed action."""
    chat = gemini_client.chats.create(
        model=LLM_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION_TEMPLATE.format(order_id=order_id),
            tools=[GEMINI_TOOLS]
        )
    )
    execution_logs.append({"step": "Plan", "detail": "Handing off to Gemini 3.8 Flash for autonomous tool orchestration."})

    response = chat.send_message(message)
    final_reply = None
    max_turns = 8  # bounded loop to prevent infinite replanning

    for _ in range(max_turns):
        function_calls = response.function_calls

        if not function_calls:
            # Model produced a plain text reply -> resolution is complete
            final_reply = response.text
            break

        tool_responses = []
        for fc in function_calls:
            tool_name = fc.name
            tool_args = dict(fc.args) if fc.args else {}
            tool_fn = TOOL_MAPPING.get(tool_name)

            if not tool_fn:
                result = {"error": f"Unknown tool '{tool_name}'"}
            else:
                result = tool_fn(**tool_args)

            step_label = "Tool Call"
            if tool_name in ("execute_refund", "execute_replacement"):
                step_label = "Action Execution"
            elif tool_name == "verify_order_state":
                step_label = "State Verification ✅"
            elif isinstance(result, dict) and result.get("status") == "BLOCKED":
                step_label = "Replanning Triggered ⚠️"

            execution_logs.append({"step": step_label, "tool": tool_name, "output": result})
            tool_responses.append(
                types.Part.from_function_response(name=tool_name, response=result)
            )

        response = chat.send_message(tool_responses)

    if final_reply is None:
        # Hit the turn cap without a final text answer — treat as unresolved
        final_reply = "I was unable to fully resolve this automatically and have escalated it to a human agent."
        execution_logs.append({"step": "Replanning Triggered ⚠️", "detail": "Max reasoning turns reached without resolution."})
        result = escalate_to_human(order_id, "Exceeded autonomous resolution turn limit")
        execution_logs.append({"step": "Escalation", "tool": "escalate_to_human", "output": result})

    return final_reply


@app.post("/api/agent-resolve")
async def agent_resolve(req: ChatRequest):
    execution_logs = []

    if LLM_API_KEY:
        try:
            reply = run_gemini_agent(req.message, req.order_id, execution_logs)
            execution_logs.append({"step": "Complete", "detail": "Resolved via live Gemini 3.8 Flash tool-calling."})
        except Exception as e:
            execution_logs.append({"step": "Fallback Triggered ⚠️", "detail": f"Live Gemini call failed ({e}); switching to deterministic resolution."})
            reply = run_deterministic_fallback(req.order_id, execution_logs)
    else:
        execution_logs.append({"step": "Plan", "detail": "No LLM_API_KEY configured — running deterministic resolution."})
        reply = run_deterministic_fallback(req.order_id, execution_logs)

    return {
        "reply": reply,
        "logs": execution_logs,
        "final_order_state": DATABASE["orders"][req.order_id]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)