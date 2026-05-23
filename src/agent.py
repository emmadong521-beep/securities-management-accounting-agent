from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import SYNTHETIC_DIR
from .validation import (
    calculate_bizline_profitability,
    calculate_branch_profitability,
    detect_management_insights,
    export_cfo_report,
    generate_cfo_report_mock,
    run_brokerage_budget_variance,
    run_pvm_analysis,
)


@dataclass
class AgentStep:
    step_no: int
    thought: str
    tool_name: str
    tool_input: dict
    observation: str


@dataclass
class AgentResult:
    user_task: str
    plan: list[str]
    steps: list[AgentStep]
    final_answer: str
    report_path: str | None
    chart_refs: list[str] | None


def _extract_period(user_task: str, period: str | None) -> str:
    if period:
        return period
    match = re.search(r"20\d{2}[-年](0[1-9]|1[0-2])", user_task)
    if match:
        return match.group(0).replace("年", "-")
    compact = re.search(r"(20\d{2})(0[1-9]|1[0-2])", user_task)
    if compact:
        return f"{compact.group(1)}-{compact.group(2)}"
    return "2025-09"


def _format_amount(value: float) -> str:
    return f"{value / 10000:,.2f} 万元"


def _task_type(user_task: str) -> str:
    task = user_task.lower()
    if "营业部" in user_task or "利润率" in user_task or "深圳" in user_task or "上海" in user_task:
        return "BRANCH_MARGIN"
    if "经纪" in user_task or "佣金率" in user_task or "交易量" in user_task or "pvm" in task:
        return "BROKERAGE_PVM"
    return "PROFIT_VARIANCE"


def _branch_master() -> pd.DataFrame:
    path = SYNTHETIC_DIR / "branch_master.csv"
    return pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["branch_id", "branch_name", "city"])


def _target_branch_id(user_task: str, branch: pd.DataFrame) -> str:
    master = _branch_master()
    for row in master.itertuples():
        if str(row.city) in user_task or str(row.branch_name) in user_task or str(row.branch_id) in user_task:
            return str(row.branch_id)
    if not branch.empty:
        return str(branch.sort_values("revenue", ascending=False).iloc[0]["branch_id"])
    return "B001"


def _branch_label(branch_id: str) -> str:
    master = _branch_master()
    match = master[master["branch_id"] == branch_id]
    if match.empty:
        return branch_id
    return str(match.iloc[0]["branch_name"])


def _major_pvm_effect(pvm: pd.Series) -> tuple[str, float]:
    effects = {
        "交易量影响": float(pvm["volume_effect"]),
        "佣金率影响": float(pvm["rate_effect"]),
        "混合影响": float(pvm["mix_effect"]),
    }
    name, value = max(effects.items(), key=lambda item: abs(item[1]))
    return name, value


def _run_profit_variance(period: str, user_task: str) -> AgentResult:
    plan = [
        "查询业务线分摊后盈利能力",
        "检查经纪业务预算与实际差异",
        "执行经纪业务 PVM 拆解",
        "查询营业部盈利能力并识别低利润率对象",
        "生成管理洞察和 CFO 报告",
    ]
    steps: list[AgentStep] = []

    biz = calculate_bizline_profitability(period)
    total_profit = float(biz["operating_profit"].sum())
    top_biz = biz.sort_values("operating_profit", ascending=False).iloc[0]
    steps.append(AgentStep(1, "先确认各业务线分摊后利润贡献。", "calculate_bizline_profitability", {"period": period}, f"总经营利润 {_format_amount(total_profit)}，利润贡献最高业务线为 {top_biz['biz_line_id']}。"))

    variance = run_brokerage_budget_variance(period)
    brokerage_revenue_variance = float(variance["revenue_variance"].sum())
    steps.append(AgentStep(2, "检查经纪业务预算与实际差异。", "run_brokerage_budget_variance", {"period": period}, f"经纪业务收入差异 {_format_amount(brokerage_revenue_variance)}。"))

    pvm = run_pvm_analysis(period, scope="BROKERAGE").iloc[0]
    major_effect, major_value = _major_pvm_effect(pvm)
    steps.append(
        AgentStep(
            3,
            "将经纪收入差异拆分为交易量、佣金率和混合影响。",
            "run_pvm_analysis",
            {"period": period, "scope": "BROKERAGE"},
            (
                f"总差异 {_format_amount(float(pvm['total_variance']))}；交易量影响 {_format_amount(float(pvm['volume_effect']))}；"
                f"佣金率影响 {_format_amount(float(pvm['rate_effect']))}；混合影响 {_format_amount(float(pvm['mix_effect']))}。"
            ),
        )
    )

    branch = calculate_branch_profitability(period)
    weak_branch = branch.sort_values("operating_margin").iloc[0]
    steps.append(AgentStep(4, "识别分摊后利润率最低的营业部。", "calculate_branch_profitability", {"period": period}, f"利润率最低营业部为 {_branch_label(str(weak_branch['branch_id']))}，经营利润率 {weak_branch['operating_margin']:.2%}。"))

    insights = detect_management_insights(period)
    titles = "；".join(insights["title"].astype(str).tolist())
    steps.append(AgentStep(5, "汇总规则识别出的经营洞察。", "detect_management_insights", {"period": period}, f"识别到 {len(insights)} 条洞察：{titles}。"))

    report = generate_cfo_report_mock(period)
    steps.append(AgentStep(6, "生成可复核的月度经营分析报告。", "generate_cfo_report_mock", {"period": period}, f"报告正文共 {len(report)} 个字符。"))

    path = export_cfo_report(period)
    report_path = str(Path(path))
    steps.append(AgentStep(7, "保存报告文件，便于后续复核。", "export_cfo_report", {"period": period}, f"报告路径：{report_path}"))

    final = (
        f"{period} 经营分析结论：公司分摊后经营利润为 {_format_amount(total_profit)}。"
        f"经纪业务收入差异为 {_format_amount(brokerage_revenue_variance)}，其中主要驱动为{major_effect}"
        f"（{_format_amount(major_value)}）。利润率最低营业部为 {_branch_label(str(weak_branch['branch_id']))}。"
        f"管理洞察提示：{titles}。"
    )
    return AgentResult(user_task, plan, steps, final, report_path, ["业务线利润贡献柱状图", "PVM 瀑布图", "营业部收入 vs 经营利润率散点图"])


def _run_brokerage_pvm(period: str, user_task: str) -> AgentResult:
    plan = [
        "执行经纪业务 PVM 拆解",
        "判断交易量影响和佣金率影响的相对贡献",
        "查询经纪业务预算与实际明细",
        "生成经营结论",
    ]
    steps: list[AgentStep] = []
    pvm = run_pvm_analysis(period, scope="BROKERAGE").iloc[0]
    major_effect, major_value = _major_pvm_effect(pvm)
    steps.append(
        AgentStep(
            1,
            "先用 PVM 模型拆解经纪佣金收入差异。",
            "run_pvm_analysis",
            {"period": period, "scope": "BROKERAGE"},
            (
                f"总差异 {_format_amount(float(pvm['total_variance']))}；交易量影响 {_format_amount(float(pvm['volume_effect']))}；"
                f"佣金率影响 {_format_amount(float(pvm['rate_effect']))}；混合影响 {_format_amount(float(pvm['mix_effect']))}。"
            ),
        )
    )
    variance = run_brokerage_budget_variance(period)
    worst = variance.sort_values("revenue_variance").iloc[0]
    steps.append(
        AgentStep(
            2,
            "下钻预算与实际明细，定位差异最大的组合。",
            "run_brokerage_budget_variance",
            {"period": period},
            (
                f"最大负差异组合为 {worst['branch_id']} / {worst['customer_segment']} / {worst['product_type']}，"
                f"收入差异 {_format_amount(float(worst['revenue_variance']))}。"
            ),
        )
    )
    final = (
        f"{period} 经纪业务收入低于预算的主要驱动是{major_effect}，金额为 {_format_amount(major_value)}。"
        f"交易量影响为 {_format_amount(float(pvm['volume_effect']))}，佣金率影响为 {_format_amount(float(pvm['rate_effect']))}，"
        f"混合影响为 {_format_amount(float(pvm['mix_effect']))}。建议优先复核低佣客户结构和交易量恢复情况。"
    )
    return AgentResult(user_task, plan, steps, final, None, ["PVM 瀑布图", "预算 vs 实际对比图", "Top negative variance 明细"])


def _run_branch_margin(period: str, user_task: str) -> AgentResult:
    plan = [
        "查询营业部分摊后盈利能力",
        "定位用户关注营业部",
        "比较收入排名和利润率排名",
        "生成管理建议",
    ]
    branch = calculate_branch_profitability(period)
    branch_id = _target_branch_id(user_task, branch)
    branch = branch.copy()
    branch["revenue_rank"] = branch["revenue"].rank(ascending=False, method="first").astype(int)
    branch["margin_rank"] = branch["operating_margin"].rank(ascending=False, method="first").astype(int)
    row = branch[branch["branch_id"] == branch_id].iloc[0]
    label = _branch_label(branch_id)
    steps = [
        AgentStep(1, "查询营业部收入、费用分摊和经营利润率。", "calculate_branch_profitability", {"period": period}, f"共返回 {len(branch)} 个营业部。"),
        AgentStep(
            2,
            "将目标营业部与全体营业部排名对比。",
            "branch_rank_analysis",
            {"period": period, "branch_id": branch_id},
            (
                f"{label} 收入排名第 {int(row['revenue_rank'])}，收入 {_format_amount(float(row['revenue']))}；"
                f"经营利润率排名第 {int(row['margin_rank'])}，经营利润率 {row['operating_margin']:.2%}。"
            ),
        ),
    ]
    final = (
        f"{period} {label} 收入为 {_format_amount(float(row['revenue']))}，收入排名第 {int(row['revenue_rank'])}；"
        f"经营利润率为 {row['operating_margin']:.2%}，利润率排名第 {int(row['margin_rank'])}。"
        f"若收入排名靠前但利润率偏低，通常说明客户或产品消耗的 IT、行情、总部管理等分摊成本较高，"
        f"或佣金率低于资源占用水平。建议按客户分层和产品类型复核服务成本与定价。"
    )
    return AgentResult(user_task, plan, steps, final, None, ["营业部收入 vs 经营利润率散点图", "营业部盈利能力排名表"])


def run_management_accounting_agent(user_task: str, period: str | None = None) -> AgentResult:
    selected_period = _extract_period(user_task, period)
    intent = _task_type(user_task)
    if intent == "BRANCH_MARGIN":
        return _run_branch_margin(selected_period, user_task)
    if intent == "BROKERAGE_PVM":
        return _run_brokerage_pvm(selected_period, user_task)
    return _run_profit_variance(selected_period, user_task)


def _period_from_context(context: AgentResult) -> str:
    return _extract_period(context.user_task + " " + context.final_answer, None)


def answer_management_followup(question: str, context: AgentResult) -> str:
    question_norm = question.strip().lower()
    combined_observation = "\n".join(step.observation for step in context.steps)
    period = _period_from_context(context)

    if "交易量" in question and "佣金率" in question:
        pvm = run_pvm_analysis(period, scope="BROKERAGE").iloc[0]
        volume = float(pvm["volume_effect"])
        rate = float(pvm["rate_effect"])
        bigger = "交易量影响" if abs(volume) >= abs(rate) else "佣金率影响"
        return f"{bigger}更大。交易量影响 {_format_amount(volume)}，佣金率影响 {_format_amount(rate)}。"
    if "业务线" in question or "主要差异" in question:
        insights = detect_management_insights(period)
        if not insights.empty:
            row = insights.iloc[0]
            return f"主要差异优先关注：{row['title']}，影响金额 {_format_amount(float(row['financial_impact']))}。"
        return "当前期间未识别到突出的业务线差异。"
    if "最低" in question and "营业部" in question:
        branch = calculate_branch_profitability(period).sort_values("operating_margin").iloc[0]
        return f"利润率最低营业部为 {_branch_label(str(branch['branch_id']))}，经营利润率 {branch['operating_margin']:.2%}。"
    if "建议" in question:
        recommendations = []
        insights = detect_management_insights(period)
        for row in insights.itertuples():
            recommendations.append(str(row.recommendation))
        if recommendations:
            return "管理建议：" + "；".join(recommendations)
        return "建议继续按业务线、营业部和客户分层下钻收入、直接成本和分摊费用。"
    if "恢复" in question and "5%" in question:
        pvm = run_pvm_analysis(period, scope="BROKERAGE").iloc[0]
        impact = float(pvm["actual_trade_volume"]) * 0.05 * float(pvm["actual_commission_rate"])
        return f"按当前实际平均佣金率粗略估算，交易量恢复 5% 将增加经纪收入约 {_format_amount(impact)}。"
    return f"当前上下文可回答 PVM 影响、业务线差异、营业部利润率和管理建议。已观察到：{combined_observation[:180]}..."
