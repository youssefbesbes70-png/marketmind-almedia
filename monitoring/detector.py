"""Find payment-success drops in hourly, country/device-level data."""

from statistics import median
from typing import Any

import pandas as pd


_NUMERIC_COLUMNS = (
    "visitors",
    "checkout_attempts",
    "successful_payments",
    "payment_success_rate",
    "orders",
    "revenue",
)
REQUIRED_COLUMNS = {"timestamp", "country", "device", *_NUMERIC_COLUMNS}


def detect_payment_incidents(
    data: pd.DataFrame,
    *,
    min_attempts: int = 20,
    min_rate_drop: float = 0.25,
    max_current_rate: float = 0.70,
    lookback_days: int = 7,
    min_baseline_points: int = 3,
) -> list[dict[str, Any]]:
    """Find and group large payment-success drops for each country/device.

    Each hour is compared with earlier rows from the same country, device, and
    hour of day. Very small samples are skipped so quiet overnight hours do
    not create unstable payment-rate alerts. Incomplete rows are skipped,
    and only consecutive observed alert hours become one incident.
    """
    missing = REQUIRED_COLUMNS - set(data.columns)
    if missing:
        raise ValueError(f"Marketplace data is missing columns: {', '.join(sorted(missing))}")
    if min_attempts < 1 or min_baseline_points < 1 or lookback_days < 1:
        raise ValueError("Sample and lookback settings must be positive.")
    if not 0 <= min_rate_drop <= 1 or not 0 <= max_current_rate <= 1:
        raise ValueError("Payment-rate settings must be between 0 and 1.")

    frame = data.loc[:, sorted(REQUIRED_COLUMNS)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    for column in _NUMERIC_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        frame[column] = values.replace([float("inf"), float("-inf")], float("nan"))
    frame = frame.dropna()
    if frame.empty:
        return []
    frame["_hour"] = frame["timestamp"].dt.hour
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    cutoff_delta = pd.Timedelta(days=lookback_days)
    candidates: list[dict[str, Any]] = []

    for _, row in frame.iterrows():
        attempts = int(row["checkout_attempts"])
        current_rate = float(row["payment_success_rate"])
        if attempts < min_attempts or current_rate > max_current_rate:
            continue

        earlier = frame[
            (frame["country"] == row["country"])
            & (frame["device"] == row["device"])
            & (frame["_hour"] == row["_hour"])
            & (frame["timestamp"] < row["timestamp"])
            & (frame["timestamp"] >= row["timestamp"] - cutoff_delta)
        ]
        if len(earlier) < min_baseline_points:
            continue

        baseline_rate = float(median(float(value) for value in earlier["payment_success_rate"]))
        rate_drop = baseline_rate - current_rate
        if rate_drop < min_rate_drop:
            continue

        candidates.append(
            {
                "timestamp": row["timestamp"],
                "country": str(row["country"]),
                "device": str(row["device"]),
                "baseline_rate": baseline_rate,
                "current_rate": current_rate,
                "checkout_attempts": attempts,
                "successful_payments": int(row["successful_payments"]),
                "visitors": int(row["visitors"]),
                "orders": int(row["orders"]),
                "revenue": float(row["revenue"]),
            }
        )

    candidates.sort(key=lambda item: (item["country"], item["device"], item["timestamp"]))
    groups: list[list[dict[str, Any]]] = []
    for candidate in candidates:
        if groups:
            previous = groups[-1][-1]
            same_segment = (
                candidate["country"] == previous["country"]
                and candidate["device"] == previous["device"]
            )
            consecutive_hour = candidate["timestamp"] - previous["timestamp"] == pd.Timedelta(hours=1)
            if same_segment and consecutive_hour:
                groups[-1].append(candidate)
                continue
        groups.append([candidate])

    incidents: list[dict[str, Any]] = []
    for group in groups:
        baseline_rate = float(median(item["baseline_rate"] for item in group))
        total_attempts = sum(item["checkout_attempts"] for item in group)
        total_successes = sum(item["successful_payments"] for item in group)
        current_rate = total_successes / total_attempts if total_attempts else 0.0
        start = group[0]["timestamp"]
        end = group[-1]["timestamp"]
        incidents.append(
            {
                "incident_id": f"payment-success-{group[0]['country']}-{group[0]['device']}-{start.isoformat()}",
                "metric": "payment_success_rate",
                "country": group[0]["country"],
                "device": group[0]["device"],
                "start_timestamp": start.isoformat(),
                "end_timestamp": end.isoformat(),
                "hours_affected": len(group),
                "baseline_payment_success_rate": baseline_rate,
                "current_payment_success_rate": current_rate,
                "drop_percentage_points": round((baseline_rate - current_rate) * 100, 1),
                "visitors": sum(item["visitors"] for item in group),
                "checkout_attempts": total_attempts,
                "successful_payments": total_successes,
                "orders": sum(item["orders"] for item in group),
                "revenue_eur": round(sum(item["revenue"] for item in group), 2),
            }
        )
    return incidents
