from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SYNTHETIC_DIR
from .validation import calculate_branch_profitability


def _read_csv(name: str) -> pd.DataFrame:
    path = SYNTHETIC_DIR / f"{name}.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _branch_names() -> pd.DataFrame:
    master = _read_csv("branch_master")
    if master.empty:
        return pd.DataFrame(columns=["branch_id", "branch_name", "city"])
    return master[["branch_id", "branch_name", "city"]]


def calculate_revenue_margin_rank_gap(period: str) -> pd.DataFrame:
    branch = calculate_branch_profitability(period).copy()
    expenses = _read_csv("branch_expense")
    kpi = _read_csv("brokerage_kpi")
    branch = branch.merge(_branch_names(), on="branch_id", how="left")
    branch["revenue_rank"] = branch["revenue"].rank(ascending=False, method="first").astype(int)
    branch["margin_rank"] = branch["operating_margin"].rank(ascending=False, method="first").astype(int)
    branch["rank_gap"] = branch["revenue_rank"] - branch["margin_rank"]
    branch["allocated_expense_ratio"] = branch["allocated_expense"] / branch["revenue"].replace(0, np.nan)

    if not expenses.empty:
        exp = expenses[expenses["period"] == period].copy()
        branch = branch.merge(
            exp[
                [
                    "branch_id",
                    "salary_expense",
                    "rent_expense",
                    "marketing_expense",
                    "it_allocated_expense",
                    "market_data_allocated_expense",
                    "hq_allocated_expense",
                    "total_expense",
                ]
            ],
            on="branch_id",
            how="left",
        )
    if not kpi.empty:
        k = kpi[kpi["period"] == period].copy()
        avg = (
            k.groupby("branch_id", as_index=False)
            .agg(trade_volume=("trade_volume", "sum"), commission_income=("commission_income", "sum"))
        )
        avg["avg_commission_rate"] = avg["commission_income"] / avg["trade_volume"].replace(0, np.nan)
        mix = (
            k.pivot_table(index="branch_id", columns="customer_segment", values="trade_volume", aggfunc="sum", fill_value=0)
            .reset_index()
        )
        for segment in ["RETAIL", "HNW", "INSTITUTION"]:
            if segment not in mix.columns:
                mix[segment] = 0.0
        mix["total_mix_volume"] = mix[["RETAIL", "HNW", "INSTITUTION"]].sum(axis=1)
        mix["institution_ratio"] = mix["INSTITUTION"] / mix["total_mix_volume"].replace(0, np.nan)
        mix["customer_mix_summary"] = mix.apply(
            lambda row: f"零售 {row['RETAIL'] / max(row['total_mix_volume'], 1):.1%}，高净值 {row['HNW'] / max(row['total_mix_volume'], 1):.1%}，机构 {row['INSTITUTION'] / max(row['total_mix_volume'], 1):.1%}",
            axis=1,
        )
        branch = branch.merge(avg[["branch_id", "trade_volume", "avg_commission_rate"]], on="branch_id", how="left")
        branch = branch.merge(mix[["branch_id", "institution_ratio", "customer_mix_summary"]], on="branch_id", how="left")

    branch["avg_commission_rate"] = branch["avg_commission_rate"].fillna(branch["avg_commission_rate"].mean())
    branch["institution_ratio"] = branch["institution_ratio"].fillna(0.0)
    branch["customer_mix_summary"] = branch["customer_mix_summary"].fillna("客户结构数据不足")
    return branch.round(6)


def _reason_tags(row: pd.Series, avg_expense_ratio: float, avg_commission_rate: float) -> list[str]:
    tags: list[str] = []
    if float(row.get("allocated_expense_ratio", 0)) > avg_expense_ratio:
        tags.append("HIGH_HQ_ALLOCATION")
    if float(row.get("avg_commission_rate", 0)) < avg_commission_rate:
        tags.append("LOW_COMMISSION_RATE")
    if float(row.get("institution_ratio", 0)) > 0.45:
        tags.append("HIGH_INSTITUTION_CLIENT_RATIO")
    if float(row.get("it_allocated_expense", 0)) + float(row.get("market_data_allocated_expense", 0)) > float(row.get("total_expense", 1)) * 0.35:
        tags.append("HIGH_SYSTEM_COST")
    if float(row.get("marketing_expense", 0)) > float(row.get("total_expense", 1)) * 0.25:
        tags.append("HIGH_MARKETING_EXPENSE")
    if float(row.get("operating_margin", 0)) < 0.2:
        tags.append("LOW_OPERATING_MARGIN")
    return tags or ["LOW_OPERATING_MARGIN"]


def detect_high_revenue_low_profit_branches(period: str) -> pd.DataFrame:
    df = calculate_revenue_margin_rank_gap(period)
    if df.empty:
        return df
    total = len(df)
    top_revenue_cutoff = max(int(np.ceil(total * 0.3)), 1)
    low_margin_cutoff = int(np.floor(total * 0.5))
    avg_expense_ratio = float(df["allocated_expense_ratio"].mean())
    avg_commission_rate = float(df["avg_commission_rate"].mean())
    df["reason_tags"] = df.apply(lambda row: "|".join(_reason_tags(row, avg_expense_ratio, avg_commission_rate)), axis=1)
    flagged = df[
        (df["revenue_rank"] <= top_revenue_cutoff)
        & (
            (df["margin_rank"] > low_margin_cutoff)
            | (df["allocated_expense_ratio"] > avg_expense_ratio)
            | (df["avg_commission_rate"] < avg_commission_rate)
        )
    ].copy()
    return flagged.sort_values(["revenue_rank", "margin_rank"]).reset_index(drop=True)


def explain_high_revenue_low_profit_branch(period: str, branch_id: str) -> dict:
    full = calculate_revenue_margin_rank_gap(period)
    matches = full[full["branch_id"] == branch_id]
    if matches.empty:
        raise ValueError(f"Unknown branch_id: {branch_id}")
    row = matches.iloc[0]
    avg_expense_ratio = float(full["allocated_expense_ratio"].mean())
    avg_commission_rate = float(full["avg_commission_rate"].mean())
    tags = _reason_tags(row, avg_expense_ratio, avg_commission_rate)
    label = row.get("branch_name") or row.get("city") or branch_id
    explanation = (
        f"{label} 收入排名第 {int(row['revenue_rank'])}，但经营利润率排名第 {int(row['margin_rank'])}。"
        f"分摊费用占收入比 {float(row['allocated_expense_ratio']):.2%}，"
        f"平均佣金率 {float(row['avg_commission_rate']):.5%}，客户结构为 {row['customer_mix_summary']}。"
        f"主要原因标签：{', '.join(tags)}。"
    )
    return {
        "period": period,
        "branch_id": branch_id,
        "branch_name": str(label),
        "revenue": float(row["revenue"]),
        "revenue_rank": int(row["revenue_rank"]),
        "operating_margin": float(row["operating_margin"]),
        "margin_rank": int(row["margin_rank"]),
        "allocated_expense_ratio": float(row["allocated_expense_ratio"]),
        "avg_commission_rate": float(row["avg_commission_rate"]),
        "trade_volume": float(row.get("trade_volume", 0.0)),
        "customer_mix_summary": str(row["customer_mix_summary"]),
        "reason_tags": tags,
        "explanation": explanation,
        "recommendation": "复核高频机构客户定价、IT和总部费用分摊规则，并按客户资源占用调整服务政策。",
    }
