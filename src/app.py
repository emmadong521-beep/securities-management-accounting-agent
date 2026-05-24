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
from src.ui import (
    format_wan,
    inject_global_css,
    reason_tag_color,
    render_info_card,
    render_kpi_card,
    render_page_header,
    render_section_title,
)
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
inject_global_css()
render_page_header(
    "证券公司管理会计多维经营分析 Agent",
    "业务线利润贡献、经纪业务 PVM、营业部盈利穿透、What-if 模拟、经营报告生成",
)

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


def _data_quality_status() -> str:
    report_path = Path(__file__).resolve().parents[1] / "data" / "output" / "data_quality_report.json"
    if not report_path.exists():
        return "WARNING"
    try:
        return json.loads(report_path.read_text(encoding="utf-8")).get("status", "WARNING")
    except json.JSONDecodeError:
        return "WARNING"


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
    render_section_title("可解释分析轨迹", "🧭")
    st.caption("展示任务理解、分析计划、工具调用轨迹、观察结果、分析判断和综合结论。")
    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi_card("分析步骤数", str(len(trace.steps)), status="PASS")
    with c2:
        render_kpi_card("工具调用次数", str(sum(1 for step in trace.steps if step.tool_name)), status="PASS")
    with c3:
        render_kpi_card("总耗时", f"{(trace.elapsed_ms or 0) / 1000:.2f}s", status="PASS")
    render_info_card("最终结论", trace.final_answer, icon="✅", border_color="#059669")
    st.markdown("**任务输入**")
    st.write(trace.user_task)
    for step in trace.steps:
        step_type = step.step_type.value
        icon = TRACE_ICONS.get(step_type, "•")
        with st.expander(f"{icon} 步骤 {step.step_no}｜{step_type}｜{step.title}", expanded=step.step_type.value == "综合结论"):
            render_info_card(step.title, step.detail, icon=icon, border_color="#1F4E79")
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
        render_section_title("推荐演示路径", "🧭")
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


def build_agent_related_chart_flags(result) -> dict:
    refs = " ".join(str(item) for item in (getattr(result, "chart_refs", None) or []))
    text = " ".join(
        [
            refs,
            str(getattr(result, "user_task", "") or ""),
            str(getattr(result, "final_answer", "") or ""),
        ]
    ).lower()
    chinese_text = text
    show_what_if = any(keyword in chinese_text for keyword in ["what-if", "what if", "如果", "交易量恢复", "交易量", "佣金率"])
    show_high_low = any(keyword in chinese_text for keyword in ["高收入", "低利润", "盈利穿透", "利润率偏低", "营业部盈利穿透"])
    show_pvm = any(keyword in chinese_text for keyword in ["pvm", "经纪", "交易量影响", "佣金率影响", "预算 vs 实际"])
    show_bizline = any(keyword in chinese_text for keyword in ["业务线", "利润低于预算", "利润贡献", "公司利润", "经营利润"])
    show_branch_scatter = any(keyword in chinese_text for keyword in ["营业部", "利润率", "branch", "收入 vs 经营利润率"])
    is_profit_variance = any(keyword in chinese_text for keyword in ["利润低于预算", "公司利润", "主要原因"])

    if not refs and not any([show_what_if, show_high_low, show_pvm, show_bizline, show_branch_scatter]):
        show_bizline = True
        show_pvm = True
        show_branch_scatter = True

    if is_profit_variance:
        show_bizline = True
        show_pvm = True
        show_branch_scatter = True
    if show_high_low:
        show_branch_scatter = True
    if show_what_if:
        show_pvm = True
    if "top negative" in chinese_text or "明细" in chinese_text or show_pvm:
        show_pvm_detail = True
    else:
        show_pvm_detail = False

    return {
        "show_bizline": show_bizline,
        "show_pvm": show_pvm,
        "show_pvm_detail": show_pvm_detail,
        "show_branch_scatter": show_branch_scatter,
        "show_high_low": show_high_low,
        "show_what_if": show_what_if,
    }


def _render_agent_related_charts(result, period: str) -> None:
    flags = build_agent_related_chart_flags(result)
    if not any(flags.values()):
        st.info("当前任务没有匹配到可展示的关联图表。")
        return

    if flags["show_bizline"]:
        try:
            chart_biz = calculate_bizline_profitability(period)
            if chart_biz.empty:
                st.info("当前期间无相关数据")
            else:
                render_section_title("业务线利润贡献", "📊")
                plot_df = chart_biz.assign(**{"经营利润（万元）": chart_biz["operating_profit"] / 10000})
                fig = px.bar(plot_df, x="biz_line_id", y="经营利润（万元）", title="业务线利润贡献（万元）")
                fig.update_yaxes(title="经营利润（万元）")
                st.plotly_chart(fig, width="stretch")
                st.dataframe(_amount_view(chart_biz), width="stretch")
                render_info_card("业务解读", "该图展示各业务线在费用分摊后的经营利润贡献，用于定位主要利润来源。", icon="📌")
        except Exception as exc:
            st.warning(f"业务线利润贡献图渲染失败：{exc}")

    if flags["show_pvm"]:
        try:
            chart_pvm = run_pvm_analysis(period, "BROKERAGE")
            if chart_pvm.empty:
                st.info("当前期间无相关数据")
            else:
                render_section_title("PVM 瀑布图", "🌊")
                p = chart_pvm.iloc[0]
                waterfall = go.Figure(
                    go.Waterfall(
                        name="PVM",
                        orientation="v",
                        measure=["absolute", "relative", "relative", "relative", "total"],
                        x=["预算收入", "交易量影响", "佣金率影响", "混合影响", "实际收入"],
                        y=[
                            p["budget_revenue"] / 10000,
                            p["volume_effect"] / 10000,
                            p["rate_effect"] / 10000,
                            p["mix_effect"] / 10000,
                            p["actual_revenue"] / 10000,
                        ],
                    )
                )
                waterfall.update_layout(title="PVM 瀑布图（万元）", yaxis_title="金额（万元）")
                st.plotly_chart(waterfall, width="stretch")
                render_info_card("业务解读", "PVM 将经纪业务收入差异拆分为交易量、佣金率和混合影响，便于区分市场活跃度和定价因素。", icon="🧮")
        except Exception as exc:
            st.warning(f"PVM 瀑布图渲染失败：{exc}")

    if flags["show_pvm_detail"]:
        try:
            detail = get_pvm_detail(period)
            render_section_title("Top negative variance 明细", "📉")
            if detail.empty:
                st.info("当前期间无相关数据")
            else:
                st.dataframe(_amount_view(detail.sort_values("total_variance").head(10)), width="stretch")
                render_info_card("业务解读", "负向差异明细用于定位经纪收入缺口集中的营业部、客户分层和产品类型。", icon="🔎")
        except Exception as exc:
            st.warning(f"PVM 明细表渲染失败：{exc}")

    if flags["show_branch_scatter"]:
        try:
            chart_branch = calculate_branch_profitability(period)
            render_section_title("营业部收入 vs 经营利润率", "🏦")
            if chart_branch.empty:
                st.info("当前期间无相关数据")
            else:
                scatter_df = chart_branch.assign(**{"收入（万元）": chart_branch["revenue"] / 10000})
                fig = px.scatter(
                    scatter_df,
                    x="收入（万元）",
                    y="operating_margin",
                    size=chart_branch["operating_profit"].clip(lower=1),
                    color="branch_id",
                    title="营业部收入 vs 经营利润率",
                )
                fig.update_xaxes(title="收入（万元）")
                fig.update_yaxes(title="经营利润率")
                st.plotly_chart(fig, width="stretch")
                render_info_card("业务解读", "该散点图用于识别收入规模较高但费用分摊后利润率偏低的营业部。", icon="🔎")
        except Exception as exc:
            st.warning(f"营业部散点图渲染失败：{exc}")

    if flags["show_high_low"]:
        try:
            high_low = detect_high_revenue_low_profit_branches(period)
            render_section_title("高收入低利润营业部", "🚨")
            if high_low.empty:
                st.info("当前期间无相关数据")
            else:
                st.dataframe(_amount_view(high_low), width="stretch")
                for row in high_low.head(3).itertuples():
                    tag_text = str(getattr(row, "reason_tags", ""))
                    render_info_card(
                        f"{getattr(row, 'branch_name', getattr(row, 'branch_id', '营业部'))}",
                        f"收入：{format_wan(getattr(row, 'revenue', 0))}；经营利润率：{getattr(row, 'operating_margin', 0):.2%}；原因标签：{tag_text}",
                        icon="⚠️",
                        border_color=reason_tag_color(tag_text),
                    )
                render_info_card("业务解读", "高收入低利润清单用于识别收入规模与真实利润贡献不匹配的营业部。", icon="📌")
        except Exception as exc:
            st.warning(f"高收入低利润表渲染失败：{exc}")

    if flags["show_what_if"]:
        try:
            scenario = simulate_brokerage_recovery(period, trade_volume_change_pct=0.05)
            render_section_title("What-if 模拟结果", "🧪")
            c1, c2 = st.columns(2)
            with c1:
                render_kpi_card("收入影响", format_wan(scenario["revenue_impact"]), status="PASS" if scenario["revenue_impact"] >= 0 else "MEDIUM")
            with c2:
                render_kpi_card("利润影响", format_wan(scenario["profit_impact"]), status="PASS" if scenario["profit_impact"] >= 0 else "MEDIUM")
            waterfall = go.Figure(
                go.Waterfall(
                    name="What-if",
                    orientation="v",
                    measure=["absolute", "relative", "relative", "total"],
                    x=["基准收入", "收入影响", "费用增量影响", "利润影响"],
                    y=[
                        scenario["base_revenue"] / 10000,
                        scenario["revenue_impact"] / 10000,
                        -(scenario["simulated_expense"] - scenario["base_expense"]) / 10000,
                        scenario["profit_impact"] / 10000,
                    ],
                )
            )
            waterfall.update_layout(title="What-if 模拟结果（万元）", yaxis_title="金额（万元）")
            st.plotly_chart(waterfall, width="stretch")
            render_info_card("业务解读", scenario["explanation"], icon="🧮")
        except Exception as exc:
            st.warning(f"What-if 模拟图渲染失败：{exc}")


if page == "CFO 首页看板":
    _recommended_demo_path()
    recon_status = get_recon_data_status()
    st.info(f"数据来源状态：当前使用：{recon_status['source']}。{recon_status['message']}")
    brokerage_variance = run_brokerage_budget_variance(period)
    profit_budget_variance = float(brokerage_variance["profit_variance"].sum())
    insight_count = len(detect_management_insights(period))
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        render_kpi_card("营业收入", format_wan(biz["revenue"].sum()), status="PASS")
    with c2:
        render_kpi_card("经营利润", format_wan(biz["operating_profit"].sum()), status="PASS")
    with c3:
        render_kpi_card("利润预算差异", format_wan(profit_budget_variance), status="MEDIUM" if profit_budget_variance < 0 else "PASS")
    with c4:
        render_kpi_card("经纪业务差异", format_wan(pvm["total_variance"].iloc[0]), status="MEDIUM" if pvm["total_variance"].iloc[0] < 0 else "PASS")
    with c5:
        render_kpi_card("管理洞察数", str(insight_count), status="PASS", help_text=f"数据质量 {_data_quality_status()}")
    biz_chart = biz.assign(**{"经营利润（万元）": biz["operating_profit"] / 10000})
    fig = px.bar(biz_chart, x="biz_line_id", y="经营利润（万元）", title="业务线利润贡献（万元）")
    fig.update_yaxes(title="经营利润（万元）")
    st.plotly_chart(fig, width="stretch")
    render_info_card(
        "业务解读",
        "利润贡献按实际收入、直接成本和分摊费用计算，用于观察不同业务线的分摊后贡献。",
        icon="📊",
    )
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
    render_info_card("图表解读", "横轴越靠右表示收入规模越高，纵轴越高表示费用分摊后的利润率越高。", icon="🔎")
    st.subheader("管理洞察")
    insight_df = detect_management_insights(period)
    for row in insight_df.itertuples():
        with st.container(border=True):
            st.markdown(f"**{row.title}**")
            st.write(row.finding)
            st.caption(f"影响金额：{row.financial_impact / 10000:,.2f} 万元；建议：{row.recommendation}")

elif page == "业务线利润贡献分析":
    render_section_title("业务线利润贡献分析", "📊")
    st.dataframe(_amount_view(biz), width="stretch")
    plot_df = biz.assign(**{"收入（万元）": biz["revenue"] / 10000, "经营利润（万元）": biz["operating_profit"] / 10000})
    fig = px.bar(plot_df, x="biz_line_id", y=["收入（万元）", "经营利润（万元）"], barmode="group", title="业务线收入与利润（万元）")
    fig.update_yaxes(title="金额（万元）")
    st.plotly_chart(fig, width="stretch")
    render_info_card(
        "业务解读",
        "该图对比业务线收入和分摊后经营利润，突出规模与分摊后利润贡献之间的差异。",
        icon="📌",
    )

elif page == "经纪业务预实差异归因":
    render_section_title("经纪业务预实差异归因", "🌊")
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
    render_info_card("业务解读", "PVM 将经纪佣金收入差异拆为交易量影响、佣金率影响和混合影响，金额由代码计算。", icon="🧮")
    grouped = variance.groupby("branch_id", as_index=False)[["budget_revenue", "actual_revenue"]].sum()
    grouped["预算收入（万元）"] = grouped["budget_revenue"] / 10000
    grouped["实际收入（万元）"] = grouped["actual_revenue"] / 10000
    fig = px.bar(grouped, x="branch_id", y=["预算收入（万元）", "实际收入（万元）"], barmode="group", title="经纪业务预算 vs 实际（万元）")
    fig.update_yaxes(title="金额（万元）")
    st.plotly_chart(fig, width="stretch")
    render_info_card("预算 vs 实际解读", "预算与实际对比用于定位收入缺口集中在哪些营业部。", icon="📉")
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
    render_section_title("营业部盈利穿透分析", "🏦")
    st.subheader("收入排名 vs 经营利润率排名")
    gap = calculate_revenue_margin_rank_gap(period)
    high_low = detect_high_revenue_low_profit_branches(period)
    st.dataframe(_amount_view(gap.sort_values("revenue_rank")), width="stretch")
    st.subheader("高收入低利润营业部清单")
    st.dataframe(_amount_view(high_low), width="stretch")
    if not high_low.empty:
        render_section_title("高收入低利润重点营业部", "🚨")
        for row in high_low.head(3).itertuples():
            tag_text = str(getattr(row, "reason_tags", ""))
            render_info_card(
                f"{getattr(row, 'branch_name', getattr(row, 'branch_id', '营业部'))}",
                f"收入：{format_wan(getattr(row, 'revenue', 0))}；经营利润率：{getattr(row, 'operating_margin', 0):.2%}；原因标签：{tag_text}",
                icon="⚠️",
                border_color=reason_tag_color(tag_text),
            )
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
    render_info_card("散点图解读", "右侧但位置偏低的营业部表示收入规模较高，但费用分摊后利润率偏低。", icon="🔎")
    if not gap.empty:
        selected_branch = st.selectbox("选择营业部", gap["branch_id"].tolist(), format_func=lambda bid: f"{bid} - {gap[gap['branch_id'] == bid]['branch_name'].iloc[0]}")
        detail = explain_high_revenue_low_profit_branch(period, selected_branch)
        with st.container(border=True):
            render_section_title("单个营业部原因解释", "🧾")
            render_info_card("原因解释", detail["explanation"], icon="📌")
            render_info_card("建议动作", detail["recommendation"], icon="✅", border_color="#059669")
        expense_cols = ["salary_expense", "rent_expense", "marketing_expense", "it_allocated_expense", "market_data_allocated_expense", "hq_allocated_expense"]
        row = gap[gap["branch_id"] == selected_branch].iloc[0]
        expense_df = pd.DataFrame({"费用类型": expense_cols, "金额（万元）": [float(row.get(col, 0)) / 10000 for col in expense_cols]})
        pie = px.pie(expense_df, names="费用类型", values="金额（万元）", title="费用分摊结构（万元）")
        st.plotly_chart(pie, width="stretch")
        st.caption("费用结构图用于判断低利润率来自系统、行情、总部、营销还是基础运营成本。")

elif page == "What-if 情景模拟":
    render_section_title("What-if 情景模拟", "🧪")
    control_col, result_col = st.columns([1, 2])
    with control_col:
        render_info_card("参数控制", "调整交易量、佣金率和费用假设，右侧实时展示代码测算结果。", icon="⚙️")
        trade_pct = st.slider("交易量变化", min_value=-0.20, max_value=0.30, value=0.05, step=0.01)
        rate_bp = st.number_input("佣金率变化（bp）", value=0.0, step=0.5)
        expense_pct = st.slider("费用变化", min_value=-0.10, max_value=0.20, value=0.0, step=0.01)
    result = simulate_brokerage_recovery(period, trade_pct, rate_bp, expense_pct)
    simulated_profit = result["simulated_revenue"] - result["simulated_expense"]
    with result_col:
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            render_kpi_card("收入影响", format_wan(result["revenue_impact"]), status="PASS" if result["revenue_impact"] >= 0 else "MEDIUM")
        with k2:
            render_kpi_card("利润影响", format_wan(result["profit_impact"]), status="PASS" if result["profit_impact"] >= 0 else "MEDIUM")
        with k3:
            render_kpi_card("模拟收入", format_wan(result["simulated_revenue"]), status="PASS")
        with k4:
            render_kpi_card("模拟利润", format_wan(simulated_profit), status="PASS" if simulated_profit >= 0 else "MEDIUM")
    waterfall = go.Figure(go.Waterfall(
        name="What-if",
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["基准收入", "收入影响", "费用增量影响", "模拟利润影响"],
        y=[result["base_revenue"] / 10000, result["revenue_impact"] / 10000, -(result["simulated_expense"] - result["base_expense"]) / 10000, result["profit_impact"] / 10000],
    ))
    waterfall.update_layout(title="What-if 收入与利润影响（万元）", yaxis_title="金额（万元）")
    st.plotly_chart(waterfall, width="stretch")
    render_info_card("情景模拟解读", result["explanation"], icon="🧮")

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
    if st.button("导出 Markdown CFO 报告", type="primary"):
        output_path = export_cfo_report(period)
        st.success(f"已导出：{output_path}")

else:
    render_section_title("Agent 工作台", "🤖")
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

    if st.button("运行 Agent", type="primary"):
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
            render_section_title("最终经营结论", "✅")
            render_info_card("经营结论", result.final_answer, icon="✅", border_color="#059669")
            if result.report_path:
                st.caption(f"报告路径：{result.report_path}")

        st.subheader("关联图表")
        _render_agent_related_charts(result, agent_period)

        followup = st.text_input("追问", placeholder="例如：交易量影响和佣金率影响哪个更大？有什么管理建议？")
        if followup:
            st.write(answer_management_followup(followup, result, use_llm=st.session_state.get("management_agent_use_llm", use_llm)))
