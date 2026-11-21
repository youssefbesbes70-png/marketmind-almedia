# MarketMind simulator and metric graph

These modules provide mock marketplace data and describe how its metrics relate. Run the commands and Python examples from the `marketmind` folder.

## Install and test

The pinned dependencies were tested with Python 3.14.3. On Windows in PowerShell, create a local environment if you need one, then install the dependencies and run the tests.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

On macOS or Linux, use `python3.14 -m venv .venv` and replace `.\.venv\Scripts\python.exe` with `./.venv/bin/python`. The dependencies include pandas for data, NetworkX for the graph, tzdata for the Berlin time zone, and pytest for tests.

## Data and scenarios

`generate_data(seed=42)` returns 2,016 rows for November 1–14, 2026. Each row describes one hour, country, and device. There are six rows per hour across Germany and France and three device types. The checked-in sample is [data/sample_marketplace.csv](data/sample_marketplace.csv).

| Column | Meaning |
| --- | --- |
| `timestamp` | Start of the hour in the Europe/Berlin time zone. The CSV stores timestamps with their UTC offset. |
| `country` | `DE` or `FR`. |
| `device` | `Android`, `iOS`, or `Desktop`. |
| `visitors` | Number of visitors. |
| `checkout_attempts` | Number of checkout attempts. |
| `successful_payments` | Number of successful payments. |
| `payment_success_rate` | Successful payments divided by checkout attempts, or 0 if there were no attempts. |
| `orders` | Number of orders, one per successful payment. |
| `average_order_value` | Average order value in euros, or 0 if there were no orders. |
| `revenue` | Orders multiplied by average order value, in euros. |
| `scenario` | Simulator-provided label for checking monitoring results. |

| Scenario | Seed-42 rows | What happens |
| --- | ---: | --- |
| `normal` | 1,981 | Regular traffic patterns and payment behavior. |
| `expected_overnight` | 30 | An expected traffic dip from 01:00 through 05:00 on November 8 across all six segments. |
| `payment_failure` | 5 | A drop in payment success from 17:00 through 21:00 on November 14 for Germany on Android. |

To regenerate the CSV from PowerShell, run this from `marketmind`.

```powershell
.\.venv\Scripts\python.exe -c "from simulator import generate_data; generate_data(seed=42).to_csv('data/sample_marketplace.csv', index=False, lineterminator=chr(10))"
```

When loading the CSV with pandas, use `pd.read_csv("data/sample_marketplace.csv", parse_dates=["timestamp"])` to read timestamps as datetimes.

## Public Python API

| Import from | Function signature | Behavior |
| --- | --- | --- |
| `simulator` | `generate_data(seed: int = 42) -> pandas.DataFrame` | Returns a fresh table. The same seed reproduces the same mock data in the tested environment. |
| `graph` | `build_graph() -> networkx.DiGraph` | Returns a fresh graph with seven built-in metrics. |
| `graph` | `get_dependencies(graph: networkx.DiGraph, metric_name: str) -> list[str]` | Returns the immediate upstream names, including funnel influences. Does not mutate the graph. An unknown name raises `networkx.NetworkXError`. |
| `graph` | `validate_graph(graph: networkx.DiGraph) -> None` | Returns `None` on success and raises `ValueError` for invalid nodes, formulas, edges, or cycles. Does not mutate the graph. |
| `graph` | `add_metric(graph: networkx.DiGraph, definition: dict) -> None` | Adds a node and its incoming `formula_input` edges **in place**. Invalid definitions or graphs raise `ValueError` before any change. |
| `graph` | `evaluate_metric(graph: networkx.DiGraph, metric_name: str, values: Mapping[str, Real]) -> Real \| None` | Evaluates one row using numeric values supplied for built-in metrics. Division by zero returns `None`. An invalid graph or missing input raises `ValueError`. Does not mutate the graph or row. |

Edges point from upstream to downstream. `formula_input` identifies an arithmetic input, `equality` connects equivalent counts, and `funnel_relation` represents a possible influence. Each node has a name, description, unit, formula (or `None`), and dimensions.

A derived metric definition contains `name`, `description`, `unit`, `formula`, and `dimensions`. The formula parser supports metric names, numbers, parentheses, and `+`, `-`, `*`, and `/`. Derived metrics use both `country` and `device` and operate on one row at a time. SQL, aggregation, and unit checking are outside this API.

## Integration example

```python
from graph import add_metric, build_graph, evaluate_metric, get_dependencies, validate_graph
from simulator import generate_data

data = generate_data(seed=42)
graph = build_graph()

add_metric(graph, {
    "name": "checkout_conversion_rate",
    "description": "Checkout attempts per visitor.",
    "unit": "ratio",
    "formula": "checkout_attempts / visitors",
    "dimensions": ["country", "device"],
})
validate_graph(graph)

row = data.loc[data["visitors"] > 0].iloc[0].to_dict()
print(get_dependencies(graph, "checkout_conversion_rate"))
# ['checkout_attempts', 'visitors']
print(evaluate_metric(graph, "checkout_conversion_rate", row))
# 0.07727272727272727
```

The derived metric lives in the graph. The original data table and CSV keep their 11 columns.
