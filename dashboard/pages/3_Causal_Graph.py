"""TraceMind AI - Causal Graph (Page 3).

Interactive causal graph visualization showing service dependencies,
trace spans, log events, metric anomalies, and deployment correlations.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

st.set_page_config(
    page_title="TraceMind AI - Causal Graph",
    page_icon="🕸️",
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


def build_causal_graph(gt: dict) -> nx.DiGraph:
    """Build a NetworkX directed graph representing the causal relationships."""
    G = nx.DiGraph()

    # Nodes: Services
    services = ["api-gateway", "order-service", "payment-service", "user-service", "postgresql"]
    for svc in services:
        is_root = svc == gt.get("root_cause_service", "")
        is_affected = svc in gt.get("affected_services", [])
        G.add_node(
            svc,
            type="service",
            label=svc,
            is_root_cause=is_root,
            is_affected=is_affected,
            color="#d62728" if is_root else ("#ff7f0e" if is_affected else "#1f77b4"),
            size=30 if is_root or is_affected else 20,
        )

    # Nodes: Deployment
    deployment = gt.get("deployment", {})
    if deployment:
        dep_id = deployment.get("deployment_id", "dep-unknown")
        G.add_node(
            dep_id,
            type="deployment",
            label=f"Deployment\n{deployment.get('service_name', 'Unknown')}",
            color="#9467bd",
            size=25,
            details={
                "Deployment ID": dep_id,
                "Service": deployment.get("service_name", "N/A"),
                "Timestamp": deployment.get("timestamp", "N/A"),
                "Commit": deployment.get("commit_sha", "N/A")[:8],
                "Change": deployment.get("change_summary", "N/A"),
            },
        )
        # Deployment -> Service edge
        G.add_edge(dep_id, deployment.get("service_name", "payment-service"), type="deployed_to", label="DEPLOYED_TO")

    # Nodes: Metric Anomalies
    anomalies = [
        ("anomaly-db-pool", "DB Pool Exhaustion", "payment-service", "critical"),
        ("anomaly-latency", "Latency Spike", "payment-service", "warning"),
        ("anomaly-error-rate", "Error Rate Spike", "api-gateway", "critical"),
    ]
    for node_id, label, service, severity in anomalies:
        color = {"critical": "#d62728", "warning": "#ff7f0e", "info": "#1f77b4"}[severity]
        G.add_node(node_id, type="anomaly", label=label, color=color, size=20, severity=severity)
        G.add_edge(service, node_id, type="observed_during", label="OBSERVED_DURING")

    # Nodes: Error Events
    errors = [
        ("error-payment-timeout", "Payment Timeout", "payment-service"),
        ("error-order-failed", "Order Failed", "order-service"),
        ("error-gateway-500", "Gateway 500", "api-gateway"),
    ]
    for node_id, label, service in errors:
        G.add_node(node_id, type="error", label=label, color="#d62728", size=18)
        G.add_edge(service, node_id, type="generated", label="GENERATED")

    # Service dependency edges (CALLS)
    G.add_edge("api-gateway", "order-service", type="calls", label="CALLS")
    G.add_edge("order-service", "payment-service", type="calls", label="CALLS")
    G.add_edge("order-service", "user-service", type="calls", label="CALLS")
    G.add_edge("payment-service", "postgresql", type="calls", label="CALLS")

    # Causal edges (PRECEDED / propagation)
    G.add_edge("payment-service", "order-service", type="preceded", label="PRECEDED")
    G.add_edge("order-service", "api-gateway", type="preceded", label="PRECEDED")

    # Deployment -> Anomaly (candidate cause)
    if deployment:
        dep_id = deployment.get("deployment_id", "dep-unknown")
        G.add_edge(dep_id, "anomaly-db-pool", type="supports_hypothesis", label="SUPPORTS_HYPOTHESIS")

    return G


def render_graph_visualization(G: nx.DiGraph, layout: str = "hierarchical"):
    """Render the causal graph using streamlit-agraph."""
    nodes = []
    edges = []

    # Color mapping for node types
    type_colors = {
        "service": "#1f77b4",
        "deployment": "#9467bd",
        "anomaly": "#ff7f0e",
        "error": "#d62728",
    }

    for node_id, data in G.nodes(data=True):
        node_type = data.get("type", "unknown")
        color = data.get("color", type_colors.get(node_type, "#7f7f7f"))
        size = data.get("size", 20)
        label = data.get("label", node_id)

        # Shape by type
        shape = {
            "service": "box",
            "deployment": "diamond",
            "anomaly": "triangle",
            "error": "triangleDown",
        }.get(node_type, "ellipse")

        nodes.append(Node(
            id=node_id,
            label=label,
            size=size,
            color=color,
            shape=shape,
            font={"size": 11, "color": "#333"},
            title=str(data.get("details", "")) if "details" in data else "",
        ))

    for source, target, data in G.edges(data=True):
        edge_type = data.get("type", "unknown")
        label = data.get("label", edge_type)

        # Edge style by type
        color = {
            "calls": "#1f77b4",
            "deployed_to": "#9467bd",
            "observed_during": "#ff7f0e",
            "generated": "#d62728",
            "preceded": "#2ca02c",
            "supports_hypothesis": "#9467bd",
        }.get(edge_type, "#7f7f7f")

        dashes = edge_type in ["preceded", "supports_hypothesis"]

        edges.append(Edge(
            source=source,
            target=target,
            label=label,
            color=color,
            dashes=dashes,
            width=2,
            font={"size": 10, "align": "middle"},
            arrows="to",
        ))

    config = Config(
        width=900,
        height=600,
        directed=True,
        physics=True,
        hierarchical=layout == "hierarchical",
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=True,
    )

    return agraph(nodes=nodes, edges=edges, config=config)


def render_graph_legend():
    """Render a legend for the graph."""
    st.markdown("### 📖 Graph Legend")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("**Node Types**")
        st.markdown("🔵 Service (healthy)")
        st.markdown("🟠 Service (affected)")
        st.markdown("🔴 Service (root cause)")
        st.markdown("🟣 Deployment")
        st.markdown("🟠 Anomaly (warning)")
        st.markdown("🔴 Anomaly/Error (critical)")

    with col2:
        st.markdown("**Edge Types**")
        st.markdown("🔵 Solid: CALLS (service dependency)")
        st.markdown("🟣 Solid: DEPLOYED_TO")
        st.markdown("🟠 Solid: OBSERVED_DURING")
        st.markdown("🔴 Solid: GENERATED (error)")
        st.markdown("🟢 Dashed: PRECEDED (temporal)")
        st.markdown("🟣 Dashed: SUPPORTS_HYPOTHESIS")

    with col3:
        st.markdown("**Key Relationships**")
        st.markdown("- Deployment → Service (deployed_to)")
        st.markdown("- Service → Anomaly (observed_during)")
        st.markdown("- Service → Error (generated)")
        st.markdown("- Service → Service (calls/preceded)")
        st.markdown("- Deployment → Anomaly (supports_hypothesis)")

    with col4:
        st.markdown("**Interaction**")
        st.markdown("- Drag nodes to reposition")
        st.markdown("- Scroll to zoom")
        st.markdown("- Hover for details")
        st.markdown("- Click node to highlight")
        st.markdown("- Use layout toggle in sidebar")


def render_node_details_panel(G: nx.DiGraph, selected_node: str | None):
    """Render detailed information for a selected node."""
    if not selected_node or selected_node not in G.nodes:
        return

    data = G.nodes[selected_node]
    node_type = data.get("type", "unknown")

    with st.sidebar:
        st.divider()
        st.subheader(f"🔍 Node Details: {data.get('label', selected_node)}")
        st.markdown(f"**Type:** {node_type}")
        st.markdown(f"**ID:** `{selected_node}`")

        if "details" in data:
            st.markdown("**Properties:**")
            for k, v in data["details"].items():
                st.markdown(f"- **{k}:** {v}")

        # Show connected edges
        st.markdown("**Connections:**")
        for pred in G.predecessors(selected_node):
            edge_data = G.edges[pred, selected_node]
            st.markdown(f"← {pred} ({edge_data.get('label', '')})")
        for succ in G.successors(selected_node):
            edge_data = G.edges[selected_node, succ]
            st.markdown(f"→ {succ} ({edge_data.get('label', '')})")


def render_path_analysis(G: nx.DiGraph):
    """Render path analysis from deployment to errors."""
    st.subheader("🔍 Causal Path Analysis")

    deployment_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "deployment"]
    error_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "error"]

    if not deployment_nodes or not error_nodes:
        st.info("Insufficient data for path analysis.")
        return

    for dep in deployment_nodes:
        for err in error_nodes:
            try:
                paths = list(nx.all_simple_paths(G, dep, err, cutoff=5))
                if paths:
                    st.markdown(f"**Path: {dep} → {err}**")
                    for i, path in enumerate(paths[:3]):  # Show top 3 paths
                        path_str = " → ".join([G.nodes[n].get("label", n) for n in path])
                        st.markdown(f"  {i+1}. `{path_str}`")
            except nx.NetworkXNoPath:
                pass


def render_graph_statistics(G: nx.DiGraph):
    """Render graph statistics."""
    st.subheader("📊 Graph Statistics")

    node_types = {}
    for _, data in G.nodes(data=True):
        t = data.get("type", "unknown")
        node_types[t] = node_types.get(t, 0) + 1

    edge_types = {}
    for _, _, data in G.edges(data=True):
        t = data.get("type", "unknown")
        edge_types[t] = edge_types.get(t, 0) + 1

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Total Nodes", G.number_of_nodes())
        st.metric("Total Edges", G.number_of_edges())

    with col2:
        st.markdown("**Nodes by Type:**")
        for t, count in node_types.items():
            st.markdown(f"- {t.capitalize()}: {count}")

    with col3:
        st.markdown("**Edges by Type:**")
        for t, count in edge_types.items():
            st.markdown(f"- {t}: {count}")


def main():
    gt = load_ground_truth()
    deployments_df = load_deployments()

    if not gt:
        st.error("⚠️ No ground truth data found. Run the simulator first:")
        st.code("python -m simulator.run_scenario")
        st.stop()

    st.title("🕸️ Causal Graph")
    st.caption(f"Scenario: {gt.get('scenario_id', 'Unknown')}")

    # Build graph
    G = build_causal_graph(gt)

    # Sidebar controls
    with st.sidebar:
        st.header("🕸️ Graph Controls")

        layout = st.radio(
            "Layout",
            options=["hierarchical", "force-directed"],
            format_func=lambda x: "📊 Hierarchical" if x == "hierarchical" else "🌐 Force-Directed",
            index=0,
        )

        st.divider()

        # Node type filters
        st.subheader("🎯 Node Filters")
        show_services = st.checkbox("Services", value=True)
        show_deployments = st.checkbox("Deployments", value=True)
        show_anomalies = st.checkbox("Anomalies", value=True)
        show_errors = st.checkbox("Errors", value=True)

        st.divider()

        # Edge type filters
        st.subheader("🔗 Edge Filters")
        show_calls = st.checkbox("CALLS", value=True)
        show_deployed = st.checkbox("DEPLOYED_TO", value=True)
        show_observed = st.checkbox("OBSERVED_DURING", value=True)
        show_generated = st.checkbox("GENERATED", value=True)
        show_preceded = st.checkbox("PRECEDED", value=True)
        show_hypothesis = st.checkbox("SUPPORTS_HYPOTHESIS", value=True)

        st.divider()

        if st.button("📥 Export Graph (GraphML)", use_container_width=True):
            import io
            buffer = io.BytesIO()
            nx.write_graphml(G, buffer)
            st.download_button(
                "Download GraphML",
                data=buffer.getvalue(),
                file_name="causal_graph.graphml",
                mime="application/xml",
                use_container_width=True,
            )

    # Apply filters
    # (In a real implementation, we'd filter the graph here)

    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🕸️ Interactive Graph", "📊 Statistics", "🔍 Path Analysis", "📖 Legend"])

    with tab1:
        render_graph_visualization(G, layout)

    with tab2:
        render_graph_statistics(G)

    with tab3:
        render_path_analysis(G)

    with tab4:
        render_graph_legend()

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
        if st.button("🔬 Evidence", use_container_width=True):
            st.switch_page("pages/4_Evidence_Explorer.py")
    with col4:
        if st.button("📋 RCA Report", use_container_width=True):
            st.switch_page("pages/5_RCA_Report.py")


if __name__ == "__main__":
    main()