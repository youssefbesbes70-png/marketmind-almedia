"""Generate hourly mock marketplace metrics for Germany and France."""

from random import Random

import pandas as pd


# Traffic rises through the morning, dips after lunch, and peaks in the evening.
HOURLY_TRAFFIC = (
    0.32, 0.23, 0.17, 0.14, 0.15, 0.21, 0.34, 0.52,
    0.69, 0.81, 0.90, 0.98, 1.05, 1.02, 0.94, 0.92,
    0.96, 1.06, 1.19, 1.30, 1.36, 1.24, 0.93, 0.58,
)
COUNTRY_TRAFFIC = {"DE": 1500, "FR": 1100}
DEVICE_SHARE = {"Android": 0.45, "iOS": 0.35, "Desktop": 0.20}


def generate_data(seed: int = 42) -> pd.DataFrame:
    """Return 14 days of hourly metrics, with order values in euros."""
    rng = Random(seed)
    timestamps = pd.date_range(
        "2026-11-01", periods=14 * 24, freq="h", tz="Europe/Berlin"
    )
    final_day = timestamps[-1].date()
    rows = []

    for timestamp in timestamps:
        hour = timestamp.hour
        traffic = HOURLY_TRAFFIC[hour]
        expected_overnight = timestamp.day == 8 and 1 <= hour < 6
        if expected_overnight:
            traffic *= 0.60

        for country, base_visitors in COUNTRY_TRAFFIC.items():
            for device, share in DEVICE_SHARE.items():
                visitors = round(base_visitors * share * traffic * rng.uniform(0.94, 1.06))
                attempts = round(visitors * rng.uniform(0.075, 0.095))
                payment_probability = rng.uniform(0.94, 0.98)
                scenario = "expected_overnight" if expected_overnight else "normal"

                if timestamp.date() == final_day and 17 <= hour < 22:
                    if country == "DE" and device == "Android":
                        payment_probability *= 0.45
                        scenario = "payment_failure"

                payments = round(attempts * payment_probability)
                average_order_value = round(rng.uniform(52, 64), 2) if payments else 0.0
                rows.append({
                    "timestamp": timestamp,
                    "country": country,
                    "device": device,
                    "visitors": visitors,
                    "checkout_attempts": attempts,
                    "successful_payments": payments,
                    "payment_success_rate": payments / attempts if attempts else 0.0,
                    "orders": payments,
                    "average_order_value": average_order_value,
                    "revenue": payments * average_order_value,
                    "scenario": scenario,
                })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(generate_data().head().to_string(index=False))
