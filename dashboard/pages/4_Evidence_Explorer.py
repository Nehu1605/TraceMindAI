"""TraceMind AI - Evidence Explorer (Page 4).

Explore logs, spans, metrics, and commits correlated to the incident.
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
    page_title="TraceMind AI - Evidence Explorer",
    page_icon="🔬",
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


def generate_sample_logs(gt: dict) -> pd.DataFrame:
    """Generate sample structured logs for the incident."""
    base_time = datetime.fromisoformat(gt.get("incident_start_time", "").replace("Z", "+00:00"))
    logs = []

    # Healthy baseline logs
    for i in range(10):
        logs.append({
            "timestamp": (base_time - timedelta(seconds=30 - i * 3)).isoformat(),
            "service": "payment-service",
            "level": "INFO",
            "event_type": "PAYMENT_APPROVED",
            "message": f"Payment approved for order ord-{1000+i}",
            "trace_id": f"trace-{1000+i:06d}",
            "span_id": f"span-{1000+i:06d}",
            "severity": "INFO",
        })

    # Incident logs - connection leaks
    for i in range(5):
        logs.append({
            "timestamp": (base_time + timedelta(seconds=2 + i * 2)).isoformat(),
            "service": "payment-service",
            "level": "WARN",
            "event_type": "DB_CONNECTION_LEAK",
            "message": f"Leaked a database connection (simulated defect) - count: {i+1}",
            "trace_id": f"trace-incident-{2000+i:06d}",
            "span_id": f"span-{2000+i:06d}",
            "severity": "WARN",
        })

    # Connection pool exhausted
    for i in range(8):
        logs.append({
            "timestamp": (base_time + timedelta(seconds=10 + i)).isoformat(),
            "service": "payment-service",
            "level": "ERROR",
            "event_type": "DATABASE_ERROR",
            "message": "Database connection acquisition timeout",
            "trace_id": f"trace-incident-{3000+i:06d}",
            "span_id": f"span-{3000+i:06d}",
            "severity": "ERROR",
        })

    # Order service errors
    for i in range(5):
        logs.append({
            "timestamp": (base_time + timedelta(seconds=12 + i)).isoformat(),
            "service": "order-service",
            "level": "ERROR",
            "event_type": "UPSTREAM_ERROR",
            "message": "Payment service returned 503: database connection acquisition timeout",
            "trace_id": f"trace-incident-{3000+i:06d}",
            "span_id": f"span-{4000+i:06d}",
            "severity": "ERROR",
        })

    # Gateway errors
    for i in range(5):
        logs.append({
            "timestamp": (base_time + timedelta(seconds=13 + i)).isoformat(),
            "service": "api-gateway",
            "level": "ERROR",
            "event_type": "HTTP_500",
            "message": "Upstream order-service returned 502",
            "trace_id": f"trace-incident-{3000+i:06d}",
            "span_id": f"span-{5000+i:06d}",
            "severity": "ERROR",
        })

    # Recovery logs
    for i in range(5):
        logs.append({
            "timestamp": (base_time + timedelta(seconds=40 + i * 2)).isoformat(),
            "service": "payment-service",
            "level": "INFO",
            "event_type": "PAYMENT_APPROVED",
            "message": f"Payment approved for order ord-{5000+i}",
            "trace_id": f"trace-recovery-{6000+i:06d}",
            "span_id": f"span-{6000+i:06d}",
            "severity": "INFO",
        })

    return pd.DataFrame(logs)


def generate_sample_spans(gt: dict) -> pd.DataFrame:
    """Generate sample trace spans for the incident."""
    base_time = datetime.fromisoformat(gt.get("incident_start_time", "").replace("Z", "+00:00"))
    spans = []

    # Healthy spans
    for i in range(5):
        start = base_time - timedelta(seconds=30 - i * 5)
        spans.append({
            "trace_id": f"trace-{1000+i:06d}",
            "span_id": f"span-{1000+i:06d}",
            "parent_span_id": None,
            "service": "api-gateway",
            "operation": "POST /orders",
            "start_time": start.isoformat(),
            "duration_ms": 15 + i * 2,
            "status": "OK",
            "http_status": 200,
        })

    # Incident spans - showing propagation
    for i in range(8):
        start = base_time + timedelta(seconds=5 + i)
        trace_id = f"trace-incident-{3000+i:06d}"

        # Gateway span
        spans.append({
            "trace_id": trace_id,
            "span_id": f"span-{5000+i:06d}",
            "parent_span_id": None,
            "service": "api-gateway",
            "operation": "POST /orders",
            "start_time": start.isoformat(),
            "duration_ms": 2000 + i * 100,
            "status": "ERROR",
            "http_status": 500,
        })

        # Order span
        spans.append({
            "trace_id": trace_id,
            "span_id": f"span-{4000+i:06d}",
            "parent_span_id": f"span-{5000+i:06d}",
            "service": "order-service",
            "operation": "POST /orders",
            "start_time": (start + timedelta(milliseconds=5)).isoformat(),
            "duration_ms": 1900 + i * 100,
            "status": "ERROR",
            "http_status": 502,
        })

        # Payment span
        spans.append({
            "trace_id": trace_id,
            "span_id": f"span-{3000+i:06d}",
            "parent_span_id": f"span-{4000+i:06d}",
            "service": "payment-service",
            "operation": "POST /pay",
            "start_time": (start + timedelta(milliseconds=10)).isoformat(),
            "duration_ms": 1800 + i * 100,
            "status": "ERROR",
            "http_status": 503,
        })

    # Recovery spans
    for i in range(5):
        start = base_time + timedelta(seconds=40 + i * 2)
        trace_id = f"trace-recovery-{6000+i:06d}"
        spans.append({
            "trace_id": trace_id,
            "span_id": f"span-{6000+i:06d}",
            "parent_span_id": None,
            "service": "api-gateway",
            "operation": "POST /orders",
            "start_time": start.isoformat(),
            "duration_ms": 18 + i,
            "status": "OK",
            "http_status": 200,
        })

    return pd.DataFrame(spans)


def generate_sample_metrics(gt: dict) -> pd.DataFrame:
    """Generate sample metrics for the incident."""
    base_time = datetime.fromisoformat(gt.get("incident_start_time", "").replace("Z", "+00:00"))
    metrics = []

    services = ["api-gateway", "order-service", "payment-service", "user-service"]

    for i in range(60):  # 60 time points, 1 second apart
        t = base_time + timedelta(seconds=i - 30)  # 30s before to 30s after

        for svc in services:
            if i < 30:  # Pre-incident
                latency = 15 + (i % 5) * 2
                error_rate = 0
                pool_usage = 20
            elif i < 40:  # Incident
                progress = (i - 30) / 10
                if svc == "payment-service":
                    latency = 50 + progress * 2000
                    error_rate = progress * 0.9
                    pool_usage = 30 + progress * 70
                elif svc == "order-service":
                    latency = 20 + progress * 1800
                    error_rate = progress * 0.8
                    pool_usage = 20
                else:
                    latency = 15 + progress * 100
                    error_rate = progress * 0.1
                    pool_usage = 20
            else:  # Recovery
                progress = min((i - 40) / 10, 1.0)
                latency = 2000 * (1 - progress) + 15
                error_rate = 0.9 * (1 - progress)
                pool_usage = 100 * (1 - progress) + 20

            metrics.append({
                "timestamp": t.isoformat(),
                "service": svc,
                "latency_p50_ms": latency,
                "latency_p99_ms": latency * 2.5,
                "error_rate": error_rate,
                "request_rate": 5.0,
                "db_pool_usage": pool_usage if svc in ["payment-service", "user-service"] else 0,
            })

    return pd.DataFrame(metrics)


def render_logs_tab(logs_df: pd.DataFrame):
    """Render the logs exploration tab."""
    st.subheader("📝 Structured Logs")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        services = ["All"] + sorted(logs_df["service"].unique().tolist())
        selected_service = st.selectbox("Service", services)
    with col2:
        levels = ["All"] + sorted(logs_df["level"].unique().tolist())
        selected_level = st.selectbox("Level", levels)
    with col3:
        event_types = ["All"] + sorted(logs_df["event_type"].unique().tolist())
        selected_event = st.selectbox("Event Type", event_types)
    with col4:
        search = st.text_input("Search", placeholder="Filter messages...")

    # Apply filters
    filtered = logs_df.copy()
    if selected_service != "All":
        filtered = filtered[filtered["service"] == selected_service]
    if selected_level != "All":
        filtered = filtered[filtered["level"] == selected_level]
    if selected_event != "All":
        filtered = filtered[filtered["event_type"] == selected_event]
    if search:
        filtered = filtered[filtered["message"].str.contains(search, case=False)]

    # Display
    st.markdown(f"**Showing {len(filtered)} of {len(logs_df)} log entries**")

    # Color by severity
    def color_severity(val):
        colors = {
            "ERROR": "background-color: #ffcccc",
            "WARN": "background-color: #fff3cd",
            "INFO": "background-color: #d4edda",
        }
        return colors.get(val, "")

    display_df = filtered[["timestamp", "service", "level", "event_type", "message", "trace_id", "span_id"]].copy()
    display_df["timestamp"] = pd.to_datetime(display_df["timestamp"]).dt.strftime("%H:%M:%S.%f").str[:-3]

    st.dataframe(
        display_df.style.applymap(color_severity, subset=["level"]),
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    # Trace ID drill-down
    st.divider()
    st.subheader("🔍 Trace Correlation")
    trace_ids = filtered["trace_id"].unique()
    if len(trace_ids) > 0:
        selected_trace = st.selectbox("Select Trace ID to view spans", ["Select..."] + sorted(trace_ids.tolist()))
        if selected_trace != "Select...":
            st.session_state["selected_trace"] = selected_trace


def render_spans_tab(spans_df: pd.DataFrame):
    """Render the trace spans exploration tab."""
    st.subheader("🔗 Trace Spans")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        services = ["All"] + sorted(spans_df["service"].unique().tolist())
        selected_service = st.selectbox("Service ", services)
    with col2:
        statuses = ["All"] + sorted(spans_df["status"].unique().tolist())
        selected_status = st.selectbox("Status", statuses)
    with col3:
        trace_filter = st.text_input("Trace ID", placeholder="Filter by trace ID...")

    filtered = spans_df.copy()
    if selected_service != "All":
        filtered = filtered[filtered["service"] == selected_service]
    if selected_status != "All":
        filtered = filtered[filtered["status"] == selected_status]
    if trace_filter:
        filtered = filtered[filtered["trace_id"].str.contains(trace_filter)]

    st.markdown(f"**Showing {len(filtered)} of {len(spans_df)} spans**")

    # Duration chart
    if not filtered.empty:
        fig = px.scatter(
            filtered,
            x="start_time",
            y="duration_ms",
            color="service",
            symbol="status",
            hover_data=["trace_id", "span_id", "operation", "http_status"],
            title="Span Duration Timeline",
            labels={"duration_ms": "Duration (ms)", "start_time": "Start Time"},
        )
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    # Span table
    display_df = filtered[["trace_id", "span_id", "parent_span_id", "service", "operation", "start_time", "duration_ms", "status", "http_status"]].copy()
    display_df["start_time"] = pd.to_datetime(display_df["start_time"]).dt.strftime("%H:%M:%S.%f").str[:-3]

    def color_status(val):
        return "background-color: #ffcccc" if val == "ERROR" else "background-color: #d4edda"

    st.dataframe(
        display_df.style.applymap(color_status, subset=["status"]),
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    # Flame graph view for selected trace
    if "selected_trace" in st.session_state:
        trace_spans = spans_df[spans_df["trace_id"] == st.session_state["selected_trace"]]
        if not trace_spans.empty:
            st.divider()
            st.subheader(f"🔥 Flame Graph: {st.session_state['selected_trace']}")
            render_flame_graph(trace_spans)


def render_flame_graph(spans_df: pd.DataFrame):
    """Render a simple flame graph for a trace."""
    # Build hierarchy
    root_spans = spans_df[spans_df["parent_span_id"].isna()]

    for _, root in root_spans.iterrows():
        render_span_tree(spans_df, root["span_id"], 0)


def render_span_tree(spans_df: pd.DataFrame, span_id: str, depth: int):
    """Recursively render span tree."""
    span = spans_df[spans_df["span_id"] == span_id]
    if span.empty:
        return

    span = span.iloc[0]
    indent = "  " * depth
    status_icon = "✅" if span["status"] == "OK" else "❌"

    with st.expander(f"{indent}{status_icon} {span['service']} - {span['operation']} ({span['duration_ms']:.0f}ms)"):
        st.markdown(f"**Span ID:** {span['span_id']}")
        st.markdown(f"**Trace ID:** {span['trace_id']}")
        st.markdown(f"**Parent:** {span['parent_span_id'] or 'ROOT'}")
        st.markdown(f"**Duration:** {span['duration_ms']:.0f}ms")
        st.markdown(f"**Status:** {span['status']}")
        st.markdown(f"**HTTP Status:** {span['http_status']}")

    # Children
    children = spans_df[spans_df["parent_span_id"] == span_id]
    for _, child in children.iterrows():
        render_span_tree(spans_df, child["span_id"], depth + 1)


def render_metrics_tab(metrics_df: pd.DataFrame):
    """Render the metrics exploration tab."""
    st.subheader("📈 Metrics")

    # Service selector
    services = sorted(metrics_df["service"].unique().tolist())
    selected_services = st.multiselect("Services", services, default=services)

    filtered = metrics_df[metrics_df["service"].isin(selected_services)]

    # Metric selector
    metric = st.selectbox(
        "Metric",
        ["latency_p50_ms", "latency_p99_ms", "error_rate", "request_rate", "db_pool_usage"],
        format_func=lambda x: {
            "latency_p50_ms": "Latency P50 (ms)",
            "latency_p99_ms": "Latency P99 (ms)",
            "error_rate": "Error Rate",
            "request_rate": "Request Rate (rps)",
            "db_pool_usage": "DB Pool Usage (%)",
        }[x],
    )

    # Time series chart
    fig = px.line(
        filtered,
        x="timestamp",
        y=metric,
        color="service",
        title=f"{metric} Over Time",
        labels={"timestamp": "Time", metric: metric},
    )
    fig.update_layout(height=400, hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    # Heatmap
    st.divider()
    st.subheader("🔥 Service Metrics Heatmap")

    # Pivot for heatmap
    pivot = filtered.pivot_table(index="service", columns="timestamp", values=metric, aggfunc="mean")
    pivot.columns = pd.to_datetime(pivot.columns).strftime("%H:%M:%S")

    fig = px.imshow(
        pivot,
        aspect="auto",
        color_continuous_scale="RdYlGn_r" if metric in ["latency_p50_ms", "latency_p99_ms", "error_rate"] else "RdYlGn",
        title=f"{metric} Heatmap",
    )
    fig.update_layout(height=300)
    st.plotly_chart(fig, use_container_width=True)


def render_deployments_tab(deployments_df: pd.DataFrame, gt: dict):
    """Render the deployments/commits tab."""
    st.subheader("🚀 Deployments & Commits")

    if deployments_df.empty:
        st.info("No deployment data available.")
        return

    # Show deployment details
    for _, dep in deployments_df.iterrows():
        with st.expander(f"🚀 {dep['deployment_id']} - {dep['service_name']} ({dep['timestamp']})"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Deployment ID:** {dep['deployment_id']}")
                st.markdown(f"**Service:** {dep['service_name']}")
                st.markdown(f"**Timestamp:** {dep['timestamp']}")
                st.markdown(f"**Status:** {dep['status']}")
            with col2:
                st.markdown(f"**Commit SHA:** {dep['commit_sha']}")
                st.markdown(f"**Changed Files:** {dep['changed_files']}")
                st.markdown(f"**Summary:** {dep['change_summary']}")

    # Correlation with incident
    st.divider()
    st.subheader("🔗 Deployment-Incident Correlation")

    incident_start = gt.get("incident_start_time", "")
    if incident_start:
        inc_time = datetime.fromisoformat(incident_start.replace("Z", "+00:00"))
        for _, dep in deployments_df.iterrows():
            dep_time = datetime.fromisoformat(dep["timestamp"].replace("Z", "+00:00"))
            diff = (inc_time - dep_time).total_seconds()
            if 0 <= diff <= 3600:  # Within 1 hour before incident
                st.success(f"✅ Deployment {dep['deployment_id']} occurred {diff:.0f}s before incident - **STRONG CORRELATION**")
            elif -3600 <= diff < 0:
                st.warning(f"⚠️ Deployment {dep['deployment_id']} occurred {abs(diff):.0f}s after incident start - **POSSIBLE CORRELATION**")
            else:
                st.info(f"ℹ️ Deployment {dep['deployment_id']} occurred {diff:.0f}s from incident - **WEAK/NO CORRELATION**")


def main():
    gt = load_ground_truth()
    deployments_df = load_deployments()

    if not gt:
        st.error("⚠️ No ground truth data found. Run the simulator first:")
        st.code("python -m simulator.run_scenario")
        st.stop()

    st.title("🔬 Evidence Explorer")
    st.caption(f"Scenario: {gt.get('scenario_id', 'Unknown')}")

    # Generate sample data
    logs_df = generate_sample_logs(gt)
    spans_df = generate_sample_spans(gt)
    metrics_df = generate_sample_metrics(gt)

    # Sidebar
    with st.sidebar:
        st.header("🔬 Evidence Controls")
        st.markdown("**Data Sources:**")
        st.markdown("- Structured JSON logs")
        st.markdown("- OpenTelemetry spans")
        st.markdown("- Prometheus metrics")
        st.markdown("- Deployment records")

        st.divider()

        if st.button("📥 Export All Evidence", use_container_width=True):
            evidence = {
                "logs": logs_df.to_dict("records"),
                "spans": spans_df.to_dict("records"),
                "metrics": metrics_df.to_dict("records"),
                "deployments": deployments_df.to_dict("records"),
            }
            st.download_button(
                "Download JSON",
                data=json.dumps(evidence, indent=2, default=str),
                file_name="incident_evidence.json",
                mime="application/json",
                use_container_width=True,
            )

    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Logs", "🔗 Spans", "📈 Metrics", "🚀 Deployments"])

    with tab1:
        render_logs_tab(logs_df)

    with tab2:
        render_spans_tab(spans_df)

    with tab3:
        render_metrics_tab(metrics_df)

    with tab4:
        render_deployments_tab(deployments_df, gt)

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
        if st.button("📋 RCA Report", use_container_width=True):
            st.switch_page("pages/5_RCA_Report.py")


if __name__ == "__main__":
    main()