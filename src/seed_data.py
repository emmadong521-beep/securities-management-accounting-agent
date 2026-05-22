from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import RANDOM_SEED, SYNTHETIC_DIR
from .load_audit_report import load_audit_metrics
from .schema import CHART_OF_ACCOUNTS, TABLE_COLUMNS


PERIODS = [f"2025-{m:02d}" for m in range(1, 13)]
BRANCHES = [
    ("B001", "深圳营业部", "华南", "深圳", "2010-03-18"),
    ("B002", "上海营业部", "华东", "上海", "2008-06-12"),
    ("B003", "北京营业部", "华北", "北京", "2009-09-01"),
    ("B004", "广州营业部", "华南", "广州", "2011-04-20"),
    ("B005", "杭州营业部", "华东", "杭州", "2014-07-11"),
    ("B006", "成都营业部", "西南", "成都", "2012-10-08"),
    ("B007", "武汉营业部", "华中", "武汉", "2007-05-09"),
    ("B008", "南京营业部", "华东", "南京", "2015-11-22"),
    ("B009", "重庆营业部", "西南", "重庆", "2016-08-15"),
]
BIZ_LINES = [
    ("BROKERAGE", "经纪业务", "手续费佣金、交易量和佣金率"),
    ("IB", "投行业务", "承销保荐、财务顾问项目"),
    ("ASSET_MGMT", "资产管理", "管理费和资管规模"),
    ("PROPRIETARY", "自营投资", "投资收益和公允价值变动"),
    ("MARGIN", "信用业务", "融资融券利息收入"),
    ("WEALTH", "财富管理", "代销金融产品和投顾"),
    ("HQ", "总部管理", "总部共享与其他收入费用"),
]
SEGMENTS = [
    ("RETAIL", "普通零售", "大众零售客户"),
    ("HNW", "高净值", "高净值及财富客户"),
    ("INSTITUTION", "机构客户", "机构客户"),
]
PRODUCTS = [
    ("P001", "STOCK", "股票", "BROKERAGE"),
    ("P002", "FUND", "基金", "BROKERAGE"),
    ("P003", "BOND", "债券", "BROKERAGE"),
    ("P004", "ETF", "ETF", "BROKERAGE"),
    ("P005", "MARGIN_FINANCING", "融资融券", "MARGIN"),
    ("P006", "IB_PROJECT", "投行项目", "IB"),
    ("P007", "ASSET_MGMT_PLAN", "资管计划", "ASSET_MGMT"),
    ("P008", "WEALTH_PRODUCT", "财富产品", "WEALTH"),
    ("P009", "PROPRIETARY_BOOK", "自营投资组合", "PROPRIETARY"),
    ("P010", "HQ_SERVICE", "总部服务", "HQ"),
]


def _money(value: float) -> float:
    return round(float(value), 2)


def _write_csv(output_dir: Path, name: str, rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=TABLE_COLUMNS.get(name))
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_dir / f"{name}.csv", index=False)
    return df


def _profitability(monthly_actual: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    branch = monthly_actual.groupby(["period", "branch_id"], as_index=False).agg(
        revenue=("actual_revenue", "sum"),
        direct_cost=("actual_direct_cost", "sum"),
        allocated_expense=("actual_allocated_expense", "sum"),
        operating_profit=("actual_profit", "sum"),
    )
    branch["operating_margin"] = branch["operating_profit"] / branch["revenue"].replace(0, np.nan)
    branch["profit_rank"] = branch.groupby("period")["operating_profit"].rank(ascending=False, method="first").astype(int)
    biz = monthly_actual.groupby(["period", "biz_line_id"], as_index=False).agg(
        revenue=("actual_revenue", "sum"),
        direct_cost=("actual_direct_cost", "sum"),
        allocated_expense=("actual_allocated_expense", "sum"),
        operating_profit=("actual_profit", "sum"),
    )
    biz["operating_margin"] = biz["operating_profit"] / biz["revenue"].replace(0, np.nan)
    total_profit = biz.groupby("period")["operating_profit"].transform("sum")
    biz["profit_contribution_rate"] = biz["operating_profit"] / total_profit.replace(0, np.nan)
    return branch.round(4), biz.round(4)


def _pvm_rows(budget: pd.DataFrame, actual: pd.DataFrame) -> list[dict]:
    rows = []
    branch_name = {branch_id: name for branch_id, name, *_ in BRANCHES}
    keys = ["period", "branch_id", "customer_segment", "product_type"]
    b = budget[budget["biz_line_id"] == "BROKERAGE"]
    a = actual[actual["biz_line_id"] == "BROKERAGE"]
    merged = b.merge(a, on=keys + ["biz_line_id"], how="inner")
    for r in merged.itertuples():
        budget_revenue = float(r.budget_revenue)
        actual_revenue = float(r.actual_revenue)
        budget_volume = float(r.budget_trade_volume)
        actual_volume = float(r.actual_trade_volume)
        budget_rate = float(r.budget_commission_rate)
        actual_rate = float(r.actual_commission_rate)
        volume_effect = (actual_volume - budget_volume) * budget_rate
        rate_effect = actual_volume * (actual_rate - budget_rate)
        total_variance = actual_revenue - budget_revenue
        mix_effect = total_variance - volume_effect - rate_effect
        rows.append({
            "period": r.period,
            "branch_id": r.branch_id,
            "branch_name": branch_name.get(r.branch_id, r.branch_id),
            "customer_segment": r.customer_segment,
            "product_type": r.product_type,
            "budget_revenue": _money(budget_revenue),
            "actual_revenue": _money(actual_revenue),
            "budget_trade_volume": _money(budget_volume),
            "actual_trade_volume": _money(actual_volume),
            "budget_commission_rate": round(budget_rate, 8),
            "actual_commission_rate": round(actual_rate, 8),
            "total_variance": _money(total_variance),
            "volume_effect": _money(volume_effect),
            "rate_effect": _money(rate_effect),
            "mix_effect": _money(mix_effect),
            "explanation": "经纪佣金收入 = 交易量 × 平均佣金率；差异按营业部、客户分层和产品类型拆解。",
        })
    return rows


def generate_synthetic_data(output_dir: str | Path = SYNTHETIC_DIR) -> dict[str, int]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(RANDOM_SEED)
    metrics = load_audit_metrics()
    annual_revenue = {
        "BROKERAGE": metrics["business_structure"]["证券经纪业务净收入"],
        "MARGIN": metrics["business_structure"]["融资融券业务利息收入"],
        "PROPRIETARY": metrics["business_structure"]["证券自营业务分部收入"],
        "IB": metrics["business_structure"]["投资银行业务净收入"],
        "ASSET_MGMT": metrics["business_structure"]["资产管理业务分部收入"],
        "WEALTH": metrics["business_structure"]["代销金融产品业务收入"] * 2.4,
        "HQ": 750_000_000.0,
    }
    season = np.array([0.073, 0.066, 0.081, 0.079, 0.084, 0.082, 0.077, 0.079, 0.09, 0.088, 0.097, 0.104])
    season = season / season.sum()
    branch_weights = pd.Series([0.15, 0.22, 0.13, 0.10, 0.09, 0.08, 0.11, 0.07, 0.05], index=[b[0] for b in BRANCHES])
    biz_product = {
        "BROKERAGE": "STOCK",
        "IB": "IB_PROJECT",
        "ASSET_MGMT": "ASSET_MGMT_PLAN",
        "PROPRIETARY": "PROPRIETARY_BOOK",
        "MARGIN": "MARGIN_FINANCING",
        "WEALTH": "WEALTH_PRODUCT",
        "HQ": "HQ_SERVICE",
    }
    biz_segment = {
        "BROKERAGE": "RETAIL",
        "IB": "INSTITUTION",
        "ASSET_MGMT": "HNW",
        "PROPRIETARY": "INSTITUTION",
        "MARGIN": "HNW",
        "WEALTH": "HNW",
        "HQ": "INSTITUTION",
    }
    budget_rows, actual_rows = [], []
    for month_idx, period in enumerate(PERIODS):
        market_factor = 0.88 if month_idx >= 6 else 0.92
        for biz_id, _, _ in BIZ_LINES:
            actual_annual = annual_revenue[biz_id]
            if biz_id == "BROKERAGE":
                budget_annual = actual_annual / 0.86
            elif biz_id == "MARGIN":
                budget_annual = actual_annual / 0.91
            elif biz_id == "WEALTH":
                budget_annual = actual_annual / 1.14
            elif biz_id == "IB":
                budget_annual = actual_annual * 1.03
            elif biz_id == "HQ":
                budget_annual = actual_annual * 0.96
            else:
                budget_annual = actual_annual * 0.98
            for branch_id, bw in branch_weights.items():
                branch_multiplier = 1.0
                if biz_id == "BROKERAGE" and branch_id == "B002":
                    branch_multiplier = 1.18
                if biz_id == "WEALTH" and branch_id in {"B001", "B002", "B005"}:
                    branch_multiplier = 1.25
                b_revenue = budget_annual * season[month_idx] * bw * branch_multiplier
                a_revenue = actual_annual * season[month_idx] * bw * branch_multiplier
                if biz_id == "BROKERAGE":
                    segment_weights = {"RETAIL": 0.56, "HNW": 0.25, "INSTITUTION": 0.19}
                    product_weights = {"STOCK": 0.58, "FUND": 0.17, "BOND": 0.08, "ETF": 0.17}
                    segment_rate_adj = {"RETAIL": 1.08, "HNW": 0.94, "INSTITUTION": 0.76}
                    product_rate_adj = {"STOCK": 1.00, "FUND": 0.90, "BOND": 0.72, "ETF": 0.82}
                    for segment, segment_weight in segment_weights.items():
                        for product_type, product_weight in product_weights.items():
                            combo_revenue = b_revenue * segment_weight * product_weight
                            budget_rate = (0.00036 if branch_id != "B002" else 0.00030) * segment_rate_adj[segment] * product_rate_adj[product_type]
                            if branch_id == "B003":
                                budget_rate *= 0.95
                            budget_volume = combo_revenue / budget_rate
                            actual_volume = budget_volume * market_factor * (0.94 if branch_id == "B002" else 0.98) * (0.96 if segment == "INSTITUTION" else 1.0)
                            actual_rate = budget_rate * (0.88 if segment == "INSTITUTION" else 0.91 if branch_id == "B002" else 0.96)
                            actual_revenue = actual_volume * actual_rate
                            direct_ratio = 0.23
                            alloc_ratio = 0.24 + (0.16 if branch_id == "B002" else 0.0) + (0.06 if branch_id in {"B006", "B009"} else 0.0)
                            b_direct = combo_revenue * direct_ratio
                            b_alloc = combo_revenue * 0.24
                            a_direct = actual_revenue * direct_ratio
                            a_alloc = actual_revenue * alloc_ratio
                            budget_rows.append({
                                "period": period,
                                "biz_line_id": biz_id,
                                "branch_id": branch_id,
                                "product_type": product_type,
                                "customer_segment": segment,
                                "budget_revenue": _money(combo_revenue),
                                "budget_direct_cost": _money(b_direct),
                                "budget_allocated_expense": _money(b_alloc),
                                "budget_profit": _money(combo_revenue - b_direct - b_alloc),
                                "budget_trade_volume": _money(budget_volume),
                                "budget_commission_rate": round(budget_rate, 8),
                            })
                            actual_rows.append({
                                "period": period,
                                "biz_line_id": biz_id,
                                "branch_id": branch_id,
                                "product_type": product_type,
                                "customer_segment": segment,
                                "actual_revenue": _money(actual_revenue),
                                "actual_direct_cost": _money(a_direct),
                                "actual_allocated_expense": _money(a_alloc),
                                "actual_profit": _money(actual_revenue - a_direct - a_alloc),
                                "actual_trade_volume": _money(actual_volume),
                                "actual_commission_rate": round(actual_rate, 8),
                            })
                    continue
                elif biz_id == "MARGIN":
                    budget_volume = b_revenue / 0.00008
                    actual_volume = budget_volume * 0.88
                    actual_rate = 0.00008 * 0.99
                    a_revenue = actual_volume * actual_rate
                else:
                    budget_volume = 0.0
                    actual_volume = 0.0
                    budget_rate = 0.0
                    actual_rate = 0.0
                direct_ratio = {"BROKERAGE": 0.23, "IB": 0.38, "ASSET_MGMT": 0.29, "PROPRIETARY": 0.08, "MARGIN": 0.18, "WEALTH": 0.30, "HQ": 0.65}[biz_id]
                alloc_ratio = {"BROKERAGE": 0.24, "IB": 0.22, "ASSET_MGMT": 0.24, "PROPRIETARY": 0.10, "MARGIN": 0.18, "WEALTH": 0.26, "HQ": 0.72}[biz_id]
                actual_direct_ratio = direct_ratio
                actual_alloc_ratio = alloc_ratio
                if biz_id == "WEALTH":
                    actual_direct_ratio += 0.12
                    actual_alloc_ratio += 0.08
                if branch_id == "B002":
                    actual_alloc_ratio += 0.16
                if branch_id in {"B006", "B009"} and biz_id == "BROKERAGE":
                    actual_alloc_ratio += 0.06
                b_direct = b_revenue * direct_ratio
                b_alloc = b_revenue * alloc_ratio
                a_direct = a_revenue * actual_direct_ratio
                a_alloc = a_revenue * actual_alloc_ratio
                budget_rows.append({
                    "period": period,
                    "biz_line_id": biz_id,
                    "branch_id": branch_id,
                    "product_type": biz_product[biz_id],
                    "customer_segment": biz_segment[biz_id],
                    "budget_revenue": _money(b_revenue),
                    "budget_direct_cost": _money(b_direct),
                    "budget_allocated_expense": _money(b_alloc),
                    "budget_profit": _money(b_revenue - b_direct - b_alloc),
                    "budget_trade_volume": _money(budget_volume),
                    "budget_commission_rate": round(budget_rate, 8),
                })
                actual_rows.append({
                    "period": period,
                    "biz_line_id": biz_id,
                    "branch_id": branch_id,
                    "product_type": biz_product[biz_id],
                    "customer_segment": biz_segment[biz_id],
                    "actual_revenue": _money(a_revenue),
                    "actual_direct_cost": _money(a_direct),
                    "actual_allocated_expense": _money(a_alloc),
                    "actual_profit": _money(a_revenue - a_direct - a_alloc),
                    "actual_trade_volume": _money(actual_volume),
                    "actual_commission_rate": round(actual_rate, 8),
                })
    budget = pd.DataFrame(budget_rows)
    actual = pd.DataFrame(actual_rows)

    brokerage_rows = []
    for period in PERIODS:
        for branch_id in branch_weights.index:
            branch_actual = actual[(actual["period"] == period) & (actual["branch_id"] == branch_id) & (actual["biz_line_id"] == "BROKERAGE")]
            total_volume = float(branch_actual["actual_trade_volume"].sum())
            total_income = float(branch_actual["actual_revenue"].sum())
            weights = [0.62, 0.25, 0.13]
            for segment, weight in zip(["RETAIL", "HNW", "INSTITUTION"], weights):
                rate = float(branch_actual["actual_commission_rate"].iloc[0]) * (1.05 if segment == "RETAIL" else 0.95 if segment == "HNW" else 0.78)
                brokerage_rows.append({
                    "period": period,
                    "branch_id": branch_id,
                    "customer_segment": segment,
                    "product_type": "STOCK" if segment != "HNW" else "ETF",
                    "trade_volume": _money(total_volume * weight),
                    "avg_commission_rate": round(rate, 8),
                    "commission_income": _money(total_income * weight),
                    "active_customers": int(rng.integers(800, 4500) * weight),
                    "new_customers": int(rng.integers(30, 260) * weight),
                    "churn_customers": int(rng.integers(20, 180) * weight),
                })

    branch_expense_rows = []
    for period in PERIODS:
        act_p = actual[actual["period"] == period]
        for branch_id in branch_weights.index:
            branch = act_p[act_p["branch_id"] == branch_id]
            allocated = float(branch["actual_allocated_expense"].sum())
            revenue = float(branch["actual_revenue"].sum())
            salary = revenue * (0.12 if branch_id != "B002" else 0.10)
            rent = revenue * (0.035 if branch_id in {"B001", "B002", "B003"} else 0.028)
            marketing = revenue * (0.04 if branch_id not in {"B001", "B005"} else 0.07)
            it_alloc = allocated * (0.36 if branch_id == "B002" else 0.25)
            market_data = allocated * 0.18
            hq_alloc = allocated - it_alloc - market_data
            branch_expense_rows.append({
                "period": period,
                "branch_id": branch_id,
                "salary_expense": _money(salary),
                "rent_expense": _money(rent),
                "marketing_expense": _money(marketing),
                "it_allocated_expense": _money(it_alloc),
                "market_data_allocated_expense": _money(market_data),
                "hq_allocated_expense": _money(hq_alloc),
                "total_expense": _money(salary + rent + marketing + allocated),
            })

    branch_profit, biz_profit = _profitability(actual)
    pvm_rows = _pvm_rows(budget, actual)
    market_rows = []
    for idx, period in enumerate(PERIODS):
        market_rows.append({
            "period": period,
            "market_trade_volume_index": round(100 * (0.98 - idx * 0.008 + rng.normal(0, 0.01)), 2),
            "industry_avg_commission_rate": round(0.00035 * (0.99 - idx * 0.003), 8),
            "industry_avg_branch_margin": round(0.33 - idx * 0.003, 4),
            "market_comment": "市场交易活跃度边际走弱，机构客户费率竞争加剧" if idx >= 6 else "市场交易活跃度平稳",
        })
    insight_rows = []
    for idx, period in enumerate(PERIODS, start=1):
        pvm = pd.DataFrame(pvm_rows).query("period == @period").iloc[0]
        insight_rows.append({
            "insight_id": f"INS{idx:03d}A",
            "period": period,
            "insight_type": "BROKERAGE_VARIANCE",
            "severity": "HIGH",
            "title": "经纪业务收入低于预算",
            "finding": "市场交易量下降叠加机构客户佣金率下行，导致经纪佣金收入低于预算。",
            "financial_impact": _money(pvm["total_variance"]),
            "recommendation": "复盘机构客户费率策略，提升ETF和财富产品交叉销售。",
            "owner_department": "经纪业务总部",
            "follow_up_metric": "交易量指数、平均佣金率",
        })
        insight_rows.append({
            "insight_id": f"INS{idx:03d}B",
            "period": period,
            "insight_type": "LOW_MARGIN_BRANCH",
            "severity": "MEDIUM",
            "title": "上海营业部收入靠前但利润率偏低",
            "finding": "高频交易客户占比高，IT系统和总部管理费用分摊后经营利润率被压低。",
            "financial_impact": _money(branch_profit[(branch_profit["period"] == period) & (branch_profit["branch_id"] == "B002")]["operating_profit"].iloc[0]),
            "recommendation": "优化高频客户定价，单列系统资源消耗指标。",
            "owner_department": "上海营业部",
            "follow_up_metric": "IT成本/收入、经营利润率",
        })
        insight_rows.append({
            "insight_id": f"INS{idx:03d}C",
            "period": period,
            "insight_type": "WEALTH_LOW_CONTRIBUTION",
            "severity": "MEDIUM",
            "title": "财富管理收入增长但利润贡献不足",
            "finding": "财富管理收入高于预算，但营销激励费用上升更快，利润贡献低于预期。",
            "financial_impact": _money(biz_profit[(biz_profit["period"] == period) & (biz_profit["biz_line_id"] == "WEALTH")]["operating_profit"].iloc[0]),
            "recommendation": "调整营销激励 ROI 门槛，聚焦高留存产品。",
            "owner_department": "财富管理中心",
            "follow_up_metric": "营销费率、利润贡献率",
        })

    outputs = {
        "chart_of_accounts": CHART_OF_ACCOUNTS,
        "biz_line_master": [{"biz_line_id": b, "biz_line_name": n, "description": d} for b, n, d in BIZ_LINES],
        "branch_master": [{"branch_id": b, "branch_name": n, "region": r, "city": c, "open_date": o, "status": "ACTIVE"} for b, n, r, c, o in BRANCHES],
        "customer_segment_master": [{"segment_id": s, "segment_name": n, "description": d} for s, n, d in SEGMENTS],
        "product_master": [{"product_id": p, "product_type": t, "product_name": n, "biz_line_id": b} for p, t, n, b in PRODUCTS],
        "monthly_budget": budget_rows,
        "monthly_actual": actual_rows,
        "brokerage_kpi": brokerage_rows,
        "branch_expense": branch_expense_rows,
        "branch_profitability": branch_profit.to_dict("records"),
        "bizline_profitability": biz_profit.to_dict("records"),
        "pvm_analysis_result": pvm_rows,
        "management_insight": insight_rows,
        "market_benchmark": market_rows,
    }
    counts = {}
    for table, rows in outputs.items():
        counts[table] = len(_write_csv(output_dir, table, rows))
    return counts


if __name__ == "__main__":
    for table, count in generate_synthetic_data().items():
        print(f"{table}: {count}")
