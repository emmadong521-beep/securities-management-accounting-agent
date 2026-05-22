from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .config import DB_PATH, OUTPUT_DIR
from .db import load_synthetic_data_to_duckdb
from .load_audit_report import load_audit_metrics
from .schema import CORE_TABLES
from .validation import detect_management_insights, get_pvm_detail


PRIMARY_KEYS = {
    "chart_of_accounts": ["account_code"],
    "biz_line_master": ["biz_line_id"],
    "branch_master": ["branch_id"],
    "customer_segment_master": ["segment_id"],
    "product_master": ["product_id"],
    "monthly_budget": ["period", "biz_line_id", "branch_id", "product_type", "customer_segment"],
    "monthly_actual": ["period", "biz_line_id", "branch_id", "product_type", "customer_segment"],
    "brokerage_kpi": ["period", "branch_id", "customer_segment", "product_type"],
    "branch_expense": ["period", "branch_id"],
    "branch_profitability": ["period", "branch_id"],
    "bizline_profitability": ["period", "biz_line_id"],
    "pvm_analysis_result": ["period", "branch_id", "customer_segment", "product_type"],
    "market_benchmark": ["period"],
}

AMOUNT_FIELDS = {
    "monthly_budget": ["budget_revenue", "budget_direct_cost", "budget_allocated_expense", "budget_profit", "budget_trade_volume"],
    "monthly_actual": ["actual_revenue", "actual_direct_cost", "actual_allocated_expense", "actual_profit", "actual_trade_volume"],
    "brokerage_kpi": ["trade_volume", "avg_commission_rate", "commission_income"],
    "branch_expense": ["total_expense"],
    "branch_profitability": ["revenue", "allocated_expense", "operating_profit"],
    "bizline_profitability": ["revenue", "allocated_expense", "operating_profit"],
    "pvm_analysis_result": ["budget_revenue", "actual_revenue", "total_variance", "volume_effect", "rate_effect", "mix_effect"],
    "management_insight": ["financial_impact"],
}

EXPECTED_INSIGHTS = {"BROKERAGE_VARIANCE", "WEALTH_LOW_CONTRIBUTION", "MARGIN_BALANCE_DECLINE"}


def _table(con: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    return con.execute(f"SELECT * FROM {table}").fetchdf()


def _status_from_checks(checks: list[dict[str, Any]]) -> str:
    if any(c["status"] == "FAIL" for c in checks):
        return "FAIL"
    if any(c["status"] == "WARNING" for c in checks):
        return "WARNING"
    return "PASS"


def _write_report(report: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "data_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 数据质量自检报告",
        "",
        f"结论：{report['status']}",
        "",
        "## 表行数",
    ]
    for table, count in report["row_counts"].items():
        lines.append(f"- {table}: {count}")
    lines.extend(["", "## 检查项"])
    for check in report["checks"]:
        lines.append(f"- [{check['status']}] {check['name']}: {check['detail']}")
    lines.extend(["", "## 校准说明", report["calibration_note"], ""])
    (OUTPUT_DIR / "data_quality_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_data_quality_checks() -> dict[str, Any]:
    load_synthetic_data_to_duckdb()
    con = duckdb.connect(str(DB_PATH))
    try:
        tables = {table: _table(con, table) for table in CORE_TABLES}
    finally:
        con.close()

    checks: list[dict[str, Any]] = []
    row_counts = {table: int(len(df)) for table, df in tables.items()}
    for table, count in row_counts.items():
        checks.append({"name": f"{table} 非空", "status": "PASS" if count > 0 else "FAIL", "detail": f"{count} rows"})

    for table, keys in PRIMARY_KEYS.items():
        df = tables[table]
        duplicate_count = int(df.duplicated(keys).sum()) if all(k in df for k in keys) else len(df)
        checks.append({
            "name": f"{table} 主键唯一",
            "status": "PASS" if duplicate_count == 0 else "FAIL",
            "detail": f"duplicate_count={duplicate_count}, keys={keys}",
        })

    budget = tables["monthly_budget"]
    actual = tables["monthly_actual"]
    keys = ["period", "biz_line_id", "branch_id", "product_type", "customer_segment"]
    budget_keys = set(map(tuple, budget[keys].astype(str).values))
    actual_keys = set(map(tuple, actual[keys].astype(str).values))
    checks.append({
        "name": "预算与实际维度一致",
        "status": "PASS" if budget_keys == actual_keys else "FAIL",
        "detail": f"budget_only={len(budget_keys - actual_keys)}, actual_only={len(actual_keys - budget_keys)}",
    })

    fk_checks = [
        ("monthly_budget.branch_id", budget["branch_id"], tables["branch_master"]["branch_id"]),
        ("monthly_actual.branch_id", actual["branch_id"], tables["branch_master"]["branch_id"]),
        ("monthly_budget.biz_line_id", budget["biz_line_id"], tables["biz_line_master"]["biz_line_id"]),
        ("product_master.biz_line_id", tables["product_master"]["biz_line_id"], tables["biz_line_master"]["biz_line_id"]),
        ("brokerage_kpi.branch_id", tables["brokerage_kpi"]["branch_id"], tables["branch_master"]["branch_id"]),
    ]
    for name, child, parent in fk_checks:
        missing = int((~child.dropna().isin(parent.dropna())).sum())
        checks.append({"name": f"{name} 外键完整", "status": "PASS" if missing == 0 else "FAIL", "detail": f"missing={missing}"})

    for table, fields in AMOUNT_FIELDS.items():
        df = tables[table]
        for field in fields:
            nulls = int(df[field].isna().sum())
            checks.append({"name": f"{table}.{field} 空值", "status": "PASS" if nulls == 0 else "FAIL", "detail": f"nulls={nulls}"})

    profit_diff = abs(float(actual["actual_profit"].sum() - (actual["actual_revenue"].sum() - actual["actual_direct_cost"].sum() - actual["actual_allocated_expense"].sum())))
    checks.append({
        "name": "实际利润金额勾稽",
        "status": "PASS" if profit_diff < 20 else "FAIL",
        "detail": f"diff={profit_diff:.2f}",
    })

    pvm = tables["pvm_analysis_result"]
    pvm_identity_diff = (pvm["total_variance"] - (pvm["volume_effect"] + pvm["rate_effect"] + pvm["mix_effect"])).abs().max()
    checks.append({
        "name": "PVM 恒等关系",
        "status": "PASS" if float(pvm_identity_diff) < 2 else "FAIL",
        "detail": f"max_diff={float(pvm_identity_diff):.2f}, rows={len(pvm)}",
    })

    pvm_detail_rows = len(get_pvm_detail("2025-09"))
    checks.append({
        "name": "PVM 明细维度",
        "status": "PASS" if row_counts["pvm_analysis_result"] >= 100 and pvm_detail_rows > 0 else "FAIL",
        "detail": f"pvm_rows={row_counts['pvm_analysis_result']}, selected_period_rows={pvm_detail_rows}",
    })

    insights = detect_management_insights("2025-09")
    detected_insights = set(insights["insight_type"].dropna().astype(str))
    missing = sorted(EXPECTED_INSIGHTS - detected_insights)
    checks.append({
        "name": "经营故事检测",
        "status": "PASS" if not missing else "FAIL",
        "detail": f"detected={sorted(detected_insights)}, missing={missing}",
    })

    metrics = load_audit_metrics()
    actual_brokerage = float(actual[actual["biz_line_id"] == "BROKERAGE"]["actual_revenue"].sum())
    public_brokerage = float(metrics["business_structure"]["证券经纪业务净收入"])
    ratio = actual_brokerage / public_brokerage if public_brokerage else 0.0
    checks.append({
        "name": "公开指标规模校准",
        "status": "PASS" if 0.65 <= ratio <= 1.05 else "WARNING",
        "detail": f"synthetic_brokerage={actual_brokerage:,.2f}, public_metric={public_brokerage:,.2f}, ratio={ratio:.2%}",
    })

    report = {
        "status": _status_from_checks(checks),
        "row_counts": row_counts,
        "checks": checks,
        "calibration_note": "审计报告公开披露指标仅用于营业总收入、手续费及佣金净收入、业务及管理费、净利润和业务结构等汇总规模校准；预算、实际、KPI 和管理洞察明细均为合成数据。",
    }
    _write_report(report)
    return report


if __name__ == "__main__":
    result = run_data_quality_checks()
    print(json.dumps({"status": result["status"], "output": str(OUTPUT_DIR / "data_quality_report.md")}, ensure_ascii=False, indent=2))
