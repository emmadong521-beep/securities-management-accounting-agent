from src.schema import CHART_OF_ACCOUNTS, TABLE_COLUMNS


def test_chart_of_accounts_consistent():
    assert any(a["account_code"] == "1002" for a in CHART_OF_ACCOUNTS)
    assert any(a["account_code"] == "6021" for a in CHART_OF_ACCOUNTS)


def test_required_tables_registered():
    for table in ["monthly_budget", "monthly_actual", "brokerage_kpi", "branch_profitability", "bizline_profitability", "pvm_analysis_result", "management_insight"]:
        assert table in TABLE_COLUMNS
