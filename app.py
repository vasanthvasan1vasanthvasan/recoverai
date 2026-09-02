from __future__ import annotations

import hashlib
import hmac
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import settings
from db import (
    ensure_database,
    fetch_all,
    get_customer,
    get_event,
    get_pending_human_cases,
    insert_customer,
    insert_event,
    list_audit_logs,
    list_cases,
)
from generate_synthetic_data import main as generate_data
from human_review import approve_case, reject_case
from pipeline import process_all_events, process_event
from razorpay_client import RazorpayClient, RazorpayClientError
from report import compute_metrics
from webhook import handle_webhook


def format_inr(paise: int | float) -> str:
    amount_rupees = (paise or 0) / 100.0
    return f"₹{amount_rupees:,.2f}"


def render_custom_table(rows: list[dict[str, Any]], max_rows: int = 25) -> None:
    if not rows:
        st.info("No data available.")
        return
    sliced = rows[:max_rows]
    headers = list(sliced[0].keys())
    header_html = "".join(f"<th style='background:#1e293b; color:#f8fafc; padding:10px 12px; text-align:left; font-weight:600; font-size:0.85rem; border-bottom:1px solid rgba(255,255,255,0.1);'>{h}</th>" for h in headers)
    
    rows_html = ""
    for idx, row in enumerate(sliced):
        bg = "rgba(15, 23, 42, 0.6)" if idx % 2 == 0 else "rgba(30, 41, 59, 0.6)"
        cells = "".join(f"<td style='padding:8px 12px; font-size:0.82rem; color:#cbd5e1; border-bottom:1px solid rgba(255,255,255,0.05);'>{row.get(h, '')}</td>" for h in headers)
        rows_html += f"<tr style='background:{bg};'>{cells}</tr>"
        
    table_html = f"""
    <div style="overflow-x:auto; border-radius:10px; border:1px solid rgba(255,255,255,0.12); margin-bottom:15px; max-height:400px; overflow-y:auto;">
        <table style="width:100%; border-collapse:collapse; text-align:left;">
            <thead style="position:sticky; top:0; z-index:1;"><tr>{header_html}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        .main {
            background-color: #0e1117;
        }

        .stMetric {
            background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            backdrop-filter: blur(8px);
        }

        .stMetric label {
            color: #8b949e !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .stMetric [data-testid="stMetricValue"] {
            color: #58a6ff !important;
            font-size: 1.8rem !important;
            font-weight: 700 !important;
        }

        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .badge-success { background-color: rgba(46, 160, 67, 0.2); color: #3fb950; border: 1px solid rgba(46, 160, 67, 0.4); }
        .badge-warning { background-color: rgba(210, 153, 34, 0.2); color: #d29922; border: 1px solid rgba(210, 153, 34, 0.4); }
        .badge-danger { background-color: rgba(248, 81, 73, 0.2); color: #f85149; border: 1px solid rgba(248, 81, 73, 0.4); }
        .badge-info { background-color: rgba(56, 139, 253, 0.2); color: #58a6ff; border: 1px solid rgba(56, 139, 253, 0.4); }
        .badge-purple { background-color: rgba(163, 113, 247, 0.2); color: #bc8cff; border: 1px solid rgba(163, 113, 247, 0.4); }

        .timeline-step {
            border-left: 2px solid #30363d;
            padding-left: 16px;
            margin-bottom: 16px;
            position: relative;
        }
        .timeline-step::before {
            content: '';
            position: absolute;
            left: -6px;
            top: 4px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: #58a6ff;
        }

        .hero-banner {
            background: linear-gradient(90deg, #1f6feb 0%, #388bfd 50%, #8957e5 100%);
            border-radius: 12px;
            padding: 24px 32px;
            color: #ffffff;
            margin-bottom: 24px;
            box-shadow: 0 8px 24px rgba(31, 111, 235, 0.25);
        }

        div[data-testid="stSidebar"] {
            background-color: #161b22;
            border-right: 1px solid #30363d;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def format_currency(amount: int | float | None) -> str:
    if amount is None:
        val = 0.0
    else:
        try:
            val = float(amount) / 100.0
        except (ValueError, TypeError):
            val = 0.0
    return f"₹{val:,.2f}"


def render_metrics_cards(metrics: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue at Risk", format_currency(metrics["revenue_at_risk"]))
    c2.metric("Recovered Revenue", format_currency(metrics["amount_recovered"]))
    c3.metric("Recovery Rate", f"{metrics['recovery_rate']:.2f}%")
    c4.metric("Recovery Attempts", metrics["recovery_attempts"])

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Successful Recoveries", metrics["successful_recoveries"])
    c6.metric("Human Escalations", metrics["escalation_count"])
    c7.metric("Policy Blocked", metrics["blocked_action_count"])
    c8.metric("Total Risk Events", metrics["total_events"])


def render_charts(metrics: dict) -> None:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Recovery Funnel")
        funnel_data = dict(
            number=[
                metrics["total_events"],
                metrics["total_events"] - metrics["blocked_action_count"],
                metrics["recovery_attempts"],
                metrics["successful_recoveries"],
            ],
            stage=["Events Detected", "Policy Cleared", "Payment Links Sent", "Revenue Recovered"],
        )
        fig_funnel = px.funnel(funnel_data, x="number", y="stage", color_discrete_sequence=["#58a6ff"])
        fig_funnel.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig_funnel, use_container_width=True)

        st.subheader("🔍 Failure & Friction Diagnosis")
        diag_df = pd.DataFrame(
            {"Diagnosis": list(metrics["diagnosis_distribution"].keys()), "Count": list(metrics["diagnosis_distribution"].values())}
        )
        if not diag_df.empty:
            fig_pie = px.pie(
                diag_df,
                names="Diagnosis",
                values="Count",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig_pie.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        st.subheader("⚡ Action Distribution")
        act_df = pd.DataFrame(
            {"Action": list(metrics["action_distribution"].keys()), "Count": list(metrics["action_distribution"].values())}
        )
        if not act_df.empty:
            fig_bar = px.bar(
                act_df,
                x="Action",
                y="Count",
                color="Action",
                color_discrete_sequence=["#2ea043", "#d29922", "#f85149", "#a371f7"],
            )
            fig_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                showlegend=False,
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("🎯 Outcome Distribution")
        out_df = pd.DataFrame(
            {"Outcome": list(metrics["outcome_distribution"].keys()), "Count": list(metrics["outcome_distribution"].values())}
        )
        if not out_df.empty:
            fig_out = px.bar(
                out_df,
                x="Outcome",
                y="Count",
                color="Outcome",
                color_discrete_sequence=["#388bfd", "#bc8cff", "#e3b341", "#8957e5"],
            )
            fig_out.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                showlegend=False,
                margin=dict(l=20, r=20, t=30, b=20),
            )
            st.plotly_chart(fig_out, use_container_width=True)


def get_status_badge(status: str) -> str:
    status = str(status).lower()
    if status in {"paid", "simulated_success", "link_created", "simulated_link_created"}:
        return f'<span class="badge badge-success">{status}</span>'
    elif status in {"escalated", "pending_human", "scheduled", "retry_scheduled"}:
        return f'<span class="badge badge-warning">{status}</span>'
    elif status in {"blocked", "stop_no_action", "failed", "simulated_no_recovery"}:
        return f'<span class="badge badge-danger">{status}</span>'
    return f'<span class="badge badge-info">{status}</span>'


def main() -> None:
    ensure_database()
    st.set_page_config(page_title="RevGuard AI - Revenue Guardrails & Recovery Agent", page_icon="🛡️", layout="wide")
    inject_custom_css()

    st.markdown(
        """
        <div class="hero-banner">
            <h1 style="margin:0; font-size: 2.2rem; font-weight: 700;">🛡️ RevGuard AI</h1>
            <p style="margin: 4px 0 0 0; opacity: 0.9; font-size: 1.05rem;">
                Autonomous AI Revenue Protection & Recovery Agent for Razorpay Payment Failures & Checkout Abandonment
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Ensure synthetic dataset is generated and fully processed across all events
    dec_check = fetch_all("SELECT COUNT(*) as count FROM decisions WHERE action_chosen IS NOT NULL")
    evt_check = fetch_all("SELECT COUNT(*) as count FROM events WHERE source = 'synthetic'")
    total_evts = evt_check[0]["count"] if evt_check else 0
    total_decs = dec_check[0]["count"] if dec_check else 0

    if total_evts == 0:
        generate_data()
        process_all_events(channel="synthetic")
    elif total_decs < total_evts:
        process_all_events(channel="synthetic")

    with st.sidebar:
        st.subheader("⚙️ System Control")
        st.info("Environment: **Razorpay TEST Mode**")

        st.markdown("---")
        st.markdown("### 🧪 Evaluation Controls")
        if st.button("🔄 Regenerate 100 Synthetic Events", use_container_width=True):
            with st.spinner("Generating & processing benchmark dataset..."):
                generate_data()
                process_all_events(channel="synthetic")
            st.success("100 Synthetic events generated and processed!")
            st.rerun()

        if st.button("🚀 Run Synthetic Pipeline", use_container_width=True):
            with st.spinner("Processing pipeline across 100 events..."):
                process_all_events(channel="synthetic")
            st.success("Synthetic pipeline execution complete!")
            st.rerun()

        st.markdown("---")
        st.markdown("### 📊 Dataset View")
        dataset_filter = st.selectbox(
            "Select Evaluation Scope",
            ["100-Event Synthetic Benchmark", "Live Razorpay TEST Events", "All Events Combined"],
            index=0,
        )

        st.markdown("---")
        st.markdown("### 🔑 API Configuration")
        st.caption(f"Razorpay Integration: **{'Connected ✅' if settings.razorpay_enabled else 'Not Configured ⚠️'}**")
        st.caption(f"LLM API Integration: **{'Active ✅' if settings.llm_api_key else 'Heuristic Fallback ℹ️'}**")

    tabs = st.tabs(["📊 Executive Overview", "🔎 Case Explorer", "🙋 Human Review Queue", "📜 Audit Trail", "🧪 Evaluation Metrics", "⚡ Live Razorpay TEST Mode"])

    # Determine active source filter
    if dataset_filter == "100-Event Synthetic Benchmark":
        selected_source = "synthetic"
    elif dataset_filter == "Live Razorpay TEST Events":
        selected_source = "razorpay_test"
    else:
        selected_source = None

    active_metrics = compute_metrics(source=selected_source)
    synthetic_metrics = compute_metrics(source="synthetic")

    # TAB 1: EXECUTIVE OVERVIEW
    with tabs[0]:
        st.subheader(f"📈 Performance Snapshot ({dataset_filter})")
        render_metrics_cards(active_metrics)
        st.markdown("---")
        render_charts(active_metrics)

    # TAB 2: CASE EXPLORER
    with tabs[1]:
        st.subheader(f"🔎 Revenue Risk Case Explorer ({dataset_filter})")
        raw_cases = list_cases(source=selected_source)
        if not raw_cases:
            st.info("No recovery cases recorded. Click 'Run Synthetic Pipeline' in the sidebar.")
        else:
            df_cases = pd.DataFrame(raw_cases)

            # Filter controls
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            with f_col1:
                event_type_filter = st.multiselect("Event Type", options=df_cases["event_type"].unique().tolist())
            with f_col2:
                diagnosis_filter = st.multiselect("Diagnosis", options=df_cases["diagnosis"].dropna().unique().tolist())
            with f_col3:
                action_filter = st.multiselect("Action Chosen", options=df_cases["action_chosen"].dropna().unique().tolist())
            with f_col4:
                search_query = st.text_input("Search Customer / Event ID", "")

            filtered_cases = raw_cases
            if event_type_filter:
                filtered_cases = [c for c in filtered_cases if c.get("event_type") in event_type_filter]
            if diagnosis_filter:
                filtered_cases = [c for c in filtered_cases if c.get("diagnosis") in diagnosis_filter]
            if action_filter:
                filtered_cases = [c for c in filtered_cases if c.get("action_chosen") in action_filter]
            if search_query:
                q = search_query.lower()
                filtered_cases = [
                    c for c in filtered_cases
                    if q in str(c.get("event_id", "")).lower() or q in str(c.get("customer_name", "")).lower()
                ]

            st.caption(f"Showing {len(filtered_cases)} of {len(raw_cases)} cases")
            st.info("💡 **Evaluator Guide:** Select any case below to view its **Google Gemini AI Diagnosis Reasoning**, **Confidence Score**, **Policy Guardrail Rules**, and **Lifecycle Audit Timeline** instantly!")
            
            if filtered_cases:
                disp_cases = []
                for c in filtered_cases:
                    disp_cases.append(
                        {
                            "Event ID": c.get("event_id"),
                            "Customer": c.get("customer_name"),
                            "Event Type": c.get("event_type"),
                            "Amount": format_currency(c.get("amount", 0)),
                            "Diagnosis": c.get("diagnosis"),
                            "Confidence": f"{c.get('diagnosis_confidence', 0.0):.2f}" if c.get("diagnosis_confidence") else "N/A",
                            "Action": c.get("action_chosen"),
                            "Policy Allowed": "YES" if c.get("policy_allowed") else "NO",
                            "Outcome": c.get("outcome"),
                            "Recovered": format_currency(c.get("amount_recovered", 0)),
                            "Channel": c.get("channel"),
                        }
                    )
                render_custom_table(disp_cases, max_rows=20)

                st.markdown("### 🧠 AI Recovery Reasoning & Case Inspector")
                case_ids = [c["event_id"] for c in filtered_cases]
                selected_event_id = st.selectbox("🔍 Choose Case to Inspect AI Reasoning:", options=case_ids, index=0)

                if selected_event_id:
                    selected_case = next(c for c in filtered_cases if c["event_id"] == selected_event_id)
                    timeline = list_audit_logs(selected_event_id)

                    d_left, d_right = st.columns([1, 1])
                    with d_left:
                        st.markdown("#### 🧠 AI Recovery Reasoning")
                        conf_val = selected_case.get("diagnosis_confidence")
                        conf_str = f"{conf_val * 100:.0f}%" if isinstance(conf_val, (int, float)) else "N/A"
                        policy_badge = "✅ Allowed" if selected_case.get("policy_allowed") else "⛔ Blocked / Escalated"
                        
                        st.markdown(
                            f"""
                            <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px; padding: 18px; margin-bottom: 15px;">
                                <p style="margin-bottom: 8px;"><strong>👤 Customer:</strong> {selected_case.get('customer_name')} (<code>{selected_case.get('customer_id')}</code>)</p>
                                <p style="margin-bottom: 8px;"><strong>💰 Amount at Risk:</strong> {format_currency(selected_case.get('amount', 0))}</p>
                                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 10px 0;"/>
                                <p style="margin-bottom: 8px;"><strong>🔬 Diagnosis:</strong> <code>{selected_case.get('diagnosis')}</code></p>
                                <p style="margin-bottom: 8px;"><strong>🎯 Confidence:</strong> <code>{conf_str}</code></p>
                                <p style="margin-bottom: 8px;"><strong>❓ Why this diagnosis?</strong><br/><span style="color: #cbd5e1; font-size: 0.92rem;">{selected_case.get('diagnosis_reasoning')}</span></p>
                                <hr style="border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 10px 0;"/>
                                <p style="margin-bottom: 8px;"><strong>🚀 Recommended Action:</strong> <code>{selected_case.get('action_chosen')}</code> ({policy_badge})</p>
                                <p style="margin-bottom: 8px;"><strong>🛡️ Why this action? (Policy Rule):</strong><br/><span style="color: #cbd5e1; font-size: 0.92rem;">{selected_case.get('action_reasoning') or selected_case.get('policy_rule_applied')}</span></p>
                                <p style="margin-bottom: 8px;"><strong>📊 Expected / Final Outcome:</strong> <code>{selected_case.get('outcome') or 'Pending Execution'}</code></p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if selected_case.get("payment_link_url"):
                            st.info(f"🔗 **Live Razorpay Link:** [{selected_case.get('payment_link_url')}]({selected_case.get('payment_link_url')})")

                    with d_right:
                        st.markdown("#### 📜 Lifecycle Audit Timeline")
                        for item in timeline:
                            stage = item.get("stage", "")
                            action = item.get("action", "")
                            reason = item.get("reason", "")
                            ts = item.get("timestamp", "")
                            st.markdown(
                                f"""
                                <div class="timeline-step">
                                    <strong>[{stage}] {action}</strong> <span style="color:#8b949e; font-size:0.8rem;">({ts})</span><br/>
                                    <span style="font-size:0.9rem; color:#c9d1d9;">{reason}</span>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

    # TAB 3: HUMAN REVIEW QUEUE
    with tabs[2]:
        st.subheader(f"🙋 Pending Human Escalations Queue ({dataset_filter})")
        st.caption("Review cases escalated by AI confidence thresholds or policy limits. Manually approve or reject candidate recovery actions.")

        pending_cases = get_pending_human_cases(source=selected_source)

        col_hr1, col_hr2 = st.columns(2)
        with col_hr1:
            st.metric("Pending Human Escalations", len(pending_cases))
        with col_hr2:
            st.metric("Historical Total Escalated (Frozen)", active_metrics.get("human_escalations", active_metrics.get("escalation_count", 0)))

        st.markdown("---")

        if not pending_cases:
            st.success("✅ No pending human escalation cases in the queue! All escalated cases have been reviewed or none are pending.")
        else:
            for p_case in pending_cases:
                event_id = p_case["event_id"]
                amount_inr = p_case["amount"] / 100
                with st.expander(f"⚠️ Case {event_id} - {p_case['customer_name']} (₹{amount_inr:,.2f})", expanded=True):
                    h_col1, h_col2 = st.columns(2)
                    with h_col1:
                        st.markdown(f"**Customer ID:** `{p_case['customer_id']}`")
                        st.markdown(f"**Event Type:** `{p_case['event_type']}`")
                        st.markdown(f"**Amount at Risk:** ₹{amount_inr:,.2f} {p_case['currency']}")
                        st.markdown(f"**Created At:** {p_case['created_at']}")
                        st.markdown(f"**Proposed Candidate Action:** `{p_case['action_chosen']}`")
                    with h_col2:
                        st.markdown(f"**Diagnosis:** `{p_case['diagnosis']}`")
                        st.markdown(f"**Confidence:** {p_case['diagnosis_confidence'] or 0.0:.2%}")
                        st.markdown(f"**Policy Rule Applied:** `{p_case['policy_rule_applied'] or 'N/A'}`")
                        st.markdown(f"**Escalation Reason:** {p_case['action_reasoning'] or 'Policy threshold exceeded'}")

                    st.markdown("**Diagnosis Reasoning:**")
                    st.info(p_case['diagnosis_reasoning'] or "No reasoning available.")

                    review_notes = st.text_input("Reviewer Notes / Justification", key=f"notes_{event_id}", placeholder="Enter optional notes for audit log...")

                    b_col1, b_col2 = st.columns(2)
                    with b_col1:
                        if st.button(f"🟢 Approve Action ({event_id})", key=f"approve_{event_id}", use_container_width=True, type="primary"):
                            res = approve_case(event_id, reviewer="human_operator", notes=review_notes)
                            st.success(f"Approved! Candidate action '{res['candidate_action']}' executed cleanly.")
                            st.rerun()
                    with b_col2:
                        if st.button(f"🔴 Reject Action ({event_id})", key=f"reject_{event_id}", use_container_width=True):
                            res = reject_case(event_id, reviewer="human_operator", notes=review_notes)
                            st.warning(f"Rejected! Zero network calls made. Case marked as stopped.")
                            st.rerun()

    # TAB 4: AUDIT TRAIL
    with tabs[3]:
        st.subheader("📜 Complete Application Audit Logs")
        logs = list_audit_logs()
        if not logs:
            st.info("No audit logs available.")
        else:
            df_logs = pd.DataFrame(logs)
            stages = df_logs["stage"].unique().tolist()
            selected_stages = st.multiselect("Filter by Stage", options=stages, default=stages)
            filtered_logs = df_logs[df_logs["stage"].isin(selected_stages)]
            render_custom_table(filtered_logs.to_dict('records'), max_rows=25)

    # TAB 5: EVALUATION METRICS
    with tabs[4]:
        st.subheader("🧪 Synthetic Batch Evaluation Results (100 Events)")
        st.caption("Evaluation against 60 Subscription Failures & 40 Checkout Abandonment Events (Reproducible Seed)")
        render_metrics_cards(synthetic_metrics)
        st.markdown("---")
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.markdown("#### Diagnosis Distribution (Synthetic)")
            st.json(synthetic_metrics["diagnosis_distribution"])
            st.markdown("#### Outcome Breakdown")
            st.json(synthetic_metrics["outcome_distribution"])
        with col_e2:
            st.markdown("#### Policy Action Distribution")
            st.json(synthetic_metrics["action_distribution"])
            st.markdown("#### Event Type Breakdown")
            st.json(synthetic_metrics["event_type_distribution"])

    # TAB 6: LIVE RAZORPAY TEST MODE
    with tabs[5]:
        st.subheader("⚡ Live Razorpay TEST Mode Integration")
        st.caption("Create Razorpay TEST payment links and verify end-to-end webhook delivery and idempotency.")

        c_top1, c_top2 = st.columns(2)
        with c_top1:
            st.write(f"**Environment:** `TEST`")
            st.write(f"**Razorpay Key ID:** `{settings.razorpay_key_id or 'Not Configured'}`")
            st.write(f"**Webhook Secret:** `{'******' if settings.razorpay_webhook_secret else 'Not Configured'}`")
            st.write(f"**Twilio WhatsApp:** `{settings.twilio_whatsapp_number or 'Not Configured'}`")
        with c_top2:
            if settings.razorpay_enabled:
                st.success("✅ Razorpay Client Connected to TEST Mode API")
            else:
                st.warning("⚠️ Credentials not set in `.env`.")

            if settings.twilio_enabled:
                st.success("📱 Twilio WhatsApp Sandbox Connected")
            else:
                st.info("📱 Twilio Messaging: Simulated (Set `TWILIO_ACCOUNT_SID` in `.env`).")

        st.markdown("---")
        st.markdown("### ➕ Create Test Recovery Payment Link & WhatsApp Action")

        with st.form("create_payment_link_form"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                cust_name = st.text_input("Customer Name", "Vasanth Vasan")
                cust_email = st.text_input("Customer Email", "vasanth@example.com")
                cust_phone = st.text_input("Customer Phone (Sandbox Joined)", "+919087823504")
            with col_f2:
                amount_inr = st.number_input("Amount (in INR ₹)", min_value=1.0, value=999.0, step=10.0)
                event_type_input = st.selectbox("Event Type", ["subscription_payment_failed", "checkout_abandoned"])
                failure_code_input = st.selectbox("Failure Reason", ["insufficient_funds", "card_expired", "bank_decline", "mandate_revoked"])
                attempt_seq_input = st.selectbox("Recovery Channel / Attempt Sequence", [
                    "Attempt 1 → WhatsApp Message",
                    "Attempt 2 → SMS Message",
                    "Attempt 3 → Twilio Voice Call"
                ])

            submitted = st.form_submit_button("🚀 Execute Autonomous Recovery Flow", use_container_width=True)

        if submitted:
            amount_paise = int(amount_inr * 100)
            import uuid
            test_evt_id = f"TEST_EVT_{uuid.uuid4().hex[:6]}"
            test_cus_id = f"TEST_CUS_{uuid.uuid4().hex[:6]}"

            attempt_num = 1
            if "Attempt 2" in attempt_seq_input:
                attempt_num = 2
            elif "Attempt 3" in attempt_seq_input:
                attempt_num = 3

            insert_customer({
                "customer_id": test_cus_id,
                "name": cust_name,
                "email": cust_email,
                "phone": cust_phone,
                "language_pref": "en",
                "opted_out": False,
                "total_attempts": attempt_num - 1,
            })
            insert_event({
                "event_id": test_evt_id,
                "event_type": event_type_input,
                "customer_id": test_cus_id,
                "customer_name": cust_name,
                "amount": amount_paise,
                "currency": "INR",
                "attempt_number": attempt_num,
                "failure_code": failure_code_input,
                "source": "razorpay_test" if settings.razorpay_enabled else "synthetic",
            })

            with st.spinner("Processing event through RevGuard AI pipeline..."):
                target_channel = "razorpay_test" if settings.razorpay_enabled else "synthetic"
                res = process_event(test_evt_id, channel=target_channel)

            st.success(f"Pipeline executed for Case `{test_evt_id}`!")
            st.json({
                "diagnosis": res["diagnosis"],
                "policy_decision": res["policy"],
                "action_result": res["action"],
            })

        st.markdown("---")
        st.markdown("### 🔔 Test Webhook Handler (`payment_link.paid`) & Idempotency")
        st.caption("Simulate an incoming Razorpay webhook event to test signature verification & strict idempotency. (Live delivery is verified via a Serveo/SSH public tunnel — see README for architecture).")

        wh_col1, wh_col2 = st.columns(2)
        with wh_col1:
            ref_id_test = st.text_input("Payment Link Reference ID", "RECOVERAI_SUB_0001")
            plink_id_test = st.text_input("Payment Link Entity ID", "plink_test_12345")
            amount_test = st.number_input("Paid Amount (Paise)", value=99900)
        with wh_col2:
            st.write("**Webhook Actions**")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("📩 Dispatch Webhook", use_container_width=True):
                    test_payload = {
                        "event": "payment_link.paid",
                        "payload": {
                            "payment_link": {
                                "entity": {
                                    "id": plink_id_test,
                                    "reference_id": ref_id_test,
                                    "amount": amount_test,
                                }
                            }
                        },
                    }
                    raw_body = json.dumps(test_payload)
                    secret = settings.razorpay_webhook_secret or "test_webhook_secret"
                    sig = hmac.new(secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
                    client_to_use = RazorpayClient() if settings.razorpay_enabled else UIWebhookClient()
                    body, status = handle_webhook(raw_body, sig, client=client_to_use)
                    if status == 200:
                        st.success(f"Webhook Response: {body}")
                    else:
                        st.error(f"Webhook Failed: {body}")

            with b2:
                if st.button("🔄 Resend Duplicate", use_container_width=True):
                    test_payload = {
                        "event": "payment_link.paid",
                        "payload": {
                            "payment_link": {
                                "entity": {
                                    "id": plink_id_test,
                                    "reference_id": ref_id_test,
                                    "amount": amount_test,
                                }
                            }
                        },
                    }
                    raw_body = json.dumps(test_payload)
                    secret = settings.razorpay_webhook_secret or "test_webhook_secret"
                    sig = hmac.new(secret.encode("utf-8"), raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
                    client_to_use = RazorpayClient() if settings.razorpay_enabled else UIWebhookClient()
                    body, status = handle_webhook(raw_body, sig, client=client_to_use)
                    if body.get("status") == "duplicate":
                        st.warning(f"Idempotency Verified! Duplicate webhook safely ignored: {body}")
                    else:
                        st.info(f"Response: {body}")

        st.markdown("---")
        st.markdown("### 📜 Recorded Razorpay TEST Actions")
        live_actions = fetch_all(
            """
            SELECT razorpay_payment_link_id, razorpay_reference, amount, payment_link_url, status, created_at
            FROM recovery_actions
            WHERE channel = 'razorpay_test' OR status = 'link_created'
            ORDER BY created_at DESC
            """
        )
        if live_actions:
            formatted_actions = []
            for row in live_actions:
                d = dict(row)
                d["amount"] = format_inr(d.get("amount") or 0)
                formatted_actions.append(d)
            render_custom_table(formatted_actions, max_rows=25)
        else:
            st.info("No Razorpay TEST mode actions recorded yet.")


if __name__ == "__main__":
    main()
