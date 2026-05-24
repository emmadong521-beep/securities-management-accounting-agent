from __future__ import annotations

import re
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .agent_trace import ReasoningTrace, StepType
from .config import SYNTHETIC_DIR
from .llm_client import call_llm, is_llm_available
from .profitability_insights import detect_high_revenue_low_profit_branches, explain_high_revenue_low_profit_branch
from .validation import (
    calculate_bizline_profitability,
    calculate_branch_profitability,
    detect_management_insights,
    export_cfo_report,
    generate_cfo_report_mock,
    run_brokerage_budget_variance,
    run_pvm_analysis,
)
from .what_if import simulate_brokerage_recovery


@dataclass
class AgentStep:
    step_no: int
    thought: str
    tool_name: str
    tool_input: dict
    observation: str
    reason_for_tool: str = ""
    confidence: float | None = None


@dataclass
class AgentResult:
    user_task: str
    plan: list[str]
    steps: list[AgentStep]
    final_answer: str
    report_path: str | None
    chart_refs: list[str] | None
    llm_mode: str = "Mock Agent"
    llm_error: str | None = None


TOOL_REGISTRY = {
    "calculate_bizline_profitability": "计算业务线分摊后利润贡献",
    "calculate_branch_profitability": "计算营业部收入、成本、分摊费用和经营利润率",
    "run_brokerage_budget_variance": "计算经纪业务预算与实际差异",
    "run_pvm_analysis": "执行经纪佣金收入价量结构拆解",
    "detect_management_insights": "识别管理会计经营洞察",
    "detect_high_revenue_low_profit_branches": "识别高收入低利润营业部",
    "explain_high_revenue_low_profit_branch": "解释单个营业部收入高但利润率低的原因",
    "simulate_brokerage_recovery": "执行经纪业务交易量、佣金率和费用 What-if 测算",
    "generate_cfo_report_mock": "生成 CFO 月度经营分析报告",
}


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
    if "如果" in user_task or "恢复" in user_task or "what-if" in task or "what if" in task or "bp" in task or "%" in user_task:
        return "WHAT_IF"
    if "高收入" in user_task or "低利润" in user_task or ("收入排名" in user_task and "利润率" in user_task):
        return "HIGH_REVENUE_LOW_PROFIT"
    if "营业部" in user_task or "利润率" in user_task or "深圳" in user_task or "上海" in user_task:
        return "BRANCH_MARGIN"
    if "经纪" in user_task or "佣金率" in user_task or "交易量" in user_task or "pvm" in task:
        return "BROKERAGE_PVM"
    return "PROFIT_VARIANCE"


def _intent_from_task_type(task_type: str) -> str:
    return {
        "BRANCH_MARGIN": "branch_profitability",
        "HIGH_REVENUE_LOW_PROFIT": "high_revenue_low_profit",
        "BROKERAGE_PVM": "brokerage_pvm",
        "WHAT_IF": "what_if",
        "PROFIT_VARIANCE": "profit_variance",
    }.get(task_type, "unknown")


def _task_type_from_intent(intent: str) -> str:
    return {
        "branch_profitability": "BRANCH_MARGIN",
        "high_revenue_low_profit": "HIGH_REVENUE_LOW_PROFIT",
        "brokerage_pvm": "BROKERAGE_PVM",
        "what_if": "WHAT_IF",
        "profit_variance": "PROFIT_VARIANCE",
        "cfo_report": "PROFIT_VARIANCE",
    }.get(intent, "PROFIT_VARIANCE")


def _fallback_task_context(user_task: str, available_periods: list[str], period: str | None = None) -> dict:
    selected_period = _extract_period(user_task, period)
    if selected_period not in available_periods:
        selected_period = available_periods[0] if available_periods else "2025-09"
    task_type = _task_type(user_task)
    branch_name = None
    for candidate in ["深圳", "上海", "北京", "广州", "杭州", "成都", "武汉", "南京", "重庆"]:
        if candidate in user_task:
            branch_name = candidate
            break
    return {
        "intent": _intent_from_task_type(task_type),
        "period": selected_period,
        "branch_name": branch_name,
        "focus": "基于管理会计指标、PVM 和经营洞察生成结论",
    }


def parse_management_task_with_llm(user_task: str, available_periods: list[str]) -> dict:
    fallback = _fallback_task_context(user_task, available_periods)
    if not is_llm_available():
        return fallback
    try:
        content = call_llm(
            [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "user_task": user_task,
                            "available_periods": available_periods,
                            "allowed_intents": [
                                "profit_variance",
                                "brokerage_pvm",
                                "branch_profitability",
                                "high_revenue_low_profit",
                                "what_if",
                                "cfo_report",
                                "unknown",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
            system_prompt=(
                "你只负责解析证券公司管理会计 Agent 任务意图，不做金额计算。"
                "必须只返回 JSON，对象字段为 intent, period, branch_name, focus。"
            ),
        )
        parsed = json.loads(content)
        intent = str(parsed.get("intent") or fallback["intent"])
        if intent not in {"profit_variance", "brokerage_pvm", "branch_profitability", "high_revenue_low_profit", "what_if", "cfo_report", "unknown"}:
            intent = fallback["intent"]
        parsed_period = parsed.get("period") if parsed.get("period") in available_periods else fallback["period"]
        branch_name = parsed.get("branch_name") or fallback["branch_name"]
        return {
            "intent": intent,
            "period": parsed_period,
            "branch_name": branch_name,
            "focus": str(parsed.get("focus") or fallback["focus"])[:120],
        }
    except Exception:
        return fallback


def _fallback_plan(task_context: dict) -> list[str]:
    intent = task_context.get("intent")
    if intent == "brokerage_pvm":
        return ["执行经纪业务 PVM 拆解", "比较交易量和佣金率影响", "下钻预算与实际明细", "生成经营结论"]
    if intent == "high_revenue_low_profit":
        return ["计算营业部盈利能力", "识别高收入低利润营业部", "解释目标营业部原因标签", "生成管理建议"]
    if intent == "what_if":
        return ["读取经纪业务当前交易量和佣金率", "执行交易量、佣金率和费用情景测算", "计算收入和利润影响", "生成风险提示和建议动作"]
    if intent == "branch_profitability":
        return ["查询营业部盈利能力", "定位关注营业部", "比较收入排名和利润率排名", "生成管理建议"]
    return ["查询业务线利润贡献", "执行经纪业务 PVM", "下钻营业部盈利能力", "检测管理洞察", "生成经营结论"]


def generate_management_plan_with_llm(task_context: dict) -> list[str]:
    fallback = _fallback_plan(task_context)
    if not is_llm_available():
        return fallback
    try:
        content = call_llm(
            [{"role": "user", "content": json.dumps(task_context, ensure_ascii=False)}],
            system_prompt=(
                "你为证券公司管理会计 Agent 生成 4-6 步分析计划。"
                "计划应围绕查询业务线利润贡献、执行经纪业务 PVM、下钻营业部盈利能力、识别高收入低利润、执行 What-if、检测管理洞察、生成经营结论。"
                "不要编造金额。每行输出一步计划，不要输出编号。"
            ),
        )
        plan = [line.strip("- 1234567890.、") for line in content.splitlines() if line.strip()]
        return plan[:6] or fallback
    except Exception:
        return fallback


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


def generate_management_final_answer_with_llm(
    user_task: str,
    plan: list[str],
    steps: list[AgentStep],
    mock_answer: str,
) -> str:
    if not is_llm_available():
        return mock_answer
    facts = {
        "user_task": user_task,
        "plan": plan,
        "steps": [step.__dict__ for step in steps],
        "mock_answer": mock_answer,
    }
    content = call_llm(
        [{"role": "user", "content": json.dumps(facts, ensure_ascii=False, default=str)}],
        system_prompt=(
            "你是证券公司管理会计 Agent 的表达层。只能基于输入事实生成中文经营分析，"
            "不得自行计算金额，不得编造业务线、营业部或指标。"
            "输出包含核心结论、关键数字、主要驱动因素、建议动作和风险提示，金额单位保持万元。"
        ),
    )
    return content.strip() or mock_answer


def _run_profit_variance(period: str, user_task: str, plan: list[str] | None = None) -> AgentResult:
    plan = plan or _fallback_plan({"intent": "profit_variance", "period": period})
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
        f"核心结论：{period} 公司分摊后经营利润为 {_format_amount(total_profit)}。"
        f"关键数字：经纪业务收入差异 {_format_amount(brokerage_revenue_variance)}，主要驱动为{major_effect}"
        f"（{_format_amount(major_value)}）。主要驱动因素：利润率最低营业部为 {_branch_label(str(weak_branch['branch_id']))}，"
        f"管理洞察包括 {titles}。建议动作：优先处理经纪交易量、低佣客户定价和费用分摊后低利润网点。"
        f"风险提示：结论基于合成经营明细和本地规则计算，需结合真实业务审批口径复核。"
    )
    return AgentResult(user_task, plan, steps, final, report_path, ["业务线利润贡献柱状图", "PVM 瀑布图", "营业部收入 vs 经营利润率散点图"])


def _run_brokerage_pvm(period: str, user_task: str, plan: list[str] | None = None) -> AgentResult:
    plan = plan or _fallback_plan({"intent": "brokerage_pvm", "period": period})
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
        f"核心结论：{period} 经纪业务收入低于预算的主要驱动是{major_effect}。"
        f"关键数字：{major_effect}为 {_format_amount(major_value)}，交易量影响 {_format_amount(float(pvm['volume_effect']))}，"
        f"佣金率影响 {_format_amount(float(pvm['rate_effect']))}，混合影响 {_format_amount(float(pvm['mix_effect']))}。"
        f"主要驱动因素：交易量下降与佣金率下行共同拖累收入。建议动作：复核低佣客户结构和交易量恢复计划。"
        f"风险提示：PVM 按交易量乘平均佣金率拆解，未覆盖全部市场和产品结构变化。"
    )
    return AgentResult(user_task, plan, steps, final, None, ["PVM 瀑布图", "预算 vs 实际对比图", "Top negative variance 明细"])


def _run_branch_margin(period: str, user_task: str, plan: list[str] | None = None, branch_name: str | None = None) -> AgentResult:
    plan = plan or _fallback_plan({"intent": "branch_profitability", "period": period})
    branch = calculate_branch_profitability(period)
    target_text = f"{user_task} {branch_name or ''}"
    branch_id = _target_branch_id(target_text, branch)
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
        f"核心结论：{period} {label} 收入为 {_format_amount(float(row['revenue']))}，收入排名第 {int(row['revenue_rank'])}；"
        f"关键数字：经营利润率 {row['operating_margin']:.2%}，利润率排名第 {int(row['margin_rank'])}。"
        f"主要驱动因素：客户或产品消耗的 IT、行情、总部管理等分摊成本较高，或佣金率低于资源占用水平。"
        f"建议动作：按客户分层和产品类型复核服务成本与定价。风险提示：需结合分摊规则和客户协议进一步复核。"
    )
    return AgentResult(user_task, plan, steps, final, None, ["营业部收入 vs 经营利润率散点图", "营业部盈利能力排名表"])


def _run_high_revenue_low_profit(period: str, user_task: str, plan: list[str] | None = None, branch_name: str | None = None) -> AgentResult:
    plan = plan or _fallback_plan({"intent": "high_revenue_low_profit", "period": period})
    branch = calculate_branch_profitability(period)
    high_low = detect_high_revenue_low_profit_branches(period)
    steps = [
        AgentStep(
            1,
            "先计算营业部分摊后盈利能力，形成收入和利润率基础排名。",
            "calculate_branch_profitability",
            {"period": period},
            f"共返回 {len(branch)} 个营业部，最高收入营业部为 {branch.sort_values('revenue', ascending=False).iloc[0]['branch_id']}。",
            "高收入低利润分析需要先建立收入、费用和利润率基线。",
            0.93,
        ),
        AgentStep(
            2,
            "识别收入靠前但经营利润率偏低或费用分摊偏高的营业部。",
            "detect_high_revenue_low_profit_branches",
            {"period": period},
            f"识别到 {len(high_low)} 个高收入低利润营业部。",
            "规则筛选能快速定位看似赚钱但真实贡献不足的机构。",
            0.9,
        ),
    ]
    target_id = None
    if branch_name:
        master = _branch_master()
        hit = master[(master["city"].astype(str).str.contains(str(branch_name), na=False)) | (master["branch_name"].astype(str).str.contains(str(branch_name), na=False))]
        if not hit.empty:
            target_id = str(hit.iloc[0]["branch_id"])
    if target_id is None:
        if not high_low.empty:
            target_id = str(high_low.iloc[0]["branch_id"])
        else:
            target_id = _target_branch_id(user_task, branch)
    detail = explain_high_revenue_low_profit_branch(period, target_id)
    steps.append(
        AgentStep(
            3,
            "对目标营业部下钻原因标签和关键指标。",
            "explain_high_revenue_low_profit_branch",
            {"period": period, "branch_id": target_id},
            detail["explanation"],
            "单点解释用于输出可执行的费用、客户结构和定价建议。",
            0.88,
        )
    )
    final = (
        f"核心结论：{period} {detail['branch_name']} 收入 {_format_amount(detail['revenue'])}，"
        f"收入排名第 {detail['revenue_rank']}，但经营利润率 {detail['operating_margin']:.2%}，"
        f"利润率排名第 {detail['margin_rank']}。关键数字：分摊费用占收入比 {detail['allocated_expense_ratio']:.2%}，"
        f"平均佣金率 {detail['avg_commission_rate']:.5%}。主要驱动因素：{', '.join(detail['reason_tags'])}。"
        f"建议动作：{detail['recommendation']} 风险提示：需结合客户服务协议和分摊规则复核后再调整定价。"
    )
    return AgentResult(user_task, plan, steps, final, None, ["营业部盈利穿透分析", "费用分摊结构图"])


def _parse_pct_from_task(user_task: str, default: float = 0.05) -> float:
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", user_task)
    if match:
        return float(match.group(1)) / 100
    return default


def _parse_bp_from_task(user_task: str) -> float:
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*bp", user_task, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    if "下降" in user_task and "1" in user_task and "佣金率" in user_task:
        return -1.0
    return 0.0


def _parse_expense_pct_from_task(user_task: str) -> float:
    if "费用" not in user_task:
        return 0.0
    matches = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", user_task)
    if len(matches) >= 2:
        return float(matches[-1]) / 100
    if "增长" in user_task or "上升" in user_task:
        return 0.02 if "2" in user_task else 0.0
    return 0.0


def _run_what_if(period: str, user_task: str, plan: list[str] | None = None) -> AgentResult:
    plan = plan or _fallback_plan({"intent": "what_if", "period": period})
    trade_pct = _parse_pct_from_task(user_task, 0.05)
    rate_bp = _parse_bp_from_task(user_task)
    expense_pct = _parse_expense_pct_from_task(user_task)
    result = simulate_brokerage_recovery(period, trade_pct, rate_bp, expense_pct)
    steps = [
        AgentStep(
            1,
            "读取经纪业务实际交易量、平均佣金率和费用基线。",
            "run_pvm_analysis",
            {"period": period, "scope": "BROKERAGE"},
            (
                f"基准交易量 {result['base_trade_volume']:,.2f}，基准佣金率 {result['base_commission_rate']:.5%}，"
                f"基准收入 {_format_amount(result['base_revenue'])}。"
            ),
            "What-if 需要先锁定本地计算出的基准指标。",
            0.9,
        ),
        AgentStep(
            2,
            "按用户输入执行情景模拟。",
            "simulate_brokerage_recovery",
            {
                "period": period,
                "trade_volume_change_pct": trade_pct,
                "commission_rate_change_bp": rate_bp,
                "expense_change_pct": expense_pct,
            },
            result["explanation"],
            "收入和利润影响由代码计算，避免由模型直接估算金额。",
            0.92,
        ),
    ]
    final = (
        f"核心结论：在 {period}，若经纪业务交易量变化 {trade_pct:.1%}、佣金率变化 {rate_bp:.2f}bp、"
        f"费用变化 {expense_pct:.1%}，收入影响为 {_format_amount(result['revenue_impact'])}，"
        f"利润影响为 {_format_amount(result['profit_impact'])}。关键数字：模拟收入 {_format_amount(result['simulated_revenue'])}，"
        f"模拟费用 {_format_amount(result['simulated_expense'])}。建议动作：将交易量恢复假设与低佣客户重定价联动评估。"
        f"风险提示：该情景未考虑市场波动、客户流失和产品结构变化。"
    )
    return AgentResult(user_task, plan, steps, final, None, ["What-if 情景模拟瀑布图"])


def run_management_accounting_agent(user_task: str, period: str | None = None, use_llm: bool | None = None) -> AgentResult:
    available_periods = [f"2025-{m:02d}" for m in range(1, 13)]
    requested_llm = is_llm_available() if use_llm is None else bool(use_llm)
    llm_error = None
    llm_mode = "Mock Agent"
    if requested_llm and is_llm_available():
        llm_mode = "Volcengine Ark LLM Agent"
    elif requested_llm:
        llm_error = "LLM 配置不完整，已回退 Mock Agent。"

    task_context = _fallback_task_context(user_task, available_periods, period)
    if requested_llm and is_llm_available():
        try:
            task_context = parse_management_task_with_llm(user_task, available_periods)
            if period:
                task_context["period"] = period
        except Exception as exc:
            llm_error = f"LLM 任务解析失败，已回退 Mock Agent：{exc}"
            llm_mode = "Mock Agent"

    selected_period = str(task_context.get("period") or _extract_period(user_task, period))
    plan = _fallback_plan(task_context)
    if requested_llm and is_llm_available():
        try:
            plan = generate_management_plan_with_llm(task_context)
        except Exception as exc:
            llm_error = f"LLM 计划生成失败，已使用 Mock 计划：{exc}"

    intent = _task_type_from_intent(str(task_context.get("intent") or "profit_variance"))
    if intent == "WHAT_IF":
        result = _run_what_if(selected_period, user_task, plan)
    elif intent == "HIGH_REVENUE_LOW_PROFIT":
        result = _run_high_revenue_low_profit(selected_period, user_task, plan, task_context.get("branch_name"))
    elif intent == "BRANCH_MARGIN":
        result = _run_branch_margin(selected_period, user_task, plan, task_context.get("branch_name"))
    elif intent == "BROKERAGE_PVM":
        result = _run_brokerage_pvm(selected_period, user_task, plan)
    else:
        result = _run_profit_variance(selected_period, user_task, plan)

    mock_final = result.final_answer
    final = mock_final
    if requested_llm and is_llm_available():
        try:
            final = generate_management_final_answer_with_llm(user_task, result.plan, result.steps, mock_final)
        except Exception as exc:
            llm_error = f"LLM 结论生成失败，已展示 Mock 结果：{exc}"
            llm_mode = "Mock Agent"
            final = mock_final
    result.final_answer = final
    result.llm_mode = llm_mode
    result.llm_error = llm_error
    return result


def run_management_accounting_agent_with_trace(
    user_task: str,
    period: str | None = None,
) -> ReasoningTrace:
    started = time.perf_counter()
    available_periods = [f"2025-{m:02d}" for m in range(1, 13)]
    task_context = _fallback_task_context(user_task, available_periods, period)
    selected_period = str(task_context.get("period") or _extract_period(user_task, period))
    intent = str(task_context.get("intent") or "profit_variance")
    trade_pct = _parse_pct_from_task(user_task, 0.05)
    rate_bp = _parse_bp_from_task(user_task)
    expense_pct = _parse_expense_pct_from_task(user_task)
    task_context.update(
        {
            "trade_volume_change_pct": trade_pct,
            "commission_rate_change_bp": rate_bp,
            "expense_change_pct": expense_pct,
        }
    )
    trace = ReasoningTrace(user_task=user_task, intent=intent, period=selected_period)
    trace.add_step(
        StepType.INTENT_RECOGNITION,
        "识别经营分析任务",
        "解析用户输入中的期间、经营分析意图、营业部和情景模拟参数。",
        result=task_context,
    )

    plan = _fallback_plan(task_context)
    trace.add_step(
        StepType.PLAN_GENERATION,
        "制定分析计划",
        "按任务类型选择业务线利润、PVM、营业部盈利、高收入低利润、What-if 和管理洞察工具。",
        result={"plan": plan, "expected_tools": list(TOOL_REGISTRY.keys())},
    )

    biz = calculate_bizline_profitability(selected_period)
    total_profit = float(biz["operating_profit"].sum()) if not biz.empty else 0.0
    trace.add_step(
        StepType.TOOL_CALL,
        "计算业务线利润贡献",
        "读取实际收入、直接成本和分摊费用，形成业务线分摊后利润视图。",
        tool_name="calculate_bizline_profitability",
        tool_input={"period": selected_period},
        result=biz,
    )
    top_biz = biz.sort_values("operating_profit", ascending=False).iloc[0] if not biz.empty else None
    trace.add_step(
        StepType.OBSERVATION,
        "观察业务线贡献",
        (
            f"期间 {selected_period} 分摊后经营利润合计 {_format_amount(total_profit)}，"
            f"利润贡献最高业务线为 {top_biz['biz_line_id']}。"
            if top_biz is not None
            else f"期间 {selected_period} 未返回业务线利润数据。"
        ),
        result=biz,
    )

    pvm = run_pvm_analysis(selected_period, scope="BROKERAGE")
    pvm_row = pvm.iloc[0]
    major_effect, major_value = _major_pvm_effect(pvm_row)
    trace.add_step(
        StepType.TOOL_CALL,
        "执行经纪业务 PVM",
        "把经纪收入差异拆为交易量、佣金率和混合影响。",
        tool_name="run_pvm_analysis",
        tool_input={"period": selected_period, "scope": "BROKERAGE"},
        result=pvm,
    )
    trace.add_step(
        StepType.OBSERVATION,
        "观察 PVM 量价影响",
        (
            f"总差异 {_format_amount(float(pvm_row['total_variance']))}，主要驱动为"
            f"{major_effect}（{_format_amount(major_value)}）。"
        ),
        result=pvm_row.to_dict(),
    )

    branch = calculate_branch_profitability(selected_period)
    weak_branch = branch.sort_values("operating_margin").iloc[0] if not branch.empty else None
    trace.add_step(
        StepType.TOOL_CALL,
        "计算营业部盈利能力",
        "比较营业部收入、分摊费用、经营利润和经营利润率。",
        tool_name="calculate_branch_profitability",
        tool_input={"period": selected_period},
        result=branch,
    )
    trace.add_step(
        StepType.OBSERVATION,
        "观察营业部盈利排名",
        (
            f"利润率最低营业部为 {_branch_label(str(weak_branch['branch_id']))}，"
            f"经营利润率 {weak_branch['operating_margin']:.2%}。"
            if weak_branch is not None
            else "未返回营业部盈利数据。"
        ),
        result=weak_branch.to_dict() if weak_branch is not None else {},
    )

    high_low = detect_high_revenue_low_profit_branches(selected_period)
    trace.add_step(
        StepType.TOOL_CALL,
        "识别高收入低利润营业部",
        "筛选收入靠前但经营利润率靠后、分摊费用率偏高或佣金率偏低的营业部。",
        tool_name="detect_high_revenue_low_profit_branches",
        tool_input={"period": selected_period},
        result=high_low,
    )
    target_branch_id = None
    high_low_detail = None
    if not high_low.empty:
        target_branch_id = str(high_low.iloc[0]["branch_id"])
        high_low_detail = explain_high_revenue_low_profit_branch(selected_period, target_branch_id)
    trace.add_step(
        StepType.ANALYSIS_DECISION,
        "判断是否需要营业部下钻",
        (
            f"识别到 {len(high_low)} 个高收入低利润营业部，"
            f"优先下钻 {_branch_label(target_branch_id)}。"
            if target_branch_id
            else "当前期间未筛出高收入低利润营业部，保留业务线和 PVM 分析结论。"
        ),
        tool_name="explain_high_revenue_low_profit_branch" if target_branch_id else None,
        tool_input={"period": selected_period, "branch_id": target_branch_id} if target_branch_id else {},
        result=high_low_detail or high_low,
    )

    scenario = simulate_brokerage_recovery(selected_period, trade_pct, rate_bp, expense_pct)
    trace.add_step(
        StepType.TOOL_CALL,
        "执行 What-if 情景模拟",
        "根据交易量、佣金率和费用变化参数计算收入和利润影响。",
        tool_name="simulate_brokerage_recovery",
        tool_input={
            "period": selected_period,
            "trade_volume_change_pct": trade_pct,
            "commission_rate_change_bp": rate_bp,
            "expense_change_pct": expense_pct,
        },
        result=scenario,
    )
    trace.add_step(
        StepType.OBSERVATION,
        "观察情景模拟影响",
        (
            f"模拟收入影响 {_format_amount(float(scenario['revenue_impact']))}，"
            f"利润影响 {_format_amount(float(scenario['profit_impact']))}。"
        ),
        result=scenario,
    )

    insights = detect_management_insights(selected_period)
    trace.add_step(
        StepType.TOOL_CALL,
        "检测管理洞察",
        "汇总预算差异、费用分摊后盈利能力和业务故事规则产生的经营洞察。",
        tool_name="detect_management_insights",
        tool_input={"period": selected_period},
        result=insights,
    )
    insight_titles = "；".join(insights["title"].astype(str).tolist()) if not insights.empty else "未识别到重点洞察"
    trace.add_step(
        StepType.ANALYSIS_DECISION,
        "判断主要驱动因素",
        (
            f"主要驱动为 {major_effect}；营业部侧关注"
            f"{_branch_label(str(weak_branch['branch_id'])) if weak_branch is not None else '暂无'}；"
            f"管理洞察：{insight_titles}。"
        ),
        result={
            "major_pvm_effect": major_effect,
            "major_pvm_value": major_value,
            "weak_branch": weak_branch.to_dict() if weak_branch is not None else None,
            "insight_titles": insight_titles,
        },
    )

    final_answer = (
        f"核心结论：{selected_period} 分摊后经营利润为 {_format_amount(total_profit)}。"
        f"关键数字：经纪 PVM 总差异 {_format_amount(float(pvm_row['total_variance']))}，"
        f"主要驱动为{major_effect}（{_format_amount(major_value)}）；"
        f"What-if 模拟收入影响 {_format_amount(float(scenario['revenue_impact']))}，"
        f"利润影响 {_format_amount(float(scenario['profit_impact']))}。"
        f"主要驱动因素：{insight_titles}。建议动作：优先复核经纪交易量、低佣客户结构和费用分摊后低利润网点。"
        f"风险提示：结论基于合成经营数据和本地规则计算，实际管理动作需结合业务审批口径复核。"
    )
    trace.final_answer = final_answer
    trace.metadata = {
        "bizline_profitability": biz,
        "pvm": pvm,
        "branch_profitability": branch,
        "high_revenue_low_profit": high_low,
        "what_if": scenario,
        "insights": insights,
    }
    trace.add_step(
        StepType.CONCLUSION,
        "综合结论",
        final_answer,
        result={
            "period": selected_period,
            "total_profit": total_profit,
            "pvm_total_variance": float(pvm_row["total_variance"]),
            "major_pvm_effect": major_effect,
            "major_pvm_value": major_value,
            "what_if_revenue_impact": float(scenario["revenue_impact"]),
            "what_if_profit_impact": float(scenario["profit_impact"]),
            "insight_count": len(insights),
        },
    )
    trace.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return trace


def _period_from_context(context: AgentResult) -> str:
    return _extract_period(context.user_task + " " + context.final_answer, None)


def answer_management_followup(question: str, context: AgentResult, use_llm: bool | None = None) -> str:
    question_norm = question.strip().lower()
    combined_observation = "\n".join(step.observation for step in context.steps)
    period = _period_from_context(context)
    requested_llm = is_llm_available() if use_llm is None else bool(use_llm)
    if requested_llm and is_llm_available() and not ("恢复" in question and "5%" in question):
        try:
            content = call_llm(
                [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "final_answer": context.final_answer,
                                "steps": [step.__dict__ for step in context.steps],
                                "chart_refs": context.chart_refs,
                            },
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                ],
                system_prompt=(
                    "你回答证券公司管理会计 Agent 的追问。只能引用上下文已有事实，"
                    "不得新增金额、业务线、营业部或指标。金额单位保持万元。"
                ),
            )
            if content.strip():
                return content.strip()
        except Exception:
            pass

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
        result = simulate_brokerage_recovery(period, trade_volume_change_pct=0.05)
        return (
            f"按本地 What-if 函数测算，交易量恢复 5% 将增加经纪收入约 {_format_amount(result['revenue_impact'])}，"
            f"利润改善约 {_format_amount(result['profit_impact'])}。公式为：模拟交易量 × 模拟佣金率 - 基准收入。"
        )
    return f"当前上下文可回答 PVM 影响、业务线差异、营业部利润率和管理建议。已观察到：{combined_observation[:180]}..."
