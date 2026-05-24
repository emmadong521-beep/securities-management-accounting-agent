from __future__ import annotations

import pandas as pd

from .validation import _table


QUADRANTS = ["增长明星", "现金牛", "潜力观察", "低效待优化"]


def classify_bcg_quadrant(
    growth_value: float,
    margin_value: float,
    growth_threshold: float,
    margin_threshold: float,
) -> str:
    if growth_value >= growth_threshold and margin_value >= margin_threshold:
        return "增长明星"
    if growth_value < growth_threshold and margin_value >= margin_threshold:
        return "现金牛"
    if growth_value >= growth_threshold and margin_value < margin_threshold:
        return "潜力观察"
    return "低效待优化"


def _previous_period(period: str) -> str:
    year, month = period.split("-")
    month_num = int(month)
    if month_num == 1:
        return f"{int(year) - 1}-12"
    return f"{year}-{month_num - 1:02d}"


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.astype(float)
    return (numerator.astype(float) / denominator.abs().where(denominator != 0)).fillna(0.0)


def _action_for_quadrant(quadrant: str) -> str:
    return {
        "增长明星": "优先投入资源，扩大高增长和高盈利质量优势。",
        "现金牛": "稳定经营节奏，保持利润贡献并控制新增资源投入。",
        "潜力观察": "优化定价、成本结构和客户结构，验证增长能否转化为利润质量。",
        "低效待优化": "控制投入，复核费用分摊、客户结构和经营策略。",
    }[quadrant]


def _reason_for_row(row: pd.Series) -> str:
    return (
        f"增长性 {row['y_value']:.2%}，盈利质量 {row['x_value']:.2%}；"
        f"阈值分别为 {row['growth_threshold']:.2%} 和 {row['margin_threshold']:.2%}。"
    )


def _entity_master(entity_type: str) -> pd.DataFrame:
    if entity_type == "biz_line":
        master = _table("biz_line_master")
        return master.rename(columns={"biz_line_id": "entity_id", "biz_line_name": "entity_name"})[
            ["entity_id", "entity_name"]
        ]
    master = _table("branch_master")
    return master.rename(columns={"branch_id": "entity_id", "branch_name": "entity_name"})[
        ["entity_id", "entity_name"]
    ]


def calculate_bcg_matrix(
    period: str,
    entity_type: str = "biz_line",
    x_metric: str = "operating_margin",
    y_metric: str = "revenue_growth_pct",
) -> pd.DataFrame:
    if entity_type not in {"biz_line", "branch"}:
        raise ValueError("entity_type must be 'biz_line' or 'branch'")
    if x_metric not in {"operating_margin", "profit_contribution_rate"}:
        raise ValueError("x_metric must be operating_margin or profit_contribution_rate")
    if y_metric not in {"revenue_growth_pct", "budget_variance_rate"}:
        raise ValueError("y_metric must be revenue_growth_pct or budget_variance_rate")

    actual = _table("monthly_actual")
    budget = _table("monthly_budget")
    entity_col = "biz_line_id" if entity_type == "biz_line" else "branch_id"
    previous_period = _previous_period(period)

    current = actual[actual["period"] == period].groupby(entity_col, as_index=False).agg(
        revenue=("actual_revenue", "sum"),
        operating_profit=("actual_profit", "sum"),
        allocated_expense=("actual_allocated_expense", "sum"),
    )
    previous = actual[actual["period"] == previous_period].groupby(entity_col, as_index=False).agg(
        previous_revenue=("actual_revenue", "sum")
    )
    current_budget = budget[budget["period"] == period].groupby(entity_col, as_index=False).agg(
        budget_revenue=("budget_revenue", "sum")
    )
    if current.empty:
        return pd.DataFrame(
            columns=[
                "period",
                "entity_type",
                "entity_id",
                "entity_name",
                "revenue",
                "previous_revenue",
                "revenue_growth_pct",
                "budget_revenue",
                "budget_variance_rate",
                "operating_profit",
                "operating_margin",
                "profit_contribution_rate",
                "allocated_expense",
                "allocated_expense_ratio",
                "x_metric",
                "y_metric",
                "x_value",
                "y_value",
                "size_value",
                "growth_threshold",
                "margin_threshold",
                "quadrant",
                "quadrant_reason",
                "recommended_action",
            ]
        )

    df = current.merge(previous, on=entity_col, how="left").merge(current_budget, on=entity_col, how="left")
    df["previous_revenue"] = df["previous_revenue"].fillna(0.0)
    df["budget_revenue"] = df["budget_revenue"].fillna(0.0)
    df["period"] = period
    df["entity_type"] = entity_type
    df["entity_id"] = df[entity_col].astype(str)
    df = df.merge(_entity_master(entity_type), on="entity_id", how="left")
    df["entity_name"] = df["entity_name"].fillna(df["entity_id"])

    df["revenue_growth_pct"] = _safe_ratio(df["revenue"] - df["previous_revenue"], df["previous_revenue"])
    df["budget_variance_rate"] = _safe_ratio(df["revenue"] - df["budget_revenue"], df["budget_revenue"])
    df["operating_margin"] = _safe_ratio(df["operating_profit"], df["revenue"])
    total_operating_profit = float(df["operating_profit"].sum())
    df["profit_contribution_rate"] = df["operating_profit"] / total_operating_profit if total_operating_profit else 0.0
    df["allocated_expense_ratio"] = _safe_ratio(df["allocated_expense"], df["revenue"])
    df["x_metric"] = x_metric
    df["y_metric"] = y_metric
    df["x_value"] = df[x_metric].fillna(0.0)
    df["y_value"] = df[y_metric].fillna(0.0)
    df["size_value"] = df["revenue"].clip(lower=0.0)
    growth_threshold = float(df["y_value"].median()) if not df.empty else 0.0
    margin_threshold = float(df["x_value"].median()) if not df.empty else 0.0
    df["growth_threshold"] = growth_threshold
    df["margin_threshold"] = margin_threshold
    df["quadrant"] = df.apply(
        lambda row: classify_bcg_quadrant(row["y_value"], row["x_value"], growth_threshold, margin_threshold),
        axis=1,
    )
    df["quadrant_reason"] = df.apply(_reason_for_row, axis=1)
    df["recommended_action"] = df["quadrant"].map(_action_for_quadrant)

    ordered_columns = [
        "period",
        "entity_type",
        "entity_id",
        "entity_name",
        "revenue",
        "previous_revenue",
        "revenue_growth_pct",
        "budget_revenue",
        "budget_variance_rate",
        "operating_profit",
        "operating_margin",
        "profit_contribution_rate",
        "allocated_expense",
        "allocated_expense_ratio",
        "x_metric",
        "y_metric",
        "x_value",
        "y_value",
        "size_value",
        "growth_threshold",
        "margin_threshold",
        "quadrant",
        "quadrant_reason",
        "recommended_action",
    ]
    return df[ordered_columns].sort_values(["quadrant", "revenue"], ascending=[True, False]).reset_index(drop=True)


def explain_bcg_entity(row: pd.Series | dict) -> dict:
    row_data = row.to_dict() if isinstance(row, pd.Series) else dict(row)
    quadrant = str(row_data.get("quadrant", "低效待优化"))
    return {
        "entity_name": str(row_data.get("entity_name", row_data.get("entity_id", ""))),
        "quadrant": quadrant,
        "reason": str(row_data.get("quadrant_reason") or _reason_for_row(pd.Series(row_data))),
        "recommended_action": str(row_data.get("recommended_action") or _action_for_quadrant(quadrant)),
        "risk_note": "该矩阵使用内部管理会计指标，不使用外部市场份额或行业增长数据，需结合业务策略和资源约束复核。",
    }


def generate_bcg_summary(period: str, entity_type: str = "biz_line") -> dict:
    matrix = calculate_bcg_matrix(period, entity_type)
    if matrix.empty:
        return {
            "period": period,
            "entity_type": entity_type,
            "quadrant_counts": {},
            "stars": [],
            "cash_cows": [],
            "potential": [],
            "low_efficiency": [],
            "summary": "当前期间无可用经营组合矩阵数据。",
            "recommended_actions": [],
        }
    quadrant_counts = {quadrant: int((matrix["quadrant"] == quadrant).sum()) for quadrant in QUADRANTS}
    by_quadrant = {
        quadrant: matrix[matrix["quadrant"] == quadrant]["entity_name"].head(5).astype(str).tolist()
        for quadrant in QUADRANTS
    }
    actions = []
    for quadrant in QUADRANTS:
        entities = by_quadrant[quadrant]
        if entities:
            actions.append(f"{quadrant}：{_action_for_quadrant(quadrant)} 代表对象：{', '.join(entities)}。")
    summary = (
        f"{period} {entity_type} 经营组合矩阵显示：增长明星 {quadrant_counts['增长明星']} 个，"
        f"现金牛 {quadrant_counts['现金牛']} 个，潜力观察 {quadrant_counts['潜力观察']} 个，"
        f"低效待优化 {quadrant_counts['低效待优化']} 个。"
    )
    return {
        "period": period,
        "entity_type": entity_type,
        "quadrant_counts": quadrant_counts,
        "stars": by_quadrant["增长明星"],
        "cash_cows": by_quadrant["现金牛"],
        "potential": by_quadrant["潜力观察"],
        "low_efficiency": by_quadrant["低效待优化"],
        "summary": summary,
        "recommended_actions": actions,
    }
