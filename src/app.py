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
    st.plotly_chart(px.bar(biz, x="biz_line_id", y="operating_profit", title="业务线利润贡献"), width="stretch")
    st.plotly_chart(px.scatter(branch, x="revenue", y="operating_margin", size="operating_profit", color="branch_id", title="营业部收入 vs 经营利润率"), width="stretch")

elif page == "业务线利润贡献分析":
    st.dataframe(biz, width="stretch")
    st.plotly_chart(px.bar(biz, x="biz_line_id", y=["revenue", "operating_profit"], barmode="group", title="业务线收入与利润"), width="stretch")

elif page == "经纪业务预实差异归因":
    variance = run_brokerage_budget_variance(period)
    st.dataframe(variance, width="stretch")
    p = pvm.iloc[0]
    waterfall = go.Figure(go.Waterfall(
        name="PVM",
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "total"],
        x=["预算收入", "交易量影响", "佣金率影响", "混合影响", "实际收入"],
        y=[p["budget_revenue"], p["volume_effect"], p["rate_effect"], p["mix_effect"], p["actual_revenue"]],
    ))
    st.plotly_chart(waterfall, width="stretch")
    grouped = variance.groupby("branch_id", as_index=False)[["budget_revenue", "actual_revenue"]].sum()
    st.plotly_chart(px.bar(grouped, x="branch_id", y=["budget_revenue", "actual_revenue"], barmode="group", title="预算 vs 实际"), width="stretch")

elif page == "营业部盈利能力排名":
    st.dataframe(branch.sort_values("profit_rank"), width="stretch")
    st.plotly_chart(px.bar(branch.sort_values("profit_rank"), x="branch_id", y="operating_profit", color="operating_margin", title="营业部盈利能力排名"), width="stretch")

elif page == "多维下钻筛选器":
    selected_biz = st.multiselect("业务线", biz["biz_line_id"].tolist(), default=biz["biz_line_id"].tolist())
    selected_branch = st.multiselect("营业部", branch["branch_id"].tolist(), default=branch["branch_id"].tolist())
    filtered = biz[biz["biz_line_id"].isin(selected_biz)]
    st.dataframe(filtered, width="stretch")
    st.plotly_chart(px.bar(filtered, x="biz_line_id", y="profit_contribution_rate", title="利润贡献率"), width="stretch")
    st.dataframe(branch[branch["branch_id"].isin(selected_branch)], width="stretch")

else:
    st.markdown(generate_cfo_report_mock(period))
