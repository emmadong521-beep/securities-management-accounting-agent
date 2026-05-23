from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .config import DB_PATH, OUTPUT_DIR
from .db import load_synthetic_data_to_duckdb


def _table(table: str) -> pd.DataFrame:
    if not Path(DB_PATH).exists():
        load_synthetic_data_to_duckdb()
    con = duckdb.connect(str(DB_PATH))
    try:
        return con.execute(f"SELECT * FROM {table}").fetchdf()
    finally:
        con.close()


def _replace_table(table: str, df: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / f"{table}.csv", index=False)
    if Path(DB_PATH).exists():
        con = duckdb.connect(str(DB_PATH))
        try:
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM df")
        finally:
            con.close()


def calculate_bizline_profitability(period: str) -> pd.DataFrame:
    actual = _table("monthly_actual")
    df = actual[actual["period"] == period].groupby(["period", "biz_line_id"], as_index=False).agg(
        revenue=("actual_revenue", "sum"),
        direct_cost=("actual_direct_cost", "sum"),
        allocated_expense=("actual_allocated_expense", "sum"),
        operating_profit=("actual_profit", "sum"),
    )
    df["operating_margin"] = df["operating_profit"] / df["revenue"].replace(0, np.nan)
    total_profit = df["operating_profit"].sum()
    df["profit_contribution_rate"] = df["operating_profit"] / total_profit if total_profit else 0
    df = df.round(4)
    _replace_table("bizline_profitability", df)
    return df


def calculate_branch_profitability(period: str) -> pd.DataFrame:
    actual = _table("monthly_actual")
    df = actual[actual["period"] == period].groupby(["period", "branch_id"], as_index=False).agg(
        revenue=("actual_revenue", "sum"),
        direct_cost=("actual_direct_cost", "sum"),
        allocated_expense=("actual_allocated_expense", "sum"),
        operating_profit=("actual_profit", "sum"),
    )
    df["operating_margin"] = df["operating_profit"] / df["revenue"].replace(0, np.nan)
    df["profit_rank"] = df["operating_profit"].rank(ascending=False, method="first").astype(int)
    df = df.round(4)
    _replace_table("branch_profitability", df)
    return df


def run_brokerage_budget_variance(period: str) -> pd.DataFrame:
    budget = _table("monthly_budget")
    actual = _table("monthly_actual")
    b = budget[(budget["period"] == period) & (budget["biz_line_id"] == "BROKERAGE")]
    a = actual[(actual["period"] == period) & (actual["biz_line_id"] == "BROKERAGE")]
    df = b.merge(a, on=["period", "biz_line_id", "branch_id", "product_type", "customer_segment"], how="inner")
    df["revenue_variance"] = df["actual_revenue"] - df["budget_revenue"]
    df["profit_variance"] = df["actual_profit"] - df["budget_profit"]
    df["trade_volume_variance"] = df["actual_trade_volume"] - df["budget_trade_volume"]
    df["commission_rate_variance"] = df["actual_commission_rate"] - df["budget_commission_rate"]
    return df


def get_pvm_detail(
    period: str,
    branch_id: str | None = None,
    customer_segment: str | None = None,
    product_type: str | None = None,
) -> pd.DataFrame:
    detail = _table("pvm_analysis_result")
    df = detail[detail["period"] == period].copy()
    if branch_id and branch_id != "ALL":
        df = df[df["branch_id"] == branch_id]
    if customer_segment and customer_segment != "ALL":
        df = df[df["customer_segment"] == customer_segment]
    if product_type and product_type != "ALL":
        df = df[df["product_type"] == product_type]
    return df.reset_index(drop=True)


def _aggregate_pvm(df: pd.DataFrame, period: str) -> pd.DataFrame:
    budget_volume = df["budget_trade_volume"].sum()
    actual_volume = df["actual_trade_volume"].sum()
    budget_revenue = df["budget_revenue"].sum()
    actual_revenue = df["actual_revenue"].sum()
    budget_rate = budget_revenue / max(budget_volume, 1.0)
    actual_rate = actual_revenue / max(actual_volume, 1.0)
    total_variance = actual_revenue - budget_revenue
    volume_effect = (actual_volume - budget_volume) * budget_rate
    rate_effect = actual_volume * (actual_rate - budget_rate)
    mix_effect = total_variance - volume_effect - rate_effect
    return pd.DataFrame([{
        "period": period,
        "branch_id": "ALL",
        "branch_name": "全公司",
        "customer_segment": "ALL",
        "product_type": "ALL",
        "budget_revenue": round(budget_revenue, 2),
        "actual_revenue": round(actual_revenue, 2),
        "budget_trade_volume": round(budget_volume, 2),
        "actual_trade_volume": round(actual_volume, 2),
        "budget_commission_rate": round(budget_rate, 8),
        "actual_commission_rate": round(actual_rate, 8),
        "total_variance": round(total_variance, 2),
        "volume_effect": round(volume_effect, 2),
        "rate_effect": round(rate_effect, 2),
        "mix_effect": round(mix_effect, 2),
        "explanation": "经纪佣金收入低于预算，主要由市场交易量下降和平均佣金率下行驱动。",
    }])


def run_pvm_analysis(
    period: str,
    scope: str = "BROKERAGE",
    branch_id: str | None = None,
    customer_segment: str | None = None,
    product_type: str | None = None,
) -> pd.DataFrame:
    if scope != "BROKERAGE":
        raise ValueError("第一版 PVM 仅实现 BROKERAGE")
    detail = get_pvm_detail(period, branch_id, customer_segment, product_type)
    if detail.empty:
        return pd.DataFrame(columns=[
            "period", "branch_id", "branch_name", "customer_segment", "product_type",
            "budget_revenue", "actual_revenue", "budget_trade_volume", "actual_trade_volume",
            "budget_commission_rate", "actual_commission_rate", "total_variance",
            "volume_effect", "rate_effect", "mix_effect", "explanation",
        ])
    return _aggregate_pvm(detail, period)


def detect_management_insights(period: str) -> pd.DataFrame:
    pvm = run_pvm_analysis(period, "BROKERAGE").iloc[0]
    branch = calculate_branch_profitability(period)
    biz = calculate_bizline_profitability(period)
    budget = _table("monthly_budget")
    actual = _table("monthly_actual")
    rows = []
    idx = 1
    if pvm["total_variance"] < 0:
        rows.append({
            "insight_id": f"MI_{period.replace('-', '')}_{idx:02d}",
            "period": period,
            "insight_type": "BROKERAGE_VARIANCE",
            "severity": "HIGH",
            "title": "经纪业务收入低于预算",
            "finding": "交易量下降和佣金率下行同时拖累经纪佣金收入。",
            "financial_impact": float(pvm["total_variance"]),
            "recommendation": "跟踪市场交易量指数，重定价低佣机构客户，提升ETF和财富产品交叉销售。",
            "owner_department": "经纪业务总部",
            "follow_up_metric": "交易量影响、佣金率影响",
        })
        idx += 1
    high_revenue_low_margin = branch.sort_values("revenue", ascending=False).head(3)
    low_margin = high_revenue_low_margin[high_revenue_low_margin["operating_margin"] < branch["operating_margin"].median()]
    for _, r in low_margin.iterrows():
        rows.append({
            "insight_id": f"MI_{period.replace('-', '')}_{idx:02d}",
            "period": period,
            "insight_type": "HIGH_REVENUE_LOW_MARGIN_BRANCH",
            "severity": "MEDIUM",
            "title": f"{r['branch_id']} 收入靠前但利润率偏低",
            "finding": "该营业部表面收入高，但扣除 IT 系统和总部管理费用分摊后利润贡献不高。",
            "financial_impact": float(r["operating_profit"]),
            "recommendation": "建立客户资源消耗定价，复核高频客户服务成本。",
            "owner_department": str(r["branch_id"]),
            "follow_up_metric": "经营利润率、IT成本/收入",
        })
        idx += 1
    wealth_actual = actual[(actual["period"] == period) & (actual["biz_line_id"] == "WEALTH")]["actual_revenue"].sum()
    wealth_budget = budget[(budget["period"] == period) & (budget["biz_line_id"] == "WEALTH")]["budget_revenue"].sum()
    wealth_profit = biz[biz["biz_line_id"] == "WEALTH"]["operating_profit"].iloc[0]
    if wealth_actual > wealth_budget and wealth_profit / wealth_actual < 0.35:
        rows.append({
            "insight_id": f"MI_{period.replace('-', '')}_{idx:02d}",
            "period": period,
            "insight_type": "WEALTH_LOW_CONTRIBUTION",
            "severity": "MEDIUM",
            "title": "财富管理收入增长但利润贡献不足",
            "finding": "财富管理收入高于预算，但营销激励和分摊费用上升更快。",
            "financial_impact": float(wealth_profit),
            "recommendation": "按产品和客户分层复盘激励 ROI，收缩低利润促销。",
            "owner_department": "财富管理中心",
            "follow_up_metric": "营销激励费率、利润贡献率",
        })
        idx += 1
    margin_actual = actual[(actual["period"] == period) & (actual["biz_line_id"] == "MARGIN")]["actual_revenue"].sum()
    margin_budget = budget[(budget["period"] == period) & (budget["biz_line_id"] == "MARGIN")]["budget_revenue"].sum()
    if margin_actual < margin_budget:
        rows.append({
            "insight_id": f"MI_{period.replace('-', '')}_{idx:02d}",
            "period": period,
            "insight_type": "MARGIN_BALANCE_DECLINE",
            "severity": "MEDIUM",
            "title": "信用业务利息收入低于预算",
            "finding": "两融余额下降导致信用业务利息收入不及预算。",
            "financial_impact": float(margin_actual - margin_budget),
            "recommendation": "关注担保品质量和客户融资需求恢复，优化利率和额度策略。",
            "owner_department": "信用业务部",
            "follow_up_metric": "两融余额、融资利率",
        })
        idx += 1
    df = pd.DataFrame(rows)
    _replace_table("management_insight", df)
    return df


def generate_cfo_report_mock(period: str, what_if_result: dict | None = None) -> str:
    biz = calculate_bizline_profitability(period)
    branch = calculate_branch_profitability(period)
    pvm = run_pvm_analysis(period, "BROKERAGE").iloc[0]
    insights = detect_management_insights(period)
    from .profitability_insights import detect_high_revenue_low_profit_branches, explain_high_revenue_low_profit_branch
    from .recon_data_loader import get_recon_data_status
    from .what_if import simulate_brokerage_recovery

    total_revenue = biz["revenue"].sum()
    total_profit = biz["operating_profit"].sum()
    top_biz = biz.sort_values("operating_profit", ascending=False).iloc[0]
    weak_branch = branch.sort_values("operating_margin").iloc[0]
    high_low = detect_high_revenue_low_profit_branches(period)
    if high_low.empty:
        high_low_text = "- 本月未识别出显著的高收入低利润营业部。"
    else:
        high_low_rows = []
        for row in high_low.head(3).itertuples():
            detail = explain_high_revenue_low_profit_branch(period, str(row.branch_id))
            high_low_rows.append(
                f"- {detail['branch_name']}：收入 {detail['revenue'] / 10000:,.2f} 万元，"
                f"收入排名第 {detail['revenue_rank']}，经营利润率 {detail['operating_margin']:.2%}，"
                f"利润率排名第 {detail['margin_rank']}，原因标签 {', '.join(detail['reason_tags'])}。"
            )
        high_low_text = "\n".join(high_low_rows)
    if what_if_result is None:
        what_if_result = simulate_brokerage_recovery(period)
    what_if_text = (
        f"交易量变化 {what_if_result['trade_volume_change_pct']:.1%}、佣金率变化 {what_if_result['commission_rate_change_bp']:.2f}bp、"
        f"费用变化 {what_if_result['expense_change_pct']:.1%} 时，经纪收入影响 "
        f"{what_if_result['revenue_impact'] / 10000:,.2f} 万元，利润影响 {what_if_result['profit_impact'] / 10000:,.2f} 万元。"
    )
    data_status = get_recon_data_status()
    major = "\n".join(f"- {r.title}：{r.finding}，影响 {r.financial_impact / 10000:,.2f} 万元。" for r in insights.itertuples())
    biz_table = "\n".join(
        f"- {r.biz_line_id}: 收入 {r.revenue / 10000:,.2f} 万元，经营利润 {r.operating_profit / 10000:,.2f} 万元，贡献率 {r.profit_contribution_rate:.2%}"
        for r in biz.itertuples()
    )
    return f"""# CFO 月度经营分析报告（{period}）

## 本月经营概览
本月营业收入 {total_revenue / 10000:,.2f} 万元，分摊后经营利润 {total_profit / 10000:,.2f} 万元。利润贡献最高的业务线为 {top_biz['biz_line_id']}。

## 主要差异
经纪业务预实差异 {pvm['total_variance'] / 10000:,.2f} 万元，其中交易量影响 {pvm['volume_effect'] / 10000:,.2f} 万元，佣金率影响 {pvm['rate_effect'] / 10000:,.2f} 万元，混合影响 {pvm['mix_effect'] / 10000:,.2f} 万元。

## 业务线分析 / 业务线利润贡献
{biz_table}

## 经纪业务 PVM 拆解
预算收入 {pvm['budget_revenue'] / 10000:,.2f} 万元，实际收入 {pvm['actual_revenue'] / 10000:,.2f} 万元。交易量影响、佣金率影响和混合影响均由本地 PVM 函数计算。

## 营业部盈利分析
利润率最低营业部为 {weak_branch['branch_id']}，经营利润率 {weak_branch['operating_margin']:.2%}。高收入营业部需要结合 IT、总部和行情成本分摊后评价真实贡献。

## 高收入低利润营业部分析
{high_low_text}

## What-if 情景模拟结果
{what_if_text}

## 管理建议
{major}

## 风险提示
本报告基于合成明细数据和公开披露汇总口径校准，不代表真实长江证券内部经营数据；不构成投资建议。

## 数据来源说明
当前数据来源：{data_status['source']}。{data_status['message']}
"""


def export_cfo_report(period: str, what_if_result: dict | None = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"cfo_report_{period}.md"
    output_path.write_text(generate_cfo_report_mock(period, what_if_result), encoding="utf-8")
    return output_path


def generate_chart_data(period: str) -> dict[str, pd.DataFrame]:
    return {
        "bizline_profitability": calculate_bizline_profitability(period),
        "branch_profitability": calculate_branch_profitability(period),
        "brokerage_variance": run_brokerage_budget_variance(period),
        "pvm": run_pvm_analysis(period, "BROKERAGE"),
        "pvm_detail": get_pvm_detail(period),
        "insights": detect_management_insights(period),
    }
