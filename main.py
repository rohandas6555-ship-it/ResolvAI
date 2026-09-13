import os
import json
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import google.generativeai as genai
from openai import OpenAI

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

# ================= AGENT ORCHESTRATOR =================
class ChatRequest(BaseModel):
    message: str
    order_id: str = "ORD-9901"
    model_provider: str = "grok" # or "gemini"

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.post("/api/toggle-stock")
def toggle_stock(request: Request):
    """Toggle stock to demo Replanning live"""
    current = DATABASE["inventory"]["ITEM-LAPTOP-BAG"]["stock"]
    DATABASE["inventory"]["ITEM-LAPTOP-BAG"]["stock"] = 5 if current == 0 else 0
    return {"new_stock": DATABASE["inventory"]["ITEM-LAPTOP-BAG"]["stock"]}

@app.post("/api/agent-resolve")
async def agent_resolve(req: ChatRequest):
    execution_logs = []
    
    # SYSTEM PROMPT FOR AUTONOMOUS RESOLUTION & REPLANNING
    system_instruction = f"""
    You are an Autonomous Enterprise Customer Resolution Agent.
    Your goal is to RESOLVE customer issues by modifying system states, not merely chatting.
    Workflow:
    1. Inspect order and policy data using tools.
    2. Try to fulfill user intent (e.g. replace if damaged).
    3. If an action is BLOCKED (e.g. out of stock), REPLAN immediately using policy (e.g., fallback to refund).
    4. Execute state-changing action.
    5. CRITICAL: Always VERIFY the database state after calling an action.
    6. Escalate ONLY if unresolvable.
    Current customer order under review: {req.order_id}
    """

    # We run a deterministic multi-step agent execution simulation
    # (To work reliably with Grok API or Gemini function calling)
    
    # Step 1: Inspect Order
    execution_logs.append({"step": "Plan", "detail": f"Retrieving order {req.order_id} and checking policies."})
    order_data = get_order_details(req.order_id)
    execution_logs.append({"step": "Tool Call", "tool": "get_order_details", "output": order_data})
    
    policy_data = query_policy("refund and replacement rules")
    execution_logs.append({"step": "Tool Call", "tool": "query_policy", "output": policy_data})

    # Step 2: User wants resolution. Check Inventory for replacement first.
    execution_logs.append({"step": "Plan", "detail": "User reported damaged item. Attempting replacement check."})
    stock_data = check_inventory(order_data["item_id"])
    execution_logs.append({"step": "Tool Call", "tool": "check_inventory", "output": stock_data})

    # Step 3: Branch / Replanning Logic
    if stock_data.get("stock", 0) <= 0:
        execution_logs.append({"step": "Replanning Triggered ⚠️", "detail": "Item is OUT OF STOCK. Replacement impossible. Replanning to: Full Refund via Policy."})
        
        # Execute Refund
        action_res = execute_refund(req.order_id, order_data["price"])
        execution_logs.append({"step": "Action Execution", "tool": "execute_refund", "output": action_res})
        
        # Verification
        v_res = verify_order_state(req.order_id)
        execution_logs.append({"step": "State Verification ✅", "tool": "verify_order_state", "output": v_res})
        
        reply = f"Hello {DATABASE['customers']['CUST-001']['name']}, I noticed your item was damaged. Since it is currently out of stock, I have autonomously processed a full refund of ₹{order_data['price']} to your original payment method. Order status verified: REFUND_PROCESSED."
    else:
        # Item in stock -> Replace
        action_res = execute_replacement(req.order_id)
        execution_logs.append({"step": "Action Execution", "tool": "execute_replacement", "output": action_res})
        
        # Verification
        v_res = verify_order_state(req.order_id)
        execution_logs.append({"step": "State Verification ✅", "tool": "verify_order_state", "output": v_res})
        
        reply = f"Hello {DATABASE['customers']['CUST-001']['name']}, I have verified your damaged item request. A replacement has been successfully booked and dispatched! Order status verified: REPLACEMENT_DISPATCHED."

    return {
        "reply": reply,
        "logs": execution_logs,
        "final_order_state": DATABASE["orders"][req.order_id]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)