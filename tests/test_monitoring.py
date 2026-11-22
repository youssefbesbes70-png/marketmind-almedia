import pandas as pd
import pytest

from monitoring.detector import detect_payment_incidents
from simulator import generate_data


@pytest.fixture(scope="module")
def data():
    return generate_data(seed=42)


def test_detection_ignores_changed_and_removed_scenario_labels(data):
    # With seven required points, excluding even one labeled baseline hour changes the result.
    settings = {"min_baseline_points": 7}
    expected = detect_payment_incidents(data, **settings)
    assert [(incident["country"], incident["device"], incident["hours_affected"])
            for incident in expected] == [("DE", "Android", 5)]
    assert detect_payment_incidents(data.assign(scenario="payment_failure"), **settings) == expected
    assert detect_payment_incidents(data.drop(columns="scenario"), **settings) == expected


@pytest.mark.parametrize("column", ["checkout_attempts", "payment_success_rate", "revenue"])
def test_null_numeric_row_is_skipped(data, column):
    failure = data["scenario"].eq("payment_failure")
    damaged = data.copy()
    damaged.loc[data.index[failure][0], column] = None
    incidents = detect_payment_incidents(damaged)
    assert len(incidents) == 1
    assert incidents[0]["hours_affected"] == 4


def test_missing_hour_is_not_counted_as_an_observed_alert(data):
    missing_index = data.index[data["scenario"].eq("payment_failure")][2]
    incidents = detect_payment_incidents(data.drop(index=missing_index))
    assert [incident["hours_affected"] for incident in incidents] == [2, 2]


def test_missing_or_unusable_baseline_does_not_generate_an_alert(data):
    recent = data.loc[data["timestamp"].dt.day >= 12].copy()
    assert detect_payment_incidents(recent) == []
    recent.loc[recent["timestamp"].dt.day < 14, "payment_success_rate"] = pd.NA
    assert detect_payment_incidents(recent, min_baseline_points=1) == []


def test_expected_overnight_traffic_does_not_generate_an_alert(data):
    overnight = data.loc[data["timestamp"].dt.day <= 8]
    assert overnight["scenario"].eq("expected_overnight").sum() == 30
    assert detect_payment_incidents(overnight.drop(columns="scenario")) == []
