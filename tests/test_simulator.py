import pandas as pd
import pytest

from simulator import generate_data


@pytest.fixture
def data():
    return generate_data()


def test_schema(data):
    assert isinstance(data, pd.DataFrame)
    assert list(data.columns) == [
        "timestamp", "country", "device", "visitors", "checkout_attempts",
        "successful_payments", "payment_success_rate", "orders",
        "average_order_value", "revenue", "scenario",
    ]


def test_hourly_coverage(data):
    assert len(data) == 14 * 24 * 2 * 3
    expected_segments = {
        (country, device)
        for country in ("DE", "FR")
        for device in ("Android", "iOS", "Desktop")
    }
    assert set(zip(data["country"], data["device"])) == expected_segments
    assert not data.duplicated(["timestamp", "country", "device"]).any()
    hours = data["timestamp"].drop_duplicates().sort_values()
    assert hours.dt.tz is not None
    assert len(hours) == 14 * 24
    assert (hours.diff().dropna() == pd.Timedelta(hours=1)).all()
    assert (data.groupby("timestamp").size() == 6).all()


def test_metric_formulas_and_counts(data):
    counts = ["visitors", "checkout_attempts", "successful_payments", "orders"]
    for column in counts:
        assert pd.api.types.is_integer_dtype(data[column])
        assert (data[column] >= 0).all()
    attempts = data["checkout_attempts"]
    payments = data["successful_payments"]
    assert (payments <= attempts).all()
    assert (attempts <= data["visitors"]).all()
    assert (data["orders"] == payments).all()
    expected_rate = payments / attempts.where(attempts > 0, 1)
    assert (data["payment_success_rate"] == expected_rate).all()
    assert (data["revenue"] == data["orders"] * data["average_order_value"]).all()


def test_scenarios(data):
    assert set(data["scenario"]) == {"normal", "payment_failure", "expected_overnight"}

    failure = data[data["scenario"] == "payment_failure"]
    assert set(zip(failure["country"], failure["device"])) == {("DE", "Android")}
    assert (failure["timestamp"].dt.date == data["timestamp"].max().date()).all()
    assert list(failure["timestamp"].dt.hour) == [17, 18, 19, 20, 21]
    assert (failure["payment_success_rate"] < 0.55).all()
    other_segments = data[
        data["timestamp"].isin(failure["timestamp"]) & (data["scenario"] == "normal")
    ]
    assert (other_segments["payment_success_rate"] > 0.85).all()

    overnight = data[data["scenario"] == "expected_overnight"]
    nights = overnight["timestamp"].drop_duplicates()
    assert len(nights) == 5
    assert list(nights.dt.hour) == [1, 2, 3, 4, 5]
    assert nights.dt.date.nunique() == 1
    assert len(overnight) == 5 * 6

    # Compare the same segments and hours on the previous night.
    previous_night = data[
        data["timestamp"].isin(nights - pd.Timedelta(days=1))
    ]
    assert (overnight["visitors"].to_numpy() < previous_night["visitors"].to_numpy()).all()
    assert overnight["successful_payments"].sum() / overnight["checkout_attempts"].sum() > 0.90


def test_reproducibility(data):
    pd.testing.assert_frame_equal(data, generate_data(seed=42))
    assert not data.equals(generate_data(seed=43))
