import pandas as pd

from src import recon_data_loader


def test_recon_loader_falls_back_when_path_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_RECON_VALIDATED_DATA", "true")
    monkeypatch.setenv("RECON_PROJECT_OUTPUT_DIR", str(tmp_path / "missing"))
    assert recon_data_loader.load_validated_actual_revenue() is None
    status = recon_data_loader.get_recon_data_status()
    assert status["available"] is False
    assert "source" in status
    assert "message" in status


def test_recon_loader_reads_mock_csv(monkeypatch, tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    pd.DataFrame({"period": ["2025-09"], "revenue_amount": [100.0]}).to_csv(out / "validated_actual_revenue.csv", index=False)
    pd.DataFrame({"period": ["2025-09"], "allocated_amount": [10.0]}).to_csv(out / "validated_allocated_expense.csv", index=False)
    monkeypatch.setenv("USE_RECON_VALIDATED_DATA", "true")
    monkeypatch.setenv("RECON_PROJECT_OUTPUT_DIR", str(out))
    revenue = recon_data_loader.load_validated_actual_revenue()
    expense = recon_data_loader.load_validated_allocated_expense()
    status = recon_data_loader.get_recon_data_status()
    assert revenue is not None and not revenue.empty
    assert expense is not None and not expense.empty
    assert status["available"] is True
