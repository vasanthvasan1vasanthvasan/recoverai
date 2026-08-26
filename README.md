# RecoverAI

**AI Revenue Recovery Agent**

---

## 📌 Problem

Modern digital merchants lose significant revenue due to payment failures and checkout friction. When a recurring subscription payment fails or a customer abandons a checkout session, merchants often lack an automated, intelligent recovery mechanism. Manual follow-ups are slow, while unguided automated retries risk spamming customers or violating financial policies.

---

## 💡 Solution

**RecoverAI** is an autonomous, policy-bounded AI revenue recovery agent built specifically for Razorpay. It detects revenue at risk, diagnoses root causes using hybrid AI and failure-code intelligence, enforces strict deterministic safety guardrails, and executes bounded recovery actions using **Real Razorpay TEST Mode Payment Links**.

The end-to-end autonomous recovery pipeline follows seven stages:
$$\text{DETECT} \longrightarrow \text{DIAGNOSE} \longrightarrow \text{DECIDE} \longrightarrow \text{POLICY} \longrightarrow \text{ACT} \longrightarrow \text{TRACK} \longrightarrow \text{REPORT}$$

---

## 🏆 Track

- **Hackathon:** Razorpay AI Buildathon 2026
- **Track:** Track 03 — AI Revenue Recovery

---

## ✨ Key Features

- **Payment Failure Recovery:** Automatic handling of recurring subscription payment failures.
- **Checkout Abandonment Recovery:** AI-driven diagnosis of multi-step checkout drop-offs.
- **Failed Subscription Recovery:** Categorized failure code mapping (`insufficient_funds`, `card_expired`, `bank_decline`, `mandate_revoked`).
- **AI Diagnosis:** Natural-language root cause analysis via **Google Gemini 2.5 Flash / OpenAI** with confidence scoring.
- **Deterministic Safety Policies:** Non-overridable Python rules enforcing customer contact limits, quiet hours, and amount caps.
- **Razorpay TEST Payment Links:** Dynamic generation of real, active Razorpay payment links (`https://rzp.io/rzp/...`).
- **Webhook Verification:** Flask webhook handler with HMAC-SHA256 signature verification.
- **Idempotency:** Automatic duplicate webhook suppression using unique `external_event_id` tracking.
- **Audit Trail:** Comprehensive SQLite audit logging tracking every stage of the lifecycle.
- **Batch Evaluation:** Reproducible benchmark evaluation across a batch of 100 synthetic events.

---

## 🎬 Demo / Verification Evidence

RecoverAI includes built-in verification tools and a dedicated Streamlit dashboard to observe recovery operations:

- **AI Recovery Reasoning Card:** Displays exact diagnosis, confidence score, cart friction analysis, chosen action, applied policy rules, and expected outcomes for every inspected case.
- **Deterministic Policy Guardrails in Action:** Demonstrates active safety suppression (e.g. `SUB_0060` blocked due to customer opt-out; `SUB_0002` escalated due to ₹25,000 amount ceiling exceeding ₹10,000 threshold).
- **Real Razorpay Payment Link Generation:** Interacts directly with Razorpay TEST sandbox APIs to generate active, clickable payment URLs (`https://rzp.io/rzp/...`).
- **Webhook Verification & Idempotency:** Includes an interactive Webhook Simulator testing HMAC-SHA256 signature verification and verifying that duplicate webhooks output `200 Duplicate webhook ignored`.
- **Chronological Audit Trail:** Forensic lifecycle logging for every event across all 7 pipeline stages.

### 📸 Dashboard & Interface Showcase

#### 1. Executive Performance Overview & Revenue Metrics
![Executive Overview](docs/images/dashboard_overview.png)

#### 2. AI Recovery Reasoning & Case Inspector
![Case Explorer & AI Reasoning](docs/images/case_explorer.png)

#### 3. Real Razorpay TEST Mode & Webhook Simulator
![Live Razorpay TEST Mode](docs/images/live_razorpay_mode.png)

---

## 📐 Architecture

```
                                  +---------------------------------------+
                                  |     100 Synthetic Benchmark Events    |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |           [1. DETECT]                 |
                                  |   Loads Event & Customer Profile      |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |           [2. DIAGNOSE]               |
                                  | Rule Engine (Failures) + Gemini AI    |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |            [3. DECIDE]                |
                                  | Formulates Candidate Recovery Strategy|
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |        [4. POLICY GUARDRAILS]         |
                                  | Quiet Hours | Opt-Out | Caps | Limits |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |             [5. ACT]                  |
                                  | Razorpay TEST Payment Links / Escalate|
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |            [6. TRACK]                 |
                                  | Webhook Listener (HMAC & Idempotency) |
                                  +---------------------------------------+
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |            [7. REPORT]                |
                                  | Streamlit Dashboard & SQLite Metrics  |
                                  +---------------------------------------+
```

### Module Overview
- `app.py`: Interactive Streamlit Dashboard (`Executive Overview`, `Case Explorer`, `Audit Trail`, `Evaluation Metrics`, `Live Razorpay TEST Mode`).
- `pipeline.py`: Orchestrates the 7-stage recovery pipeline.
- `diagnose.py`: Hybrid rule-based failure diagnosis and LLM-powered abandonment diagnosis.
- `ai_client.py`: Gemini 2.5 Flash / OpenAI API client with heuristic fallback.
- `policy.py`: Deterministic Python safety engine enforcing financial guardrails.
- `act.py`: Recovery action execution module.
- `razorpay_client.py`: Razorpay SDK wrapper (`create_payment_link`, `verify_webhook_signature`).
- `webhook.py`: Flask webhook listener with HMAC signature verification.
- `db.py`: SQLite persistence helper layer.
- `report.py`: Aggregated metrics and metric calculations.

---

## 🧠 AI Usage

### What AI Does
- Diagnoses ambiguous checkout abandonment events using cart state, duration, and checkout step.
- Assigns a diagnosis confidence score (0.00 – 1.00).
- Generates natural-language reasoning explaining customer cart friction.
- Provides context-aware customer communication text based on language preferences (`en`, `hi`).

### What AI Does NOT Do
- Does **NOT** make final policy or financial decisions.
- Does **NOT** execute payment links autonomously without policy validation.
- Does **NOT** perform financial or revenue metric calculations.
- Does **NOT** override customer opt-out settings, quiet hours, or maximum attempt caps.
- Does **NOT** validate webhook signatures or handle security verification.

---

## 🛡️ Safety Guardrails

Hardcoded, deterministic Python rules strictly enforce safety boundaries before any recovery action is taken:

- **Maximum Attempts:** Maximum 3 recovery attempts per customer; escalates to human if exceeded.
- **₹10,000 Autonomous Limit:** Transactions exceeding ₹10,000 (1,000,000 paise) automatically escalate to human intervention.
- **Quiet Hours:** Customer contact is suppressed between 21:00 and 09:00 IST to prevent late-night disturbances.
- **Opt-Out Protection:** Immediately stops all recovery actions for customers who opted out (`opted_out = True`).
- **Confidence Threshold:** Diagnoses with AI confidence below 0.60 or `unknown` trigger human escalation.
- **Human Escalation:** Flagged cases are placed into a human review queue with full diagnostic context.

---

## 📊 Evaluation

RecoverAI evaluated its pipeline against a reproducible benchmark dataset:

- **Benchmark Dataset:** 100 events (60 subscription failures + 40 checkout abandonments) across 24 customer profiles.
- **Overall Revenue at Risk:** `₹452,810.00` (Total payable value of all detected at-risk events).
- **Targeted Recovery Value (Attempted):** `₹28,493.00` (Total value associated with permitted recovery-attempt actions).
- **Confirmed Recovered Revenue:** `₹2,697.00` (Confirmed paid recoveries recorded via webhook / simulation).
- **Overall Recovery Rate:** `0.60%` (Confirmed recovered revenue relative to total revenue at risk).
- **Policy Enforcement Outcomes:** 32 human escalations and 15 policy-blocked events correctly identified.

---

## ⚡ Razorpay TEST Integration

RecoverAI integrates with Razorpay via the official Python SDK (`razorpay` package):

1. **Payment Link Generation (`create_payment_link`):** Generates active payment URLs (`https://rzp.io/rzp/...`) configured with customer contact details, amount in paise, reference ID, and description.
2. **Signature Verification (`verify_webhook_signature`):** Uses HMAC-SHA256 signature verification to validate incoming webhook events against `RAZORPAY_WEBHOOK_SECRET`.
3. **Idempotency Control:** Logs external event IDs to prevent duplicate webhook processing and double-counting of recovered revenue.

---

## ⚙️ Installation

```bash
# 1. Clone the repository
git clone https://github.com/vasanthvasan1vasanthvasan/recoverai.git
cd recoverai

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate  # On Windows

# 3. Install required dependencies
pip install -r requirements.txt
```

---

## 🔑 Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```ini
# Razorpay TEST Credentials
RAZORPAY_KEY_ID=your_razorpay_key_id_here
RAZORPAY_KEY_SECRET=your_razorpay_key_secret_here
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here

# LLM API key
LLM_API_KEY=your_llm_api_key_here

# Database File Path
DATABASE_PATH=data/recoverai.db
```

---

## 🚀 Running the Application

### 1. Generate Benchmark Dataset
```bash
python generate_synthetic_data.py
```

### 2. Run Synthetic Batch Evaluation
```bash
python run_evaluation.py
```

### 3. Launch the Streamlit Dashboard
```bash
python -m streamlit run app.py
```
*Open `http://localhost:8501` in your browser.*

### 4. Run Webhook Service (Optional)
```bash
python webhook.py
```

---

## 🧪 Running Tests

Run the complete test suite using pytest:

```bash
python -m pytest
```

*All 14 unit and integration tests pass cleanly.*

---

## ⚠️ Known Limitations

- **TEST Mode Sandbox:** Real integration requires active Razorpay TEST Mode credentials in `.env`.
- **Heuristic Fallback:** If `LLM_API_KEY` is not provided, ambiguous checkout abandonments fall back to deterministic heuristic diagnosis without failing.
- **Idempotent Webhooks:** Duplicate webhooks with existing `external_event_id` are safely ignored.
