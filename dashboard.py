"""Offline Streamlit dashboard for MarketMind's simulated marketplace."""

from datetime import datetime
from os import getenv
from pathlib import Path

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
    panel = panel.container(key="claude_panel", border=True)
    panel.subheader("Claude AI analysis")
    analyses = st.session_state.setdefault("claude_analyses", {})
    incident_id = report["incident_id"]
    panel.caption("AI-assisted explanation of the evidence above. Clicking sends the simulated incident to Claude and may use API credits. Claude does not run follow-up checks.")
    if panel.button(
        "Analyze with Claude", key="analyze_claude", type="primary", disabled=incident_id in analyses
    ):
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


def _render_overview(data):
    st.html("""
        <header class="mm-header">
            <div class="mm-brand">
                <span class="mm-mark" aria-hidden="true">◈</span>
                <div><h1>MarketMind</h1><p>Intelligent Marketplace Observability</p></div>
            </div>
            <div class="mm-status">
                <span class="mm-chip"><span class="mm-dot" aria-hidden="true"></span>Scan complete</span>
                <span class="mm-chip">Simulated data · DE and FR</span>
            </div>
        </header>
    """)
    st.header("Marketplace overview")
    metrics = (
        ("Total visitors", f"{data['visitors'].sum():,}", "◉", "#80b6ff"),
        ("Checkout attempts", f"{data['checkout_attempts'].sum():,}", "◇", "#67deef"),
        ("Successful payments", f"{data['successful_payments'].sum():,}", "✓", "#b0a0ff"),
        ("Revenue", f"€{data['revenue'].sum():,.2f}", "€", "#84dbc5"),
    )
    cards = "".join(
        f'<div class="mm-kpi" style="--accent:{accent}">'
        f'<div class="mm-kpi-label"><span aria-hidden="true">{icon}</span>{label}</div>'
        f'<strong>{value}</strong></div>'
        for label, value, icon, accent in metrics
    )
    st.html(f'<div class="mm-kpis">{cards}</div>')


def _render_payment_comparison(panel, report):
    rates = (
        ("Baseline payment success", float(report["baseline_payment_success_rate"]), "baseline"),
        ("Observed payment success", float(report["current_payment_success_rate"]), "observed"),
    )
    bars = "".join(
        f'<div class="mm-rate-label"><span>{label}</span><strong>{rate:.1%}</strong></div>'
        f'<div class="mm-track" aria-hidden="true">'
        f'<div class="mm-fill mm-{kind}" style="width:{rate * 100:.2f}%"></div></div>'
        for label, rate, kind in rates
    )
    panel.html(f'<div class="mm-comparison">{bars}</div>')


def render_dashboard(data, graph, reports):
    _render_overview(data)
    graph_column, detail_column = st.columns([1.75, 1], gap="medium")
    graph_panel = graph_column.container(key="metric_graph", border=True)
    incident_panel = detail_column.container(key="incident_panel", border=True)
    incident_panel.header("Incident investigation")
    by_id = {report["incident_id"]: report for report in reports}
    report = None
    if by_id:
        incident_panel.html(
            '<span class="mm-chip"><span class="mm-dot mm-alert-dot" aria-hidden="true"></span>'
            f'{len(by_id)} {"incident" if len(by_id) == 1 else "incidents"} detected</span>'
        )
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
        _render_payment_comparison(incident_panel, report)
        incident_panel.markdown(
            f":orange[**↓ {report['drop_percentage_points']:.1f} percentage points**]"
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
        _render_claude_analysis(graph_column, report, graph)


def main():
    st.set_page_config(page_title="MarketMind", layout="wide")
    st.html(Path(__file__).with_name("dashboard.css"))
    render_dashboard(*load_demo())


if __name__ == "__main__":
    main()
