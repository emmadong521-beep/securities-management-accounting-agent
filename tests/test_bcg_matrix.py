from src.agent import run_management_accounting_agent_with_trace
from src.bcg_matrix import (
    QUADRANTS,
    calculate_bcg_matrix,
    classify_bcg_quadrant,
    explain_bcg_entity,
    generate_bcg_summary,
)
from src.db import load_synthetic_data_to_duckdb
from src.seed_data import generate_synthetic_data


def setup_module():
    generate_synthetic_data()
    load_synthetic_data_to_duckdb()


def test_classify_bcg_quadrant():
    assert classify_bcg_quadrant(0.2, 0.3, 0.1, 0.2) == "增长明星"
    assert classify_bcg_quadrant(0.05, 0.3, 0.1, 0.2) == "现金牛"
    assert classify_bcg_quadrant(0.2, 0.1, 0.1, 0.2) == "潜力观察"
    assert classify_bcg_quadrant(0.05, 0.1, 0.1, 0.2) == "低效待优化"


def test_calculate_bcg_matrix_bizline_not_empty():
    matrix = calculate_bcg_matrix("2025-09", entity_type="biz_line")

    assert not matrix.empty
    assert "quadrant" in matrix.columns
    assert {"revenue_growth_pct", "operating_margin", "x_value", "y_value"}.issubset(matrix.columns)


def test_calculate_bcg_matrix_branch_not_empty():
    matrix = calculate_bcg_matrix("2025-09", entity_type="branch")

    assert not matrix.empty
    assert "quadrant" in matrix.columns
    assert {"allocated_expense_ratio", "budget_variance_rate"}.issubset(matrix.columns)


def test_bcg_quadrant_values_valid():
    matrix = calculate_bcg_matrix("2025-09", entity_type="biz_line")

    assert set(matrix["quadrant"]).issubset(set(QUADRANTS))


def test_generate_bcg_summary_contains_quadrants():
    summary = generate_bcg_summary("2025-09", entity_type="biz_line")

    assert "quadrant_counts" in summary
    assert set(summary["quadrant_counts"]).issubset(set(QUADRANTS))
    assert "recommended_actions" in summary


def test_explain_bcg_entity_returns_reason_and_action():
    matrix = calculate_bcg_matrix("2025-09", entity_type="biz_line")
    explanation = explain_bcg_entity(matrix.iloc[0])

    assert explanation["reason"]
    assert explanation["recommended_action"]
    assert explanation["risk_note"]


def test_agent_bcg_task_trace():
    trace = run_management_accounting_agent_with_trace(
        "请用 BCG 矩阵分析 2025-09 各业务线经营状态。",
        period="2025-09",
    )
    tool_names = {step.tool_name for step in trace.steps if step.tool_name}

    assert trace.steps
    assert {"calculate_bcg_matrix", "generate_bcg_summary"} & tool_names
    assert trace.final_answer
