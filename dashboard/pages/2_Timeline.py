"""TraceMind AI - Incident Timeline (Page 2).

Detailed timeline view showing deployments, anomalies, errors, and recovery events.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="TraceMind AI - Timeline",
    page_icon="📅",
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


def parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.now()


def format_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except Exception:
        return ts


def render_sidebar(gt: dict):
    with st.sidebar:
        st.header("📅 Timeline Controls")

        # Time range selector
        start_str = gt.get("incident_start_time", "")
        end_str = gt.get("incident_end_time", "")
        if start_str and end_str:
            start_dt = parse_ts(start_str)
            end_dt = parse_ts(end_str)
            st.markdown(f"**Incident Window**")
            st.markdown(f"{format_ts(start_str)} → {format_ts(end_str)}")
            st.markdown(f"Duration: {(end_dt - start_dt).total_seconds():.0f}s")

        st.divider()

        # Event filters
        st.subheader("🔍 Event Filters")
        show_deployments = st.checkbox("Deployments", value=True)
        show_anomalies = st.checkbox("Metric Anomalies", value=True)
        show_errors = st.checkbox("Error Events", value=True)
        show_recovery = st.checkbox("Recovery Events", value=True)

        st.divider()

        # Export
        if st.button("📥 Export Timeline JSON", use_container_width=True):
            timeline_data = build_timeline_events(gt)
            st.download_button(
                "Download",
                data=json.dumps(timeline_data, indent=2),
                file_name="incident_timeline.json",
                mime="application/json",
                use_container_width=True,
            )

        return {
            "show_deployments": show_deployments,
            "show_anomalies": show_anomalies,
            "show_errors": show_errors,
            "show_recovery": show_recovery,
        }


def build_timeline_events(gt: dict) -> list[dict]:
    """Build a comprehensive timeline of events from ground truth."""
    events = []
    base_time = parse_ts(gt.get("incident_start_time", datetime.now().isoformat()))

    # Deployment event
    deployment = gt.get("deployment", {})
    if deployment:
        dep_time = parse_ts(deployment.get("timestamp", ""))
        events.append({
            "time": dep_time,
            "time_str": format_ts(deployment.get("timestamp", "")),
            "type": "deployment",
            "icon": "🚀",
            "title": f"Deployment: {deployment.get('service_name', 'Unknown')}",
            "description": deployment.get("change_summary", ""),
            "details": {
                "Deployment ID": deployment.get("deployment_id", "N/A"),
                "Commit": deployment.get("commit_sha", "N/A")[:8],
                "Status": deployment.get("status", "N/A"),
                "Changed Files": deployment.get("changed_files", "N/A"),
            },
            "severity": "info",
        })

    # Incident start
    inc_start = parse_ts(gt.get("incident_start_time", ""))
    events.append({
        "time": inc_start,
        "time_str": format_ts(gt.get("incident_start_time", "")),
        "type": "anomaly",
        "icon": "⚡",
        "title": "Anomaly Detected",
        "description": "Database connection utilization spike detected",
        "details": {
            "Trigger": "Connection pool > 80% utilization",
            "Service": "payment-service",
        },
        "severity": "warning",
    })

    # Metric anomalies (simulated based on incident data)
    incident_traffic = gt.get("incident_traffic", {})
    if incident_traffic:
        # Latency spike
        events.append({
            "time": inc_start + timedelta(seconds=5),
            "time_str": format_ts((inc_start + timedelta(seconds=5)).isoformat()),
            "type": "anomaly",
            "icon": "📈",
            "title": "Latency Spike",
            "description": f"Payment latency increased to {incident_traffic.get('avg_latency_ms', 0):.0f}ms avg",
            "details": {
                "Metric": "http_request_duration_ms",
                "Service": "payment-service",
                "Value": f"{incident_traffic.get('avg_latency_ms', 0):.0f}ms",
                "Baseline": f"{gt.get('healthy_baseline', {}).get('avg_latency_ms', 0):.1f}ms",
            },
            "severity": "warning",
        })

        # Error rate spike
        events.append({
            "time": inc_start + timedelta(seconds=8),
            "time_str": format_ts((inc_start + timedelta(seconds=8)).isoformat()),
            "type": "error",
            "icon": "🔴",
            "title": "Error Rate Spike",
            "description": f"HTTP 5xx rate reached {incident_traffic.get('error_rate', 0):.1%}",
            "details": {
                "Metric": "http_5xx_rate",
                "Service": "api-gateway",
                "Value": f"{incident_traffic.get('error_rate', 0):.1%}",
                "Baseline": f"{gt.get('healthy_baseline', {}).get('error_rate', 0):.1%}",
            },
            "severity": "critical",
        })

        # Connection pool exhaustion
        events.append({
            "time": inc_start + timedelta(seconds=10),
            "time_str": format_ts((inc_start + timedelta(seconds=10)).isoformat()),
            "type": "error",
            "icon": "💥",
            "title": "Connection Pool Exhausted",
            "description": "Payment-service DB connection pool fully exhausted",
            "details": {
                "Service": "payment-service",
                "Pool Size": "5",
                "Leaked Connections": "5",
                "Error": "Database connection acquisition timeout",
            },
            "severity": "critical",
        })

        # Cascading failures
        for svc in ["order-service", "api-gateway"]:
            events.append({
                "time": inc_start + timedelta(seconds=12),
                "time_str": format_ts((inc_start + timedelta(seconds=12)).isoformat()),
                "type": "error",
                "icon": "🌊",
                "title": f"Cascading Failure: {svc}",
                "description": f"{svc} returning errors due to upstream payment failure",
                "details": {
                    "Upstream": "payment-service",
                    "Error": "HTTP 502/500",
                    "Impact": "Request propagation failure",
                },
                "severity": "critical",
            })

    # Recovery events
    inc_end = parse_ts(gt.get("incident_end_time", ""))
    events.append({
        "time": inc_end,
        "time_str": format_ts(gt.get("incident_end_time", "")),
        "type": "recovery",
        "icon": "🔧",
        "title": "Fault Reset Initiated",
        "description": "Payment-service fault mode reset to 'none'",
        "details": {
            "Action": "POST /admin/reset",
            "Service": "payment-service",
            "Leaked Connections Released": "5",
        },
        "severity": "info",
    })

    events.append({
        "time": inc_end + timedelta(seconds=2),
        "time_str": format_ts((inc_end + timedelta(seconds=2)).isoformat()),
        "type": "recovery",
        "icon": "🟢",
        "title": "Services Recovered",
        "description": "All services returning HTTP 200",
        "details": {
            "Recovery Traffic": f"{gt.get('recovery_traffic', {}).get('total', 0)} requests",
            "Error Rate": f"{gt.get('recovery_traffic', {}).get('error_rate', 0):.1%}",
            "Avg Latency": f"{gt.get('recovery_traffic', {}).get('avg_latency_ms', 0):.1f}ms",
        },
        "severity": "info",
    })

    return sorted(events, key=lambda x: x["time"])


def render_timeline_chart(events: list[dict], filters: dict):
    """Render an interactive Plotly timeline chart."""
    if not events:
        st.info("No timeline events to display.")
        return

    # Filter events
    filtered = []
    for e in events:
        if e["type"] == "deployment" and not filters["show_deployments"]:
            continue
        if e["type"] == "anomaly" and not filters["show_anomalies"]:
            continue
        if e["type"] == "error" and not filters["show_errors"]:
            continue
        if e["type"] == "recovery" and not filters["show_recovery"]:
            continue
        filtered.append(e)

    if not filtered:
        st.info("No events match current filters.")
        return

    # Create timeline dataframe
    df = pd.DataFrame([
        {
            "Start": e["time"],
            "End": e["time"] + timedelta(seconds=2),
            "Event": e["title"],
            "Type": e["type"].capitalize(),
            "Severity": e["severity"],
            "Description": e["description"],
            "Icon": e["icon"],
        }
        for e in filtered
    ])

    # Color map by severity
    color_map = {
        "info": "#1f77b4",
        "warning": "#ff7f0e",
        "critical": "#d62728",
    }

    fig = px.timeline(
        df,
        x_start="Start",
        x_end="End",
        y="Event",
        color="Severity",
        color_discrete_map=color_map,
        hover_data=["Description", "Type"],
        title="Incident Timeline",
        height=400,
    )

    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="",
        showlegend=True,
        hovermode="closest",
    )

    st.plotly_chart(fig, use_container_width=True)


def render_event_details(events: list[dict], filters: dict):
    """Render detailed event cards."""
    st.subheader("📋 Event Details")

    # Filter events
    filtered = []
    for e in events:
        if e["type"] == "deployment" and not filters["show_deployments"]:
            continue
        if e["type"] == "anomaly" and not filters["show_anomalies"]:
            continue
        if e["type"] == "error" and not filters["show_errors"]:
            continue
        if e["type"] == "recovery" and not filters["show_recovery"]:
            continue
        filtered.append(e)

    for event in filtered:
        severity_colors = {
            "info": "🔵",
            "warning": "🟡",
            "critical": "🔴",
        }

        with st.expander(f"{event['icon']} {event['time_str']} - {event['title']} [{severity_colors.get(event['severity'], '⚪')}]"):
            col1, col2 = st.columns([1, 2])

            with col1:
                st.markdown(f"**Type:** {event['type'].capitalize()}")
                st.markdown(f"**Severity:** {event['severity'].capitalize()}")
                st.markdown(f"**Description:** {event['description']}")

            with col2:
                st.markdown("**Details:**")
                for key, value in event["details"].items():
                    st.markdown(f"- **{key}:** {value}")


def render_metrics_timeline(gt: dict):
    """Render metrics over time (simulated)."""
    st.subheader("📊 Metrics Timeline (Simulated)")

    # Create simulated time series data
    base_time = parse_ts(gt.get("incident_start_time", datetime.now().isoformat()))
    time_points = [base_time + timedelta(seconds=i) for i in range(0, 45, 3)]

    baseline_latency = gt.get("healthy_baseline", {}).get("avg_latency_ms", 18.5)
    incident_latency = gt.get("incident_traffic", {}).get("avg_latency_ms", 420.7)
    baseline_error = gt.get("healthy_baseline", {}).get("error_rate", 0)
    incident_error = gt.get("incident_traffic", {}).get("error_rate", 0.84)

    # Simulate latency progression
    latencies = []
    errors = []
    pool_usage = []

    for i, t in enumerate(time_points):
        if i < 3:  # Pre-incident
            latencies.append(baseline_latency + (i * 2))
            errors.append(baseline_error)
            pool_usage.append(20 + i * 5)
        elif i < 10:  # Incident ramp
            progress = (i - 3) / 7
            latencies.append(baseline_latency + progress * (incident_latency - baseline_latency))
            errors.append(baseline_error + progress * (incident_error - baseline_error))
            pool_usage.append(40 + progress * 60)
        elif i < 12:  # Peak
            latencies.append(incident_latency)
            errors.append(incident_error)
            pool_usage.append(100)
        else:  # Recovery
            recovery_progress = min((i - 12) / 3, 1.0)
            latencies.append(incident_latency - recovery_progress * (incident_latency - baseline_latency))
            errors.append(incident_error - recovery_progress * incident_error)
            pool_usage.append(100 - recovery_progress * 80)

    metrics_df = pd.DataFrame({
        "Time": time_points,
        "Latency (ms)": latencies,
        "Error Rate": errors,
        "DB Pool Usage (%)": pool_usage,
    })

    # Plot
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=metrics_df["Time"],
        y=metrics_df["Latency (ms)"],
        name="Latency (ms)",
        line=dict(color="#1f77b4", width=2),
        yaxis="y1",
    ))

    fig.add_trace(go.Scatter(
        x=metrics_df["Time"],
        y=metrics_df["Error Rate"],
        name="Error Rate",
        line=dict(color="#d62728", width=2),
        yaxis="y2",
    ))

    fig.add_trace(go.Scatter(
        x=metrics_df["Time"],
        y=metrics_df["DB Pool Usage (%)"],
        name="DB Pool Usage (%)",
        line=dict(color="#ff7f0e", width=2, dash="dot"),
        yaxis="y3",
    ))

    fig.update_layout(
        title="Key Metrics During Incident",
        xaxis=dict(title="Time", domain=[0, 1]),
        yaxis=dict(title="Latency (ms)", side="left", showgrid=False),
        yaxis2=dict(title="Error Rate", side="right", overlaying="y", range=[0, 1], showgrid=False),
        yaxis3=dict(title="Pool Usage (%)", side="right", overlaying="y", range=[0, 120], showgrid=False, position=0.95),
        hovermode="x unified",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)


def main():
    gt = load_ground_truth()
    deployments_df = load_deployments()

    if not gt:
        st.error("⚠️ No ground truth data found. Run the simulator first:")
        st.code("python -m simulator.run_scenario")
        st.stop()

    st.title("📅 Incident Timeline")
    st.caption(f"Scenario: {gt.get('scenario_id', 'Unknown')}")

    # Sidebar controls
    filters = render_sidebar(gt)

    # Build events
    events = build_timeline_events(gt)

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📈 Timeline Chart", "📋 Event Details", "📊 Metrics"])

    with tab1:
        render_timeline_chart(events, filters)

    with tab2:
        render_event_details(events, filters)

    with tab3:
        render_metrics_timeline(gt)

    # Navigation
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🏠 Overview", use_container_width=True):
            st.switch_page("app.py")
    with col2:
        if st.button("🕸️ Causal Graph", use_container_width=True):
            st.switch_page("pages/3_Causal_Graph.py")
    with col3:
        if st.button("🔬 Evidence", use_container_width=True):
            st.switch_page("pages/4_Evidence_Explorer.py")
    with col4:
        if st.button("📋 RCA Report", use_container_width=True):
            st.switch_page("pages/5_RCA_Report.py")


if __name__ == "__main__":
    main()