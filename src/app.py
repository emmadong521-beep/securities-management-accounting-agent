from __future__ import annotations

from dataclasses import asdict
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.agent import answer_management_followup, run_management_accounting_agent, run_management_accounting_agent_with_trace
from src.db import load_synthetic_data_to_duckdb
from src.llm_client import explain_llm_config_status, is_llm_available, load_llm_config
from src.profitability_insights import (
    calculate_revenue_margin_rank_gap,
    detect_high_revenue_low_profit_branches,
    explain_high_revenue_low_profit_branch,
)
from src.recon_data_loader import get_recon_data_status
from src.validation import (
    calculate_bizline_profitability,
    calculate_branch_profitability,
    detect_management_insights,
    export_cfo_report,
    generate_cfo_report_mock,
    get_pvm_detail,
    run_brokerage_budget_variance,
    run_pvm_analysis,
)
from src.what_if import simulate_brokerage_recovery


st.set_page_config(page_title="证券公司管理会计多维经营分析 Agent", layout="wide")
st.title("证券公司管理会计多维经营分析 Agent")

load_synthetic_data_to_duckdb()
period = st.sidebar.selectbox("分析期间", [f"2025-{m:02d}" for m in range(1, 13)], index=8)
page = st.sidebar.radio(
    "功能",
    [
        "CFO 首页看板",
        "业务线利润贡献分析",
        "经纪业务预实差异归因",
        "营业部盈利能力排名",
        "营业部盈利穿透分析",
        "What-if 情景模拟",
        "多维下钻筛选器",
        "自动生成 CFO 月度经营分析报告",
        "Agent 工作台",
    ],
)

biz = calculate_bizline_profitability(period)
branch = calculate_branch_profitability(period)
pvm = run_pvm_analysis(period, "BROKERAGE")

AMOUNT_COLUMNS = {
    "budget_revenue",
    "budget_direct_cost",
    "budget_allocated_expense",
    "budget_profit",
    "actual_revenue",
    "actual_direct_cost",
    "actual_allocated_expense",
    "actual_profit",
    "revenue",
    "direct_cost",
    "allocated_expense",
    "operating_profit",
    "total_variance",
    "volume_effect",
    "rate_effect",
    "mix_effect",
    "revenue_variance",
    "profit_variance",
    "financial_impact",
    "revenue_impact",
    "profit_impact",
    "base_revenue",
    "simulated_revenue",
    "base_expense",
    "simulated_expense",
}


def _amount_view(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename = {}
    for col in AMOUNT_COLUMNS.intersection(out.columns):
        out[col] = out[col].astype(float) / 10000
        rename[col] = f"{col}（万元）"
    return out.rename(columns=rename)


def _agent_steps_view(result) -> pd.DataFrame:
    rows = []
    for step in result.steps:
        row = asdict(step)
        row["tool_input"] = str(row["tool_input"])
        rows.append(row)
    return pd.DataFrame(rows)


TRACE_ICONS = {
    "意图识别": "🎯",
    "制定计划": "📝",
    "工具调用": "🔧",
    "观察结果": "👁️",
    "分析判断": "🧠",
    "综合结论": "✅",
}


def _render_trace_payload(payload) -> None:
    if isinstance(payload, dict) and payload.get("type") == "DataFrame":
        st.json({key: value for key, value in payload.items() if key != "preview"})
        if payload.get("preview"):
            st.dataframe(pd.DataFrame(payload["preview"]), width="stretch")
    elif isinstance(payload, dict) and payload.get("type") == "list":
        st.json({key: value for key, value in payload.items() if key != "preview"})
        if payload.get("preview"):
            st.json(payload["preview"])
    elif payload is not None:
        st.json(payload)


def _render_explainable_trace(trace) -> None:
    trace_dict = trace.to_dict()
    st.subheader("可解释分析轨迹")
    st.caption("展示任务理解、分析计划、工具调用轨迹、观察结果、分析判断和综合结论。")
    c1, c2, c3 = st.columns(3)
    c1.metric("分析步骤数", len(trace.steps))
    c2.metric("工具调用次数", sum(1 for step in trace.steps if step.tool_name))
    c3.metric("总耗时", f"{(trace.elapsed_ms or 0) / 1000:.2f}s")
    with st.container(border=True):
        st.subheader("最终结论")
        st.write(trace.final_answer)
    st.markdown("**任务输入**")
    st.write(trace.user_task)
    for step in trace.steps:
        step_type = step.step_type.value
        icon = TRACE_ICONS.get(step_type, "•")
        with st.expander(f"{icon} 步骤 {step.step_no}｜{step_type}｜{step.title}", expanded=step.step_type.value == "综合结论"):
            st.write(step.detail)
            if step.tool_name:
                st.markdown("**工具调用轨迹**")
                st.json({"tool_name": step.tool_name, "tool_input": step.tool_input or {}})
            if step.result_summary is not None:
                st.markdown("**观察结果**")
                _render_trace_payload(step.result_summary)
            if step.key_numbers:
                st.markdown("**关键数字**")
                st.json(step.key_numbers)
    st.download_button(
        "下载 trace JSON",
        data=json.dumps(trace_dict, ensure_ascii=False, indent=2, default=str),
        file_name="management_agent_trace.json",
        mime="application/json",
    )


def _recommended_demo_path() -> None:
    with st.container(border=True):
        st.subheader("推荐演示路径")
        st.markdown(
            """
1. 从“CFO 首页看板”查看营业收入、经营利润、经纪收入差异和管理洞察数量。
2. 进入“业务线利润贡献分析”，比较收入规模与分摊后利润贡献。
3. 打开“经纪业务预实差异归因”，用营业部、客户分层、产品类型筛选 PVM 明细。
4. 查看“营业部盈利能力排名”，识别收入高但利润率偏低的营业部。
5. 在“自动生成 CFO 月度经营分析报告”中导出 Markdown 报告。
            """
        )


def _llm_status_text(use_llm: bool) -> str:
    status = explain_llm_config_status()
    if use_llm and status["available"]:
        return "当前模式：Volcengine Ark LLM Agent"
    if use_llm and not status["available"]:
        return "当前模式：LLM 配置不完整，已回退 Mock Agent"
    return "当前模式：Mock Agent"


def _show_llm_config_status() -> None:
    status = explain_llm_config_status()
    display_status = {
        "mode": status["mode"],
        "provider": status["provider"],
        "base_url": status["base_url"],
        "model": status["model"],
        "missing_fields": status["missing_fields"],
        "message": status["message"],
        "api_key": "已配置" if status.get("api_key_configured") else "未配置",
    }
    with st.expander("LLM 配置状态"):
        st.json(display_status)


if page == "CFO 首页看板":
    _recommended_demo_path()
    recon_status = get_recon_data_status()
    st.info(f"数据来源状态：当前使用：{recon_status['source']}。{recon_status['message']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("营业收入", f"{biz['revenue'].sum()/10000:,.0f} 万元")
    c2.metric("经营利润", f"{biz['operating_profit'].sum()/10000:,.0f} 万元")
    c3.metric("经纪收入差异", f"{pvm['total_variance'].iloc[0]/10000:,.0f} 万元")
    c4.metric("洞察数量", len(detect_management_insights(period)))
    biz_chart = biz.assign(**{"经营利润（万元）": biz["operating_profit"] / 10000})
    fig = px.bar(biz_chart, x="biz_line_id", y="经营利润（万元）", title="业务线利润贡献（万元）")
    fig.update_yaxes(title="经营利润（万元）")
    st.plotly_chart(fig, width="stretch")
    st.caption("利润贡献按实际收入、直接成本和分摊费用计算，用于观察不同业务线的分摊后贡献。")
    branch_chart = branch.assign(**{"收入（万元）": branch["revenue"] / 10000})
    scatter = px.scatter(
        branch_chart,
        x="收入（万元）",
        y="operating_margin",
        size=branch["operating_profit"].clip(lower=1),
        color="branch_id",
        title="营业部收入 vs 经营利润率（收入单位：万元）",
    )
    scatter.update_xaxes(title="收入（万元）")
    scatter.update_yaxes(title="经营利润率")
    st.plotly_chart(scatter, width="stretch")
    st.caption("横轴越靠右表示收入规模越高，纵轴越高表示费用分摊后的利润率越高。")
    st.subheader("管理洞察")
    insight_df = detect_management_insights(period)
    for row in insight_df.itertuples():
        with st.container(border=True):
            st.markdown(f"**{row.title}**")
            st.write(row.finding)
            st.caption(f"影响金额：{row.financial_impact / 10000:,.2f} 万元；建议：{row.recommendation}")

elif page == "业务线利润贡献分析":
    st.dataframe(_amount_view(biz), width="stretch")
    plot_df = biz.assign(**{"收入（万元）": biz["revenue"] / 10000, "经营利润（万元）": biz["operating_profit"] / 10000})
    fig = px.bar(plot_df, x="biz_line_id", y=["收入（万元）", "经营利润（万元）"], barmode="group", title="业务线收入与利润（万元）")
    fig.update_yaxes(title="金额（万元）")
    st.plotly_chart(fig, width="stretch")
    st.caption("该图对比业务线收入和分摊后经营利润，突出规模与真实利润贡献之间的差异。")

elif page == "经纪业务预实差异归因":
    variance = run_brokerage_budget_variance(period)
    pvm_all = get_pvm_detail(period)
    branch_options = ["ALL"] + sorted(pvm_all["branch_id"].dropna().unique().tolist())
    segment_options = ["ALL"] + sorted(pvm_all["customer_segment"].dropna().unique().tolist())
    product_options = ["ALL"] + sorted(pvm_all["product_type"].dropna().unique().tolist())
    f1, f2, f3 = st.columns(3)
    selected_branch = f1.selectbox("营业部", branch_options)
    selected_segment = f2.selectbox("客户分层", segment_options)
    selected_product = f3.selectbox("产品类型", product_options)
    detail = get_pvm_detail(period, selected_branch, selected_segment, selected_product)
    pvm_filtered = run_pvm_analysis(period, "BROKERAGE", selected_branch, selected_segment, selected_product)
    st.subheader("PVM 汇总表")
    st.dataframe(_amount_view(pvm_filtered), width="stretch")
    st.subheader("PVM 明细表")
    st.dataframe(_amount_view(detail), width="stretch")
    p = pvm_filtered.iloc[0]
    waterfall = go.Figure(go.Waterfall(
        name="PVM",
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "total"],
        x=["预算收入", "交易量影响", "佣金率影响", "混合影响", "实际收入"],
        y=[p["budget_revenue"] / 10000, p["volume_effect"] / 10000, p["rate_effect"] / 10000, p["mix_effect"] / 10000, p["actual_revenue"] / 10000],
    ))
    waterfall.update_layout(title="PVM 瀑布图（万元）", yaxis_title="金额（万元）")
    st.plotly_chart(waterfall, width="stretch")
    st.caption("PVM 将经纪佣金收入差异拆为交易量影响、佣金率影响和混合影响，金额由代码计算。")
    grouped = variance.groupby("branch_id", as_index=False)[["budget_revenue", "actual_revenue"]].sum()
    grouped["预算收入（万元）"] = grouped["budget_revenue"] / 10000
    grouped["实际收入（万元）"] = grouped["actual_revenue"] / 10000
    fig = px.bar(grouped, x="branch_id", y=["预算收入（万元）", "实际收入（万元）"], barmode="group", title="经纪业务预算 vs 实际（万元）")
    fig.update_yaxes(title="金额（万元）")
    st.plotly_chart(fig, width="stretch")
    st.caption("预算与实际对比用于定位收入缺口集中在哪些营业部。")
    st.subheader("Top negative variance 明细")
    st.dataframe(_amount_view(detail.sort_values("total_variance").head(10)), width="stretch")
    st.subheader("自动经营解释")
    st.write(p["explanation"])

elif page == "营业部盈利能力排名":
    st.dataframe(_amount_view(branch.sort_values("profit_rank")), width="stretch")
    rank_df = branch.sort_values("profit_rank").assign(**{"经营利润（万元）": branch["operating_profit"] / 10000})
    fig = px.bar(rank_df, x="branch_id", y="经营利润（万元）", color="operating_margin", title="营业部盈利能力排名（万元）")
    fig.update_yaxes(title="经营利润（万元）")
    st.plotly_chart(fig, width="stretch")
    st.caption("排名表基于费用分摊后的经营利润，避免只看收入规模。")

elif page == "营业部盈利穿透分析":
    st.subheader("收入排名 vs 经营利润率排名")
    gap = calculate_revenue_margin_rank_gap(period)
    high_low = detect_high_revenue_low_profit_branches(period)
    st.dataframe(_amount_view(gap.sort_values("revenue_rank")), width="stretch")
    st.subheader("高收入低利润营业部清单")
    st.dataframe(_amount_view(high_low), width="stretch")
    scatter_df = gap.assign(**{"收入（万元）": gap["revenue"] / 10000})
    fig = px.scatter(
        scatter_df,
        x="收入（万元）",
        y="operating_margin",
        color="reason_tags" if "reason_tags" in scatter_df.columns else "branch_id",
        size="allocated_expense",
        hover_name="branch_name",
        title="营业部收入 vs 经营利润率（收入单位：万元）",
    )
    fig.update_xaxes(title="收入（万元）")
    fig.update_yaxes(title="经营利润率")
    st.plotly_chart(fig, width="stretch")
    st.caption("右侧但位置偏低的营业部表示收入规模较高，但费用分摊后利润率偏低。")
    if not gap.empty:
        selected_branch = st.selectbox("选择营业部", gap["branch_id"].tolist(), format_func=lambda bid: f"{bid} - {gap[gap['branch_id'] == bid]['branch_name'].iloc[0]}")
        detail = explain_high_revenue_low_profit_branch(period, selected_branch)
        with st.container(border=True):
            st.subheader("单个营业部原因解释")
            st.write(detail["explanation"])
            st.write(f"建议：{detail['recommendation']}")
        expense_cols = ["salary_expense", "rent_expense", "marketing_expense", "it_allocated_expense", "market_data_allocated_expense", "hq_allocated_expense"]
        row = gap[gap["branch_id"] == selected_branch].iloc[0]
        expense_df = pd.DataFrame({"费用类型": expense_cols, "金额（万元）": [float(row.get(col, 0)) / 10000 for col in expense_cols]})
        pie = px.pie(expense_df, names="费用类型", values="金额（万元）", title="费用分摊结构（万元）")
        st.plotly_chart(pie, width="stretch")
        st.caption("费用结构图用于判断低利润率来自系统、行情、总部、营销还是基础运营成本。")

elif page == "What-if 情景模拟":
    st.subheader("What-if 情景模拟")
    c1, c2, c3 = st.columns(3)
    trade_pct = c1.slider("交易量变化", min_value=-0.20, max_value=0.30, value=0.05, step=0.01)
    rate_bp = c2.number_input("佣金率变化（bp）", value=0.0, step=0.5)
    expense_pct = c3.slider("费用变化", min_value=-0.10, max_value=0.20, value=0.0, step=0.01)
    result = simulate_brokerage_recovery(period, trade_pct, rate_bp, expense_pct)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("收入影响", f"{result['revenue_impact']/10000:,.2f} 万元")
    k2.metric("利润影响", f"{result['profit_impact']/10000:,.2f} 万元")
    k3.metric("模拟收入", f"{result['simulated_revenue']/10000:,.2f} 万元")
    k4.metric("模拟费用", f"{result['simulated_expense']/10000:,.2f} 万元")
    waterfall = go.Figure(go.Waterfall(
        name="What-if",
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["基准收入", "收入影响", "费用增量影响", "模拟利润影响"],
        y=[result["base_revenue"] / 10000, result["revenue_impact"] / 10000, -(result["simulated_expense"] - result["base_expense"]) / 10000, result["profit_impact"] / 10000],
    ))
    waterfall.update_layout(title="What-if 收入与利润影响（万元）", yaxis_title="金额（万元）")
    st.plotly_chart(waterfall, width="stretch")
    st.caption("情景模拟用交易量、佣金率和费用变化计算收入与利润影响，金额由代码完成。")
    st.write(result["explanation"])

elif page == "多维下钻筛选器":
    selected_biz = st.multiselect("业务线", biz["biz_line_id"].tolist(), default=biz["biz_line_id"].tolist())
    selected_branch = st.multiselect("营业部", branch["branch_id"].tolist(), default=branch["branch_id"].tolist())
    filtered = biz[biz["biz_line_id"].isin(selected_biz)]
    st.dataframe(_amount_view(filtered), width="stretch")
    fig = px.bar(filtered, x="biz_line_id", y="profit_contribution_rate", title="利润贡献率")
    fig.update_yaxes(title="利润贡献率")
    st.plotly_chart(fig, width="stretch")
    st.caption("利润贡献率用于判断各业务线在分摊后利润池中的相对贡献。")
    st.dataframe(_amount_view(branch[branch["branch_id"].isin(selected_branch)]), width="stretch")

elif page == "自动生成 CFO 月度经营分析报告":
    report = generate_cfo_report_mock(period)
    st.markdown(report)
    if st.button("导出 Markdown CFO 报告"):
        output_path = export_cfo_report(period)
        st.success(f"已导出：{output_path}")

else:
    st.subheader("Agent 工作台")
    st.caption("输入自然语言任务，Agent 会自动生成分析计划、调用管理会计分析工具，并展示观察结果和最终经营结论。")
    llm_config = load_llm_config()
    use_llm = st.checkbox("使用 LLM 增强回答", value=llm_config.enabled)
    st.info(_llm_status_text(use_llm))
    _show_llm_config_status()
    if use_llm and is_llm_available():
        st.caption(f"当前模型：{llm_config.model}")
    elif use_llm and llm_config.enabled:
        st.warning("LLM 配置不完整，页面将自动使用 Mock Agent。")
    default_task = f"请分析 {period} 公司利润低于预算的主要原因。"
    user_task = st.text_area("自然语言任务", value=default_task, height=100)
    agent_period = st.selectbox("Agent 分析期间", [f"2025-{m:02d}" for m in range(1, 13)], index=int(period[-2:]) - 1)

    if st.button("运行 Agent"):
        st.session_state["management_agent_use_llm"] = use_llm
        st.session_state["management_agent_result"] = run_management_accounting_agent(user_task, agent_period, use_llm=use_llm)
        st.session_state["management_agent_trace"] = run_management_accounting_agent_with_trace(user_task, agent_period)

    result = st.session_state.get("management_agent_result")
    if result:
        if result.llm_error:
            st.warning(result.llm_error)
        trace = st.session_state.get("management_agent_trace")
        if trace:
            _render_explainable_trace(trace)
        st.subheader("Agent 分析计划")
        for idx, item in enumerate(result.plan, start=1):
            st.markdown(f"{idx}. {item}")

        st.subheader("工具调用轨迹")
        st.dataframe(_agent_steps_view(result), width="stretch")

        st.subheader("每一步观察结果")
        for step in result.steps:
            with st.expander(f"步骤 {step.step_no}：{step.tool_name}"):
                st.markdown(f"**规划意图：** {step.thought}")
                st.json(step.tool_input)
                st.write(step.observation)

        with st.container(border=True):
            st.subheader("最终经营结论")
            st.write(result.final_answer)
            if result.report_path:
                st.caption(f"报告路径：{result.report_path}")

        if result.chart_refs:
            st.subheader("关联图表")
            for chart in result.chart_refs:
                st.markdown(f"- {chart}")

        followup = st.text_input("追问", placeholder="例如：交易量影响和佣金率影响哪个更大？有什么管理建议？")
        if followup:
            st.write(answer_management_followup(followup, result, use_llm=st.session_state.get("management_agent_use_llm", use_llm)))
