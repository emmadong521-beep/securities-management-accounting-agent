from src.db import load_synthetic_data_to_duckdb
from src.profitability_insights import (
    calculate_revenue_margin_rank_gap,
    detect_high_revenue_low_profit_branches,
    explain_high_revenue_low_profit_branch,
)
from src.seed_data import generate_synthetic_data


def setup_module():
    generate_synthetic_data()
    load_synthetic_data_to_duckdb()


def test_high_revenue_low_profit_detection_outputs_rows():
    rows = detect_high_revenue_low_profit_branches("2025-09")
    assert not rows.empty
    assert "rank_gap" in rows.columns
    assert "reason_tags" in rows.columns


def test_rank_gap_and_explain_are_specific():
    gap = calculate_revenue_margin_rank_gap("2025-09")
    assert "rank_gap" in gap.columns
    branch_id = detect_high_revenue_low_profit_branches("2025-09").iloc[0]["branch_id"]
    detail = explain_high_revenue_low_profit_branch("2025-09", branch_id)
    assert detail["reason_tags"]
    assert detail["explanation"]
    assert detail["recommendation"]
