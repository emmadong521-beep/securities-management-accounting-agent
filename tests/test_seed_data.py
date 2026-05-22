import pandas as pd

from src.config import SYNTHETIC_DIR
from src.db import load_synthetic_data_to_duckdb
from src.seed_data import generate_synthetic_data
from src.schema import CORE_TABLES


def test_core_tables_non_empty():
    counts = generate_synthetic_data()
    load_synthetic_data_to_duckdb()
    for table in CORE_TABLES:
        assert counts[table] > 0, table


def test_budget_and_actual_dimensions_match():
    generate_synthetic_data()
    budget = pd.read_csv(SYNTHETIC_DIR / "monthly_budget.csv")
    actual = pd.read_csv(SYNTHETIC_DIR / "monthly_actual.csv")
    keys = ["period", "biz_line_id", "branch_id", "product_type", "customer_segment"]
    assert set(map(tuple, budget[keys].values)) == set(map(tuple, actual[keys].values))
