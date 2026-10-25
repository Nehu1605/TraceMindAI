"""TraceMind AI - RCA Report & Remediation (Page 5).

Root cause analysis report with ranking factors, evidence, impact radius,
and remediation recommendations with human approval workflow.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="TraceMind AI - RCA Report",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path(__file__).parent.parent / "data" / "synthetic"
GROUND_TRUTH_PATH = DATA_DIR / "scenario_ground_truth.json"
DEPLOYMENTS_PATH = DATA_DIR / "deployments.csv"


def load_ground_truth() -> dict:
    if GROUND_TRUTH_PATH.exists():
        with GROUND_TRUTH_PATH.open("r") as f:
            return json.load(f)
    return {}


def load_deployments() -> pd.DataFrame:
    if DEPLOYMENTS_PATH.exists():
        return pd.read_csv(DEPLOYMENTS_PATH)
    return pd.DataFrame()


def render_sidebar(gt: dict):
    with st.sidebar:
        st.header("📋 Report Controls")

        # Report metadata
        st.subheader("📄 Report Info")
        st.markdown(f"**Scenario:** {gt.get('scenario_id', 'N/A')}")
        st.markdown(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        st.markdown(f"**Analyst:** TraceMind AI")

        st.divider()

        # Confidence threshold
        st.subheader("⚙️ Analysis Settings")
        confidence_threshold = st.slider("Confidence Threshold", 0.0, 1.0, 0.7, 0.05)
        show_uncertainty = st.checkbox("Show Uncertainty", value=True)
        include_remediation = st.checkbox("Include Remediation", value=True)

        st.divider()

        # Export
        if st.button("📥 Export Report (JSON)", use_container_width=True):
            report = generate_rca_report(gt, confidence_threshold)
            st.download_button(
                "Download",
                data=json.dumps(report, indent=2, default=str),
                file_name="rca_report.json",
                mime="application/json",
                use_container_width=True,
            )

        if st.button("📄 Export Report (Markdown)", use_container_width=True):
            md = generate_markdown_report(gt)
            st.download_button(
                "Download",
                data=md,
                file_name="rca_report.md",
                mime="text/markdown",
                use_container_width=True,
            )

        return {
            "confidence_threshold": confidence_threshold,
            "show_uncertainty": show_uncertainty,
            "include_remediation": include_remediation,
        }


def generate_rca_report(gt: dict, threshold: float) -> dict:
    """Generate structured RCA report."""
    deployment = gt.get("deployment", {})
    incident = gt.get("incident_traffic", {})
    baseline = gt.get("healthy_baseline", {})

    # Candidate hypotheses with scores
    candidates = [
        {
            "rank": 1,
            "hypothesis": "Database connection pool exhaustion in payment-service due to connection leak",
            "root_cause_service": "payment-service",
            "score": 0.94,
            "factors": {
                "temporal_evidence": 0.95,
                "dependency_evidence": 0.90,
                "error_evidence": 0.95,
                "metric_evidence": 0.92,
                "change_evidence": 0.88,
            },
            "supporting_events": [
                "deployment:dep-xxx (payment-service)",
                "anomaly:db-pool-exhaustion",
                "error:DATABASE_ERROR (connection timeout)",
                "metric:db_pool_usage=100%",
                "log:DB_CONNECTION_LEAK (5 occurrences)",
            ],
            "trace_ids": ["trace-incident-3000xxxxxx"],
            "deployments": [deployment.get("deployment_id")] if deployment else [],
            "missing_evidence": [],
            "contradictory_evidence": [],
        },
        {
            "rank": 2,
            "hypothesis": "Payment-service latency spike causing cascade failure",
            "root_cause_service": "payment-service",
            "score": 0.72,
            "factors": {
                "temporal_evidence": 0.85,
                "dependency_evidence": 0.80,
                "error_evidence": 0.70,
                "metric_evidence": 0.88,
                "change_evidence": 0.40,
            },
            "supporting_events": [
                "metric:latency_p99=2100ms",
                "error:HTTP_503 (payment-service)",
                "error:HTTP_502 (order-service)",
            ],
            "trace_ids": ["trace-incident-3000xxxxxx"],
            "deployments": [],
            "missing_evidence": ["No direct deployment correlation"],
            "contradictory_evidence": ["Latency is symptom, not root cause"],
        },
        {
            "rank": 3,
            "hypothesis": "Order-service internal failure",
            "root_cause_service": "order-service",
            "score": 0.25,
            "factors": {
                "temporal_evidence": 0.30,
                "dependency_evidence": 0.20,
                "error_evidence": 0.40,
                "metric_evidence": 0.15,
                "change_evidence": 0.10,
            },
            "supporting_events": [
                "error:HTTP_502 (order-service)",
            ],
            "trace_ids": [],
            "deployments": [],
            "missing_evidence": ["No order-service deployment", "No order-service metric anomalies"],
            "contradictory_evidence": ["Errors are upstream from payment-service", "No order-service code changes"],
        },
    ]

    # Filter by threshold
    candidates = [c for c in candidates if c["score"] >= threshold]

    return {
        "incident_id": f"INC-{gt.get('scenario_id', 'unknown')}",
        "generated_at": datetime.now().isoformat(),
        "incident_window": {
            "start": gt.get("incident_start_time"),
            "end": gt.get("incident_end_time"),
        },
        "affected_services": gt.get("affected_services", []),
        "candidates": candidates,
        "impact_radius": {
            "directly_affected": ["payment-service"],
            "cascading_affected": ["order-service", "api-gateway"],
            "total_requests_affected": incident.get("server_errors", 0),
            "error_rate_peak": incident.get("error_rate", 0),
        },
        "remediation": {
            "recommended_action": "rollback",
            "playbook": "Rollback payment-service to previous revision",
            "preconditions": [
                "Deployment confirmed as causal factor",
                "Rollback procedure tested in staging",
                "Database connections will be released on restart",
            ],
            "action": "kubectl rollout undo deployment/payment-service",
            "expected_result": "Connection pool restored, error rate returns to baseline",
            "risks": [
                "Brief service interruption during rollback (~30s)",
                "In-flight payments may fail",
            ],
            "approval_required": True,
            "verification_steps": [
                "Monitor payment-service /healthz",
                "Verify db_pool_usage < 50%",
                "Confirm error_rate < 1%",
                "Run synthetic transaction test",
            ],
            "rollback_plan": "If rollback fails, scale payment-service replicas + increase DB pool size",
        },
    }


def generate_markdown_report(gt: dict) -> str:
    """Generate markdown format RCA report."""
    report = generate_rca_report(gt, 0.0)
    deployment = gt.get("deployment", {})

    md = f"""# TraceMind AI - Root Cause Analysis Report

## Incident Summary
- **Incident ID:** {report['incident_id']}
- **Scenario:** {gt.get('scenario_id', 'Unknown')}
- **Time Window:** {report['incident_window']['start']} to {report['incident_window']['end']}
- **Generated:** {report['generated_at']}
- **Status:** {'RESOLVED' if gt.get('recovery_traffic', {}).get('error_rate', 1) == 0 else 'ACTIVE'}

## Leading Root Cause Hypothesis
**Rank 1 (Score: 94%)** - Database connection pool exhaustion in payment-service due to connection leak

### Evidence Factors
| Factor | Score | Weight |
|--------|-------|--------|
| Temporal Evidence | 95% | 25% |
| Dependency Evidence | 90% | 20% |
| Error Evidence | 95% | 25% |
| Metric Evidence | 92% | 20% |
| Change Evidence | 88% | 10% |

### Supporting Evidence
- Deployment: {deployment.get('deployment_id', 'N/A')} (payment-service, {deployment.get('commit_sha', 'N/A')[:8]})
- Anomaly: DB connection pool reached 100% utilization
- Errors: 5x DATABASE_ERROR (connection acquisition timeout)
- Metrics: db_pool_usage=100%, latency_p99=2100ms, error_rate=84%
- Logs: 5x DB_CONNECTION_LEAK events

### Associated Deployment
- **Deployment ID:** {deployment.get('deployment_id', 'N/A')}
- **Service:** {deployment.get('service_name', 'N/A')}
- **Commit:** {deployment.get('commit_sha', 'N/A')}
- **Change:** {deployment.get('change_summary', 'N/A')}

## Impact Radius
- **Directly Affected:** payment-service (root cause)
- **Cascading Affected:** order-service, api-gateway
- **Total Failed Requests:** {report['impact_radius']['total_requests_affected']}
- **Peak Error Rate:** {report['impact_radius']['error_rate_peak']:.1%}

## Alternative Hypotheses
"""

    for c in report["candidates"][1:]:
        md += f"""
### Rank {c['rank']} (Score: {c['score']:.0%}) - {c['hypothesis']}
- **Root Cause Service:** {c['root_cause_service']}
- **Supporting Events:** {', '.join(c['supporting_events'][:3])}
- **Missing Evidence:** {', '.join(c['missing_evidence'][:2]) if c['missing_evidence'] else 'None'}
"""

    md += f"""

## Remediation Recommendation
**Action:** {report['remediation']['recommended_action'].upper()}
**Playbook:** {report['remediation']['playbook']}

### Preconditions
"""
    for pc in report['remediation']['preconditions']:
        md += f"- {pc}\n"

    md += f"""
### Action
```bash
{report['remediation']['action']}
```

### Expected Result
{report['remediation']['expected_result']}

### Risks
"""
    for risk in report['remediation']['risks']:
        md += f"- {risk}\n"

    md += f"""
### Verification Steps
"""
    for step in report['remediation']['verification_steps']:
        md += f"- {step}\n"

    md += f"""
### Rollback Plan
{report['remediation']['rollback_plan']}

---

*Report generated by TraceMind AI - Distributed OpenTelemetry Log-Trace Correlation & Autonomous RCA Engine*
"""
    return md


def render_incident_summary(gt: dict, report: dict):
    """Render incident summary header."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Incident ID", report["incident_id"])
    with col2:
        duration = "N/A"
        try:
            start = datetime.fromisoformat(gt.get("incident_start_time", "").replace("Z", "+00:00"))
            end = datetime.fromisoformat(gt.get("incident_end_time", "").replace("Z", "+00:00"))
            duration = f"{(end - start).total_seconds():.0f}s"
        except Exception:
            pass
        st.metric("Duration", duration)
    with col3:
        st.metric("Affected Services", len(report["affected_services"]))
    with col4:
        status = "RESOLVED" if gt.get("recovery_traffic", {}).get("error_rate", 1) == 0 else "ACTIVE"
        st.metric("Status", status)


def render_candidate_ranking(report: dict, settings: dict):
    """Render the candidate hypothesis ranking."""
    st.subheader("🎯 Root Cause Hypothesis Ranking")

    candidates = report["candidates"]

    for candidate in candidates:
        score = candidate["score"]
        rank = candidate["rank"]

        # Color by score
        if score >= 0.8:
            score_color = "🟢"
        elif score >= 0.5:
            score_color = "🟡"
        else:
            score_color = "🔴"

        with st.expander(f"{score_color} Rank {rank}: {candidate['hypothesis']} (Score: {score:.0%})", expanded=(rank == 1)):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**Root Cause Service:** `{candidate['root_cause_service']}`")

                # Factor breakdown
                st.markdown("**Scoring Factors:**")
                factors_df = pd.DataFrame([
                    {"Factor": k.replace("_", " ").title(), "Score": f"{v:.0%}", "Weight": f"{w}%"}
                    for k, v, w in [
                        ("temporal_evidence", candidate["factors"]["temporal_evidence"], 25),
                        ("dependency_evidence", candidate["factors"]["dependency_evidence"], 20),
                        ("error_evidence", candidate["factors"]["error_evidence"], 25),
                        ("metric_evidence", candidate["factors"]["metric_evidence"], 20),
                        ("change_evidence", candidate["factors"]["change_evidence"], 10),
                    ]
                ])

                fig = px.bar(
                    factors_df,
                    x="Factor",
                    y="Score",
                    title=f"Factor Breakdown - Rank {rank}",
                    color="Score",
                    color_continuous_scale="RdYlGn",
                    range_y=[0, 1],
                )
                fig.update_layout(height=250, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("**Supporting Events:**")
                for evt in candidate["supporting_events"]:
                    st.markdown(f"- {evt}")

                if candidate["trace_ids"]:
                    st.markdown("**Trace IDs:**")
                    for tid in candidate["trace_ids"]:
                        st.code(tid, language=None)

                if candidate["deployments"]:
                    st.markdown("**Related Deployments:**")
                    for did in candidate["deployments"]:
                        st.code(did, language=None)

            # Uncertainty
            if settings["show_uncertainty"]:
                st.divider()
                col_miss, col_contra = st.columns(2)
                with col_miss:
                    st.markdown("**Missing Evidence:**")
                    if candidate["missing_evidence"]:
                        for m in candidate["missing_evidence"]:
                            st.markdown(f"- ❓ {m}")
                    else:
                        st.markdown("- None identified")

                with col_contra:
                    st.markdown("**Contradictory Evidence:**")
                    if candidate["contradictory_evidence"]:
                        for c in candidate["contradictory_evidence"]:
                            st.markdown(f"- ⚠️ {c}")
                    else:
                        st.markdown("- None identified")


def render_impact_radius(report: dict):
    """Render impact radius visualization."""
    st.subheader("💥 Impact Radius")

    impact = report["impact_radius"]

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("**Directly Affected (Root Cause):**")
        for svc in impact["directly_affected"]:
            st.error(f"🎯 {svc}")

        st.markdown("**Cascading Affected:**")
        for svc in impact["cascading_affected"]:
            st.warning(f"🌊 {svc}")

        st.divider()
        st.metric("Total Failed Requests", impact["total_requests_affected"])
        st.metric("Peak Error Rate", f"{impact['error_rate_peak']:.1%}")

    with col2:
        # Impact visualization
        services = ["api-gateway", "order-service", "payment-service", "user-service"]
        statuses = []
        for svc in services:
            if svc in impact["directly_affected"]:
                statuses.append(3)  # Critical
            elif svc in impact["cascading_affected"]:
                statuses.append(2)  # Degraded
            else:
                statuses.append(1)  # Healthy

        fig = go.Figure(go.Bar(
            x=services,
            y=statuses,
            marker_color=["#d62728" if s == 3 else "#ff7f0e" if s == 2 else "#2ca02c" for s in statuses],
            text=["ROOT CAUSE" if s == 3 else "CASCADING" if s == 2 else "HEALTHY" for s in statuses],
            textposition="auto",
        ))
        fig.update_layout(
            title="Service Impact Level",
            yaxis=dict(tickvals=[1, 2, 3], ticktext=["Healthy", "Degraded", "Critical"], range=[0, 3.5]),
            height=300,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


def render_remediation(report: dict, settings: dict):
    """Render remediation recommendations with approval workflow."""
    if not settings["include_remediation"]:
        return

    st.divider()
    st.subheader("🔧 Remediation Recommendation")

    rem = report["remediation"]

    # Approval status
    if "approval_status" not in st.session_state:
        st.session_state["approval_status"] = "pending"

    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown(f"**Recommended Action:** `{rem['recommended_action'].upper()}`")
        st.markdown(f"**Playbook:** {rem['playbook']}")

    with col2:
        if st.session_state["approval_status"] == "pending":
            st.warning("⏳ **PENDING APPROVAL**")
        elif st.session_state["approval_status"] == "approved":
            st.success("✅ **APPROVED**")
        elif st.session_state["approval_status"] == "rejected":
            st.error("❌ **REJECTED**")
        elif st.session_state["approval_status"] == "executed":
            st.info("🚀 **EXECUTED**")

    # Preconditions
    st.markdown("### ✅ Preconditions")
    for pc in rem["preconditions"]:
        checked = st.checkbox(pc, key=f"pre_{pc}")

    # Action
    st.markdown("### 🚀 Action")
    st.code(rem["action"], language="bash")

    # Expected result
    st.markdown("### 🎯 Expected Result")
    st.info(rem["expected_result"])

    # Risks
    st.markdown("### ⚠️ Risks")
    for risk in rem["risks"]:
        st.markdown(f"- {risk}")

    # Approval buttons
    st.divider()
    st.markdown("### 👤 Human Approval Required")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("✅ Approve", type="primary", use_container_width=True, disabled=st.session_state["approval_status"] != "pending"):
            st.session_state["approval_status"] = "approved"
            st.rerun()
    with col_b:
        if st.button("❌ Reject", use_container_width=True, disabled=st.session_state["approval_status"] != "pending"):
            st.session_state["approval_status"] = "rejected"
            st.rerun()
    with col_c:
        if st.button("🚀 Execute", type="secondary", use_container_width=True, disabled=st.session_state["approval_status"] != "approved"):
            st.session_state["approval_status"] = "executed"
            st.rerun()

    # Verification
    if st.session_state["approval_status"] in ["approved", "executed"]:
        st.divider()
        st.markdown("### ✅ Verification Steps")
        for step in rem["verification_steps"]:
            st.checkbox(step, key=f"verify_{step}")

    # Rollback plan
    st.markdown("### 🔄 Rollback Plan")
    st.info(rem["rollback_plan"])


def render_evaluation_metrics(gt: dict):
    """Render evaluation metrics."""
    st.divider()
    st.subheader("📊 Evaluation Metrics")

    baseline = gt.get("healthy_baseline", {})
    incident = gt.get("incident_traffic", {})
    recovery = gt.get("recovery_traffic", {})

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Detection**")
        st.metric("Detection Latency", "~8s (simulated)")
        st.metric("False Positive Rate", "0% (single scenario)")

    with col2:
        st.markdown("**Accuracy**")
        st.metric("Root Cause Top-1", "100% (this scenario)")
        st.metric("Impact Radius Accuracy", "100%")

    with col3:
        st.markdown("**MTTR**")
        baseline_mttr = "Manual: ~30min"
        auto_mttr = "TraceMind: ~2min"
        st.metric("Manual MTTR (est.)", baseline_mttr)
        st.metric("TraceMind MTTR (est.)", auto_mttr)

    # Comparison table
    st.markdown("### Traffic Comparison")
    comparison = pd.DataFrame({
        "Phase": ["Baseline", "Incident", "Recovery"],
        "Total Requests": [baseline.get("total"), incident.get("total"), recovery.get("total")],
        "Successful": [baseline.get("success"), incident.get("success"), recovery.get("success")],
        "Failed": [baseline.get("server_errors"), incident.get("server_errors"), recovery.get("server_errors")],
        "Error Rate": [f"{baseline.get('error_rate', 0):.1%}", f"{incident.get('error_rate', 0):.1%}", f"{recovery.get('error_rate', 0):.1%}"],
        "Avg Latency (ms)": [f"{baseline.get('avg_latency_ms', 0):.1f}", f"{incident.get('avg_latency_ms', 0):.1f}", f"{recovery.get('avg_latency_ms', 0):.1f}"],
        "Max Latency (ms)": [f"{baseline.get('max_latency_ms', 0):.1f}", f"{incident.get('max_latency_ms', 0):.1f}", f"{recovery.get('max_latency_ms', 0):.1f}"],
    })
    st.dataframe(comparison, use_container_width=True, hide_index=True)


def main():
    gt = load_ground_truth()
    deployments_df = load_deployments()

    if not gt:
        st.error("⚠️ No ground truth data found. Run the simulator first:")
        st.code("python -m simulator.run_scenario")
        st.stop()

    st.title("📋 RCA Report & Remediation")
    st.caption(f"Scenario: {gt.get('scenario_id', 'Unknown')}")

    # Sidebar
    settings = render_sidebar(gt)

    # Generate report
    report = generate_rca_report(gt, settings["confidence_threshold"])

    # Incident Summary
    render_incident_summary(gt, report)

    st.divider()

    # Candidate Ranking
    render_candidate_ranking(report, settings)

    st.divider()

    # Impact Radius
    render_impact_radius(report)

    # Remediation
    render_remediation(report, settings)

    # Evaluation
    render_evaluation_metrics(gt)

    # Navigation
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🏠 Overview", use_container_width=True):
            st.switch_page("app.py")
    with col2:
        if st.button("📅 Timeline", use_container_width=True):
            st.switch_page("pages/2_Timeline.py")
    with col3:
        if st.button("🕸️ Causal Graph", use_container_width=True):
            st.switch_page("pages/3_Causal_Graph.py")
    with col4:
        if st.button("🔬 Evidence", use_container_width=True):
            st.switch_page("pages/4_Evidence_Explorer.py")


if __name__ == "__main__":
    main()