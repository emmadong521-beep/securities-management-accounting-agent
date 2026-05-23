from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


def _enabled() -> bool:
    return os.getenv("USE_RECON_VALIDATED_DATA", "false").strip().lower() == "true"


def _output_dir() -> Path:
    return Path(os.getenv("RECON_PROJECT_OUTPUT_DIR", "/path/to/securities-month-end-recon-agent/data/output"))


def load_validated_actual_revenue() -> pd.DataFrame | None:
    if not _enabled():
        return None
    path = _output_dir() / "validated_actual_revenue.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def load_validated_allocated_expense() -> pd.DataFrame | None:
    if not _enabled():
        return None
    path = _output_dir() / "validated_allocated_expense.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def get_recon_data_status() -> dict:
    enabled = _enabled()
    output_dir = _output_dir()
    revenue_file = output_dir / "validated_actual_revenue.csv"
    expense_file = output_dir / "validated_allocated_expense.csv"
    revenue_exists = revenue_file.exists()
    expense_exists = expense_file.exists()
    available = enabled and revenue_exists and expense_exists
    if not enabled:
        message = "USE_RECON_VALIDATED_DATA=false，当前使用项目二内置合成数据。"
        source = "项目二内置合成数据"
    elif available:
        message = "已读取项目一导出的可信月结数据。"
        source = "项目一导出的可信月结数据"
    else:
        message = "未找到可信月结数据，已使用项目二合成数据。"
        source = "项目二内置合成数据"
    return {
        "use_recon_validated_data": enabled,
        "configured_path": str(output_dir),
        "revenue_file_exists": revenue_exists,
        "expense_file_exists": expense_exists,
        "available": available,
        "source": source,
        "message": message,
    }
