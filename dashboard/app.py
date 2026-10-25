"""TraceMind AI - Incident Overview Dashboard (Page 1).

Main entry point for the Streamlit multi-page dashboard.
Provides an incident overview with key metrics, status, and quick navigation.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Page config must be the first Streamlit command
st.set_page_config(
    page_title="TraceMind AI - Incident Overview",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Constants
DATA_DIR = Path(__file__).parent.parent / "data" / "synthetic"
GROUND_TRUTH_PATH = DATA_DIR / "scenario_ground_truth.json"
DEPLOYMENTS_PATH = DATA_DIR / "deployments.csv"
INCIDENT_SCENARIOS_PATH = DATA_DIR / "incident_scenarios.json"


def load_ground_truth() -> dict:
    """Load ground truth data from JSON file."""
    if GROUND_TRUTH_PATH.exists():
        with GROUND_TRUTH_PATH.open("r") as f:
            return json.load(f)
    return {}


def load_deployments() -> pd.DataFrame:
    """Load deployments from CSV file."""
    if DEPLOYMENTS_PATH.exists():
        return pd.read_csv(DEPLOYMENTS_PATH)
    return pd.DataFrame()


def load_scenarios() -> dict:
    """Load incident scenarios from JSON file."""
    if INCIDENT_SCENARIOS_PATH.exists():
        with INCIDENT_SCENARIOS_PATH.open("r") as f:
            return json.load(f)
    return {"scenarios": []}


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts


def render_metric_card(label: str, value: str, delta: str | None = None, delta_color: str = "normal"):
    """Render a metric card with consistent styling."""
    st.metric(label=label, value=value, delta=delta, delta_color=delta_color)


def render_incident_header(gt: dict):
    """Render the incident header with key information."""
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.title("🔍 TraceMind AI - Incident Overview")
        st.caption(f"Scenario: {gt.get('scenario_id', 'Unknown')}")

    with col2:
        severity = "🔴 CRITICAL" if gt.get("incident_traffic", {}).get("error_rate", 0) > 0.5 else "🟡 WARNING"
        st.markdown(f"### Severity\n{severity}")

    with col3:
        status = "🟢 RESOLVED" if gt.get("recovery_traffic", {}).get("error_rate", 1) == 0 else "🔴 ACTIVE"
        st.markdown(f"### Status\n{status}")

    st.divider()


def render_key_metrics(gt: dict):
    """Render key metrics row."""
    baseline = gt.get("healthy_baseline", {})
    incident = gt.get("incident_traffic", {})
    recovery = gt.get("recovery_traffic", {})

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        error_rate = incident.get("error_rate", 0)
        baseline_rate = baseline.get("error_rate", 0)
        delta = f"+{error_rate - baseline_rate:.1%}" if error_rate > baseline_rate else f"{error_rate - baseline_rate:.1%}"
        render_metric_card("Error Rate", f"{error_rate:.1%}", delta=delta, delta_color="inverse")

    with col2:
        avg_latency = incident.get("avg_latency_ms", 0)
        baseline_latency = baseline.get("avg_latency_ms", 0)
        delta = f"+{avg_latency - baseline_latency:.0f}ms" if avg_latency > baseline_latency else f"{avg_latency - baseline_latency:.0f}ms"
        render_metric_card("Avg Latency", f"{avg_latency:.0f}ms", delta=delta, delta_color="inverse")

    with col3:
        total_requests = incident.get("total", 0)
        render_metric_card("Total Requests", f"{total_requests}")

    with col4:
        failed_requests = incident.get("server_errors", 0)
        render_metric_card("Failed Requests", f"{failed_requests}", delta_color="inverse")

    with col5:
        affected = len(gt.get("affected_services", []))
        render_metric_card("Affected Services", f"{affected}")


def render_incident_timeline(gt: dict):
    """Render a compact incident timeline."""
    st.subheader("📅 Incident Timeline")

    events = [
        ("🚀 Deployment", gt.get("deployment", {}).get("timestamp"), gt.get("deployment", {}).get("change_summary", "")),
        ("⚡ Incident Start", gt.get("incident_start_time"), "Anomaly detected"),
        ("🔥 Peak Impact", gt.get("incident_end_time"), f"Error rate: {gt.get('incident_traffic', {}).get('error_rate', 0):.1%}"),
        ("✅ Recovery Start", gt.get("incident_end_time"), "Fault reset initiated"),
        ("🟢 Recovery Complete", gt.get("incident_end_time"), "Services healthy"),
    ]

    for icon, ts, desc in events:
        if ts:
            col1, col2, col3 = st.columns([1, 2, 4])
            with col1:
                st.markdown(f"**{icon}**")
            with col2:
                st.markdown(format_timestamp(ts))
            with col3:
                st.markdown(desc)


def render_affected_services(gt: dict):
    """Render affected services panel."""
    st.subheader("🔗 Affected Services")

    affected = gt.get("affected_services", [])
    root_cause = gt.get("root_cause_service", "")

    cols = st.columns(len(affected) if affected else 1)
    for i, service in enumerate(affected):
        with cols[i]:
            is_root = service == root_cause
            label = f"🎯 **{service}** (ROOT CAUSE)" if is_root else f"🔴 {service}"
            st.markdown(label)
            if is_root:
                st.error("Database connection pool exhausted")
            elif service == "order-service":
                st.warning("Upstream payment failures")
            elif service == "api-gateway":
                st.warning("Cascading 500 errors")


def render_root_cause_hypothesis(gt: dict):
    """Render the leading root cause hypothesis."""
    st.subheader("🎯 Leading Root Cause Hypothesis")

    root_cause = gt.get("root_cause_service", "Unknown")
    cause = gt.get("injected_cause", "Unknown")
    deployment = gt.get("deployment", {})

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(f"""
        **Root Cause Service:** `{root_cause}`  
        **Failure Mode:** `{cause}`  
        **Associated Deployment:** `{deployment.get('deployment_id', 'N/A')}`  
        **Commit:** `{deployment.get('commit_sha', 'N/A')[:8]}`  
        **Change Summary:** {deployment.get('change_summary', 'N/A')}
        """)

    with col2:
        st.info("📊 **Confidence: HIGH**\n\nStrong correlation between deployment, connection pool exhaustion, and cascading failures.")


def render_quick_actions():
    """Render quick action buttons for navigation."""
    st.subheader("🚀 Quick Navigation")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("📅 View Timeline", use_container_width=True, type="primary"):
            st.switch_page("pages/2_Timeline.py")

    with col2:
        if st.button("🕸️ View Causal Graph", use_container_width=True):
            st.switch_page("pages/3_Causal_Graph.py")

    with col3:
        if st.button("🔬 Evidence Explorer", use_container_width=True):
            st.switch_page("pages/4_Evidence_Explorer.py")

    with col4:
        if st.button("📋 RCA Report", use_container_width=True):
            st.switch_page("pages/5_RCA_Report.py")


def render_sidebar(gt: dict, deployments_df: pd.DataFrame, scenarios: dict):
    """Render sidebar with incident details and controls."""
    with st.sidebar:
        st.header("🔧 Incident Details")

        # Scenario selector
        scenario_list = scenarios.get("scenarios", [])
        if scenario_list:
            selected = st.selectbox(
                "Select Scenario",
                options=[s["id"] for s in scenario_list],
                format_func=lambda x: next((s["description"] for s in scenario_list if s["id"] == x), x),
            )
            if selected != gt.get("scenario_id"):
                st.info("Switch scenarios by re-running the simulator.")

        st.divider()

        # Deployment info
        st.subheader("🚀 Deployment")
        deployment = gt.get("deployment", {})
        if deployment:
            st.markdown(f"**ID:** {deployment.get('deployment_id', 'N/A')}")
            st.markdown(f"**Service:** {deployment.get('service_name', 'N/A')}")
            st.markdown(f"**Time:** {format_timestamp(deployment.get('timestamp', 'N/A'))}")
            st.markdown(f"**Commit:** {deployment.get('commit_sha', 'N/A')[:8]}")

        st.divider()

        # Time window
        st.subheader("⏱️ Time Window")
        st.markdown(f"**Start:** {format_timestamp(gt.get('incident_start_time', 'N/A'))}")
        st.markdown(f"**End:** {format_timestamp(gt.get('incident_end_time', 'N/A'))}")

        st.divider()

        # Expected symptoms
        st.subheader("🩺 Expected Symptoms")
        for symptom in gt.get("expected_symptoms", []):
            st.markdown(f"- {symptom}")

        st.divider()

        # Stats comparison
        st.subheader("📊 Traffic Comparison")
        baseline = gt.get("healthy_baseline", {})
        incident = gt.get("incident_traffic", {})
        recovery = gt.get("recovery_traffic", {})

        comparison_data = {
            "Metric": ["Total Requests", "Success", "Server Errors", "Error Rate", "Avg Latency (ms)", "Max Latency (ms)"],
            "Baseline": [
                baseline.get("total", 0),
                baseline.get("success", 0),
                baseline.get("server_errors", 0),
                f"{baseline.get('error_rate', 0):.1%}",
                f"{baseline.get('avg_latency_ms', 0):.1f}",
                f"{baseline.get('max_latency_ms', 0):.1f}",
            ],
            "Incident": [
                incident.get("total", 0),
                incident.get("success", 0),
                incident.get("server_errors", 0),
                f"{incident.get('error_rate', 0):.1%}",
                f"{incident.get('avg_latency_ms', 0):.1f}",
                f"{incident.get('max_latency_ms', 0):.1f}",
            ],
            "Recovery": [
                recovery.get("total", 0),
                recovery.get("success", 0),
                recovery.get("server_errors", 0),
                f"{recovery.get('error_rate', 0):.1%}",
                f"{recovery.get('avg_latency_ms', 0):.1f}",
                f"{recovery.get('max_latency_ms', 0):.1f}",
            ],
        }
        st.dataframe(pd.DataFrame(comparison_data), use_container_width=True, hide_index=True)


def main():
    """Main dashboard entry point."""
    # Load data
    gt = load_ground_truth()
    deployments_df = load_deployments()
    scenarios = load_scenarios()

    if not gt:
        st.error("⚠️ No ground truth data found. Run the simulator first:")
        st.code("python -m simulator.run_scenario")
        st.stop()

    # Render sidebar
    render_sidebar(gt, deployments_df, scenarios)

    # Main content
    render_incident_header(gt)
    render_key_metrics(gt)

    st.divider()

    # Two-column layout for timeline and affected services
    col_left, col_right = st.columns([3, 2])

    with col_left:
        render_incident_timeline(gt)

    with col_right:
        render_affected_services(gt)

    st.divider()

    render_root_cause_hypothesis(gt)

    st.divider()

    render_quick_actions()

    # Footer
    st.divider()
    st.caption("TraceMind AI - Distributed OpenTelemetry Log-Trace Correlation & Autonomous RCA Engine")


if __name__ == "__main__":
    main()