from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.db import load_synthetic_data_to_duckdb
from src.validation import (
    calculate_bizline_profitability,
    calculate_branch_profitability,
    detect_management_insights,
    generate_cfo_report_mock,
    get_pvm_detail,
    run_brokerage_budget_variance,
    run_pvm_analysis,
)


st.set_page_config(page_title="证券公司管理会计多维经营分析 Agent", layout="wide")
st.title("证券公司管理会计多维经营分析 Agent")

load_synthetic_data_to_duckdb()
period = st.sidebar.selectbox("分析期间", [f"2025-{m:02d}" for m in range(1, 13)], index=8)
page = st.sidebar.radio("功能", ["CFO 首页看板", "业务线利润贡献分析", "经纪业务预实差异归因", "营业部盈利能力排名", "多维下钻筛选器", "自动生成 CFO 月度经营分析报告"])

biz = calculate_bizline_profitability(period)
branch = calculate_branch_profitability(period)
pvm = run_pvm_analysis(period, "BROKERAGE")

if page == "CFO 首页看板":
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("营业收入", f"{biz['revenue'].sum()/10000:,.0f} 万元")
    c2.metric("经营利润", f"{biz['operating_profit'].sum()/10000:,.0f} 万元")
    c3.metric("经纪收入差异", f"{pvm['total_variance'].iloc[0]/10000:,.0f} 万元")
    c4.metric("洞察数量", len(detect_management_insights(period)))
    fig = px.bar(biz, x="biz_line_id", y=biz["operating_profit"] / 10000, title="业务线利润贡献（万元）")
    fig.update_yaxes(title="经营利润（万元）")
    st.plotly_chart(fig, width="stretch")
    st.caption("利润贡献按实际收入、直接成本和分摊费用计算，用于观察不同业务线的分摊后贡献。")
    scatter = px.scatter(
        branch,
        x=branch["revenue"] / 10000,
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
    st.dataframe(biz, width="stretch")
    plot_df = biz.assign(revenue_wan=biz["revenue"] / 10000, profit_wan=biz["operating_profit"] / 10000)
    fig = px.bar(plot_df, x="biz_line_id", y=["revenue_wan", "profit_wan"], barmode="group", title="业务线收入与利润（万元）")
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
    st.dataframe(pvm_filtered, width="stretch")
    st.subheader("PVM 明细表")
    st.dataframe(detail, width="stretch")
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
    grouped["budget_revenue_wan"] = grouped["budget_revenue"] / 10000
    grouped["actual_revenue_wan"] = grouped["actual_revenue"] / 10000
    fig = px.bar(grouped, x="branch_id", y=["budget_revenue_wan", "actual_revenue_wan"], barmode="group", title="经纪业务预算 vs 实际（万元）")
    fig.update_yaxes(title="金额（万元）")
    st.plotly_chart(fig, width="stretch")
    st.caption("预算与实际对比用于定位收入缺口集中在哪些营业部。")
    st.subheader("Top negative variance 明细")
    st.dataframe(detail.sort_values("total_variance").head(10), width="stretch")
    st.subheader("自动经营解释")
    st.write(p["explanation"])

elif page == "营业部盈利能力排名":
    st.dataframe(branch.sort_values("profit_rank"), width="stretch")
    rank_df = branch.sort_values("profit_rank").assign(operating_profit_wan=branch["operating_profit"] / 10000)
    fig = px.bar(rank_df, x="branch_id", y="operating_profit_wan", color="operating_margin", title="营业部盈利能力排名（万元）")
    fig.update_yaxes(title="经营利润（万元）")
    st.plotly_chart(fig, width="stretch")
    st.caption("排名表基于费用分摊后的经营利润，避免只看收入规模。")

elif page == "多维下钻筛选器":
    selected_biz = st.multiselect("业务线", biz["biz_line_id"].tolist(), default=biz["biz_line_id"].tolist())
    selected_branch = st.multiselect("营业部", branch["branch_id"].tolist(), default=branch["branch_id"].tolist())
    filtered = biz[biz["biz_line_id"].isin(selected_biz)]
    st.dataframe(filtered, width="stretch")
    st.plotly_chart(px.bar(filtered, x="biz_line_id", y="profit_contribution_rate", title="利润贡献率"), width="stretch")
    st.dataframe(branch[branch["branch_id"].isin(selected_branch)], width="stretch")

else:
    st.markdown(generate_cfo_report_mock(period))
