from __future__ import annotations

from .validation import _table, run_pvm_analysis


def simulate_brokerage_recovery(
    period: str,
    trade_volume_change_pct: float = 0.05,
    commission_rate_change_bp: float = 0.0,
    expense_change_pct: float = 0.0,
) -> dict:
    pvm = run_pvm_analysis(period, scope="BROKERAGE").iloc[0]
    actual = _table("monthly_actual")
    brokerage = actual[(actual["period"] == period) & (actual["biz_line_id"] == "BROKERAGE")]
    base_trade_volume = float(pvm["actual_trade_volume"])
    base_commission_rate = float(pvm["actual_commission_rate"])
    base_revenue = float(pvm["actual_revenue"])
    base_expense = float((brokerage["actual_direct_cost"] + brokerage["actual_allocated_expense"]).sum())

    simulated_trade_volume = base_trade_volume * (1 + trade_volume_change_pct)
    simulated_commission_rate = max(base_commission_rate + commission_rate_change_bp * 0.0001, 0.0)
    simulated_revenue = simulated_trade_volume * simulated_commission_rate
    revenue_impact = simulated_revenue - base_revenue
    simulated_expense = base_expense * (1 + expense_change_pct)
    profit_impact = revenue_impact - (simulated_expense - base_expense)
    return {
        "period": period,
        "base_trade_volume": round(base_trade_volume, 2),
        "simulated_trade_volume": round(simulated_trade_volume, 2),
        "base_commission_rate": round(base_commission_rate, 8),
        "simulated_commission_rate": round(simulated_commission_rate, 8),
        "base_revenue": round(base_revenue, 2),
        "simulated_revenue": round(simulated_revenue, 2),
        "revenue_impact": round(revenue_impact, 2),
        "base_expense": round(base_expense, 2),
        "simulated_expense": round(simulated_expense, 2),
        "profit_impact": round(profit_impact, 2),
        "trade_volume_change_pct": trade_volume_change_pct,
        "commission_rate_change_bp": commission_rate_change_bp,
        "expense_change_pct": expense_change_pct,
        "explanation": (
            f"按实际佣金率基准测算，交易量变化 {trade_volume_change_pct:.1%}、"
            f"佣金率变化 {commission_rate_change_bp:.2f}bp、费用变化 {expense_change_pct:.1%} 时，"
            f"收入影响 {revenue_impact / 10000:,.2f} 万元，利润影响 {profit_impact / 10000:,.2f} 万元。"
        ),
    }
