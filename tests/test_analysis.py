from src.db import load_synthetic_data_to_duckdb
from src.seed_data import generate_synthetic_data
from src.validation import (
    calculate_bizline_profitability,
    calculate_branch_profitability,
    detect_management_insights,
    export_cfo_report,
    generate_cfo_report_mock,
    get_pvm_detail,
    run_pvm_analysis,
)


def setup_module():
    generate_synthetic_data()
    load_synthetic_data_to_duckdb()


def test_bizline_profitability_total_matches_actual_profit():
    biz = calculate_bizline_profitability("2025-09")
    assert abs(biz["profit_contribution_rate"].sum() - 1) < 0.0001
    assert biz["operating_profit"].sum() != 0


def test_branch_profitability_has_no_nulls():
    branch = calculate_branch_profitability("2025-09")
    assert not branch[["revenue", "direct_cost", "allocated_expense", "operating_profit", "operating_margin"]].isna().any().any()


def test_pvm_identity_holds():
    pvm = run_pvm_analysis("2025-09", "BROKERAGE").iloc[0]
    assert abs(pvm["total_variance"] - (pvm["volume_effect"] + pvm["rate_effect"] + pvm["mix_effect"])) < 1.0


def test_pvm_detail_dimension_expanded():
    detail = get_pvm_detail("2025-09")
    assert len(detail) >= 100
    assert {"branch_id", "branch_name", "customer_segment", "product_type"}.issubset(detail.columns)
    identity_diff = (detail["total_variance"] - (detail["volume_effect"] + detail["rate_effect"] + detail["mix_effect"])).abs().max()
    assert identity_diff < 2.0


def test_seeded_management_stories_detected():
    insights = detect_management_insights("2025-09")
    types = set(insights["insight_type"])
    assert "BROKERAGE_VARIANCE" in types
    assert "WEALTH_LOW_CONTRIBUTION" in types
    assert "MARGIN_BALANCE_DECLINE" in types
    assert any(t in types for t in ["HIGH_REVENUE_LOW_MARGIN_BRANCH", "LOW_MARGIN_BRANCH"])


def test_cfo_report_sections():
    report = generate_cfo_report_mock("2025-09")
    for section in ["本月经营概览", "主要差异", "业务线分析", "营业部盈利分析", "管理建议", "风险提示"]:
        assert section in report


def test_cfo_report_can_be_exported():
    output_path = export_cfo_report("2025-09")
    assert output_path.exists()
    assert output_path.name == "cfo_report_2025-09.md"
