"""Offline Streamlit dashboard for MarketMind's simulated marketplace."""

from datetime import datetime
from os import getenv

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from graph import build_graph
from monitoring.agent import run_monitoring
from monitoring.ai_explainer import ANALYSIS_SECTIONS, analyze_incident
from simulator import generate_data
from visualization import metric_graph_figure


@st.cache_data(show_spinner="Scanning simulated marketplace data…")
def load_demo():
    data = generate_data(seed=42)
    graph = build_graph()
    reports = run_monitoring(data, graph, ai_explain=False, state_path=None)
    return data, graph, reports


def _time_label(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).strftime("%d %b %Y, %H:%M")


def _render_claude_analysis(panel, report, graph):
    analyses = st.session_state.setdefault("claude_analyses", {})
    incident_id = report["incident_id"]
    panel.caption("Optional live analysis. Clicking sends this simulated incident to Claude and may use API credits.")
    if panel.button("Analyze with Claude", key="analyze_claude", disabled=incident_id in analyses):
        api_key = getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            try:
                api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
            except StreamlitSecretNotFoundError:
                api_key = ""
        if not isinstance(api_key, str) or not api_key.strip():
            panel.warning("Set ANTHROPIC_API_KEY in your environment or Streamlit secrets, then try again.")
        else:
            try:
                with panel.spinner("Analyzing the selected incident…"):
                    analyses[incident_id] = analyze_incident(report, graph, api_key=api_key)
            except RuntimeError as error:
                panel.warning(f"{error} The investigation report above is still available.")
            except ValueError:
                panel.warning("The incident path could not be validated. The offline report is still available.")
    if incident_id in analyses:
        panel.subheader("AI-generated hypothesis")
        for key, title in ANALYSIS_SECTIONS:
            panel.markdown(f"**{title}**")
            panel.text(analyses[incident_id][key])


def render_dashboard(data, graph, reports):
    st.title("MarketMind")
    st.caption("**Simulated data** · Germany and France · November 2026")

    st.header("Marketplace overview")
    visitors, orders, revenue, incidents = st.columns(4)
    visitors.metric("Visitors", f"{data['visitors'].sum():,}")
    orders.metric("Orders", f"{data['orders'].sum():,}")
    revenue.metric("Revenue", f"€{data['revenue'].sum():,.2f}")
    incidents.metric("Detected incidents", len(reports))

    graph_panel, incident_panel = st.columns([2, 1], gap="large")
    incident_panel.header("Incident investigation")
    by_id = {report["incident_id"]: report for report in reports}
    report = None
    if by_id:
        def incident_label(incident_id):
            entry = by_id[incident_id]
            return f"{entry['country']} / {entry['device']} · {_time_label(entry['start_timestamp'])}"

        selected_id = incident_panel.selectbox(
            "Select an incident", list(by_id), format_func=incident_label, key="incident"
        )
        report = by_id[selected_id]
        incident_panel.caption(
            f"{_time_label(report['start_timestamp'])} to "
            f"{_time_label(report['end_timestamp'])} · Europe/Berlin · "
            f"{report['hours_affected']} affected hours"
        )
        incident_panel.metric(
            "Payment success · baseline → observed",
            f"{report['baseline_payment_success_rate']:.1%} → {report['current_payment_success_rate']:.1%}",
            delta=f"-{report['drop_percentage_points']:.1f} percentage points",
            border=True,
        )
        incident_panel.metric("Observed revenue in affected hours", f"€{report['revenue_eur']:,.2f}")
    else:
        incident_panel.info("No incidents were detected in these simulated metrics.")

    graph_panel.header("Business metric graph")
    if report:
        graph_panel.caption("Orange marks the selected incident’s investigation path. Arrows point downstream.")
    graph_panel.plotly_chart(
        metric_graph_figure(graph, report["metric_path"] if report else ()),
        theme=None,
        config={"displayModeBar": False},
        alt="Directed business metric graph with the selected investigation path highlighted",
    )

    if report:
        incident_panel.subheader("Investigation report")
        incident_panel.write(report["explanation"])
        incident_panel.write(
            f"Evidence: {report['successful_payments']:,} successful payments from "
            f"{report['checkout_attempts']:,} attempts."
        )
        graph_panel.caption(" → ".join(metric.replace("_", " ").capitalize() for metric in report["metric_path"]))
        _render_claude_analysis(incident_panel, report, graph)


def main():
    st.set_page_config(page_title="MarketMind", layout="wide")
    render_dashboard(*load_demo())


if __name__ == "__main__":
    main()
