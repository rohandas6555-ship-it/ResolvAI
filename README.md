# 🤖 Autonomous Customer Resolution Agent (ResolvAI)

> **Track 3: Smart Automation | Problem Statement 5**
> An autonomous, closed-loop customer resolution agent engineered to execute state-changing actions across enterprise systems, autonomously replan around constraints, and verify database states.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python)](https://python.org)
[![OpenAPI](https://img.shields.io/badge/API-OpenAPI%203.0-6BA539.svg?style=flat&logo=swagger)](https://swagger.io/)
[![Architecture](https://img.shields.io/badge/Agent-Closed--Loop%20ReAct-blueviolet)](#-system-architecture)

---

## 📌 Executive Summary

Traditional customer support bots are passive: they classify tickets, summarize text, or point customers to static FAQs.

**ResolvAI** is built to bridge the gap between intent recognition and actual system resolution. When a customer reports an issue, the agent autonomously accesses backend tools, evaluates enterprise policies, executes verified state mutations (such as processing refunds or ordering replacements), and handles edge-case bottlenecks using dynamic replanning.

---

## 🌟 Key Capabilities

1. **State-Changing Actions (Beyond Text Generation)**
   The agent interfaces directly with simulated enterprise backends via standardized OpenAPI endpoints to alter database records (`DELIVERED` → `REFUND_PROCESSED` or `REPLACEMENT_DISPATCHED`).

2. **Autonomous Replanning Under Constraints**
   If an intended action is blocked (e.g., a customer requests a replacement but inventory is 0), the agent does not quit or fail. It autonomously replans against enterprise policy guidelines and falls back to an eligible alternative (e.g., issuing a full refund).

3. **Closed-Loop State Verification**
   Following every transactional action, the agent executes an independent verification step, querying the persistence layer to confirm the record state was successfully mutated.

4. **Model-Agnostic LLM Tool Orchestration**
   Designed around open standard Tool Calling / Function Calling specifications. The architecture connects cleanly to any enterprise LLM / foundation model backend.

5. **Safe Escalation Guardrails**
   Policy-driven limits protect enterprise boundaries. Requests that violate safety constraints or exceed authorized thresholds (e.g., high refund limits) are routed to human queues.

---

## 🏗️ System Architecture

> This diagram reflects the intended production architecture. In the current demo build, the replanning decision inside the Agent Core is deterministic (see note in [Configuration](#-configuration)) to keep live demonstrations repeatable; the tool layer, policy engine, and verification loop shown below are fully implemented and exercised in every request.

```
[ Customer Request ]
        │
        ▼
┌───────────────────────────────────────────┐
│         Autonomous LLM Agent Core          │
│  - Intent Understanding & Goal Extraction  │
│  - Policy Reasoning & Tool Orchestration   │
└─────────────────────┬───────────────────────┘
                       │
       ┌───────────────┴────────────────┐
       ▼                                 ▼
[ Policy Engine ]              [ Simulated OpenAPI Tools ]
 - Return/Refund Rules           - Customer DB
 - Escalation Thresholds         - Order Management API
                                 - Real-Time Inventory API
                                          │
                                          ▼
                             [ Action Execution Block ]
                              - Replace / Refund / Cancel
                                          │
       ┌──────────────────────────────────┘
       ▼
[ Blocked / Constraint? ]
   ├── YES ──► [ Autonomous Replanning Loop ] ──► [ Alternative Action ]
   └── NO  ──► [ Execute Primary Action ]
                       │
                       ▼
      [ Verification Engine (Read DB State) ]
                       │
                       ▼
      [ Final State Confirmed & User Notified ]
```

---

## 💻 Tech Stack

| Layer               | Technology                                                        |
|---------------------|--------------------------------------------------------------------|
| Frontend            | Responsive dual-panel dashboard (Vanilla HTML5, CSS3, JavaScript) |
| Backend API         | FastAPI (async Python framework)                                  |
| API Standard        | OpenAPI 3.0 / Swagger interactive documentation                   |
| Agent Framework     | Closed-loop ReAct-style tool-calling & replanning orchestration   |
| LLM                 | Gemini 3.8 Flash (via `google-genai`)                       |
| Data Persistence    | In-memory enterprise state simulation with consistent, transactional state updates |

---

## 🚀 Quickstart Guide

### Prerequisites
- Python 3.9+ installed on your system.
- A Google AI Studio API key for Gemini (see [Configuration](#-configuration) below).

### 1. Clone the Repository

```bash
git clone https://github.com/rohandas6555-ship-it/ResolvAI.git
cd ResolvAI
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Minimum required packages:

```
fastapi
uvicorn
pydantic
google-genai
python-dotenv
```

> This project uses Google's **Gemini 3.8 Flash** model via the `google-genai` SDK, loaded from `.env` using `python-dotenv`.

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
LLM_PROVIDER=google
LLM_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL=gemini-3.8-flash
PORT=8000
```

> ⚠️ Never commit your real API key to the repository. Keep `.env` in `.gitignore` and only share `AIzaSy...` style placeholders in documentation.

### 4. Start the Application

```bash
python main.py
```

### 5. Access the Interfaces
- **Customer & Agent Live Dashboard:** [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

## ⚙️ Configuration

| Variable       | Description                                  | Required | Value Used in This Project |
|----------------|-----------------------------------------------|----------|------------------------------|
| `LLM_PROVIDER` | LLM backend used for agent reasoning          | Yes      | `google`                     |
| `LLM_API_KEY`  | API key for the Gemini API (used by `google-genai`) | Yes | Your own key (get one at [aistudio.google.com](https://aistudio.google.com)) |
| `LLM_MODEL`    | Model identifier used for tool-calling & replanning | Yes | `gemini-3.8-flash`           |
| `PORT`         | Port to run the FastAPI server on              | No       | `8000` (default)             |

> **Hybrid Resolution Note:** `agent_resolve()` (`main.py`) first attempts a **live Gemini 3.8 Flash tool-calling loop** — the model itself inspects the order, checks inventory, and decides whether to replace or replan to a refund, calling the real tool functions each time. If `LLM_API_KEY` is not set, or the live call errors out (timeout, quota, network), the endpoint automatically falls back to an equivalent deterministic Python resolution path, so the demo never fails on stage even without API access. Every request's logs indicate which path was used (`"Resolved via live Gemini 3.8 Flash tool-calling"` vs. the fallback trace).

---

## 🧪 Evaluation Test Scenarios

The sandbox includes interactive toggles to test resolution paths deterministically.

### Scenario A: Constraint-Driven Autonomous Replanning
1. Ensure the top status indicator shows **"Simulate Stock: Out of Stock (0)"**.
2. Submit: *"I received a damaged laptop bag. Please send me a replacement!"*

**Observed agent workflow:**
1. Calls `get_order_details` and `query_policy`.
2. Attempts `check_inventory` → receives `stock: 0`.
3. Triggers replanning: logs explain that replacement is unavailable and fall back to a policy-permitted full refund.
4. Executes `execute_refund`.
5. Calls `verify_order_state` → confirms `REFUND_PROCESSED`.
6. Live DB State Inspector updates automatically.

### Scenario B: Happy Path Resolution
1. Click **"Simulate Stock"** in the top bar to toggle inventory to 5.
2. Resubmit the replacement request.

**Observed agent workflow:**
1. Checks inventory → confirms sufficient stock.
2. Executes `execute_replacement` directly, without fallback.
3. Calls `verify_order_state` → confirms `REPLACEMENT_DISPATCHED`.

---

## 🛡️ Enterprise Readiness & Safety

- **Auditable agent logs** — every cognitive step, tool parameter, and API payload is recorded in the trace log.
- **Fail-safe escalation** — if both replacement and refund pathways fail, or policy limits are exceeded, the agent cleanly executes `escalate_to_human`.
- **Bounded replanning** — the replanning loop is capped at a fixed number of attempts to prevent infinite retry cycles; exceeding the cap triggers escalation.
- **Tool-call failure handling** — timeouts or malformed responses from a simulated backend are caught and treated as blocked actions, feeding into the same replanning/escalation path as policy blocks.
- **Threshold-based escalation** — refunds or actions above a configured value automatically route to a human queue rather than executing autonomously.