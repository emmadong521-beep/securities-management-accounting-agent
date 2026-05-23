from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from .agent import run_management_accounting_agent
from .config import OUTPUT_DIR, SYNTHETIC_DIR
from .data_quality import run_data_quality_checks
from .validation import calculate_bizline_profitability, calculate_branch_profitability, detect_management_insights


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _csv_count(name: str) -> int:
    path = SYNTHETIC_DIR / f"{name}.csv"
    return int(len(pd.read_csv(path))) if path.exists() else 0


def _pytest_summary() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"(\d+) passed", output)
    if match and result.returncode == 0:
        return f"{match.group(1)} passed"
    return "not available"


def _agent_step_range() -> str:
    tasks = [
        "请分析 2025-09 公司利润低于预算的主要原因。",
        "经纪业务收入低于预算，是交易量下降还是佣金率下降导致？",
        "为什么深圳营业部收入排名靠前，但经营利润率偏低？",
        "如果经纪业务交易量恢复 5%，收入和利润能改善多少？",
    ]
    counts = [len(run_management_accounting_agent(task, "2025-09", use_llm=False).steps) for task in tasks]
    return f"{min(counts)}-{max(counts)}"


def collect_project_metrics() -> dict[str, Any]:
    quality = run_data_quality_checks()
    bizline = calculate_bizline_profitability("2025-09")
    branch = calculate_branch_profitability("2025-09")
    insights = detect_management_insights("2025-09")
    metrics = {
        "Monthly budget rows": _csv_count("monthly_budget"),
        "Monthly actual rows": _csv_count("monthly_actual"),
        "Brokerage KPI rows": _csv_count("brokerage_kpi"),
        "Branch profitability rows": int(len(branch)),
        "Bizline profitability rows": int(len(bizline)),
        "PVM analysis rows": _csv_count("pvm_analysis_result"),
        "Business lines": _csv_count("biz_line_master"),
        "Branches": _csv_count("branch_master"),
        "Management insight rows": int(len(insights)),
        "Supported analysis scenarios": 5,
        "Agent tool-call steps per demo task": _agent_step_range(),
        "Unit tests": _pytest_summary(),
        "Data quality status": str(quality["status"]),
    }
    return metrics


def _write_outputs(metrics: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "project_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["| Metric | Value |", "|---|---:|"]
    for key, value in metrics.items():
        lines.append(f"| {key} | {value} |")
    (OUTPUT_DIR / "project_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    project_metrics = collect_project_metrics()
    _write_outputs(project_metrics)
    print(json.dumps(project_metrics, ensure_ascii=False, indent=2))
