from src.db import load_synthetic_data_to_duckdb
from src.seed_data import generate_synthetic_data
from src.what_if import simulate_brokerage_recovery


def setup_module():
    generate_synthetic_data()
    load_synthetic_data_to_duckdb()


def test_simulate_brokerage_recovery_outputs_impacts():
    result = simulate_brokerage_recovery("2025-09", trade_volume_change_pct=0.05)
    assert "revenue_impact" in result
    assert "profit_impact" in result
    assert result["simulated_trade_volume"] > result["base_trade_volume"]


def test_commission_rate_bp_changes_rate():
    result = simulate_brokerage_recovery("2025-09", commission_rate_change_bp=-1.0)
    assert result["simulated_commission_rate"] < result["base_commission_rate"]
