"""Run one monitoring pass over the generated marketplace data."""

import argparse
from pathlib import Path

from graph import build_graph
from simulator import generate_data
from monitoring.agent import run_monitoring


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor hourly marketplace metrics.")
    parser.add_argument("--seed", type=int, default=42, help="Repeatable demo-data seed.")
    parser.add_argument(
        "--ai-explain",
        action="store_true",
        help="Ask Claude to explain new incidents; uses API credits.",
    )
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Treat current incidents as new again, for a demo rerun.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    state_path = project_root / ".monitoring_state.json"
    if args.reset_state:
        state_path.write_text("[]", encoding="utf-8")

    data = generate_data(seed=args.seed)
    graph = build_graph()
    reports = run_monitoring(
        data,
        graph,
        ai_explain=args.ai_explain,
        state_path=state_path,
    )

    print(f"Rows scanned: {len(data)}")
    if not reports:
        print("No new incidents found.")
        return

    print(f"New incidents: {len(reports)}")
    for report in reports:
        print("-----------------------------")
        print(f"Incident: {report['incident_id']}")
        print(f"Segment: {report['country']} / {report['device']}")
        print(f"Time: {report['start_timestamp']} to {report['end_timestamp']}")
        print(
            "Payment success: "
            f"{report['baseline_payment_success_rate']:.0%} to "
            f"{report['current_payment_success_rate']:.0%}"
        )
        print(f"Revenue in affected hours: EUR {report['revenue_eur']:.2f}")
        print(f"Graph path: {' -> '.join(report['metric_path'])}")
        print(f"Explanation: {report['explanation']}")
        if "ai_explanation" in report:
            print(f"AI explanation: {report['ai_explanation']}")


if __name__ == "__main__":
    main()
