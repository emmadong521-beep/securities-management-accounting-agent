from types import SimpleNamespace

from src.app import build_agent_related_chart_flags


def _result(user_task: str, chart_refs=None, final_answer: str = ""):
    return SimpleNamespace(user_task=user_task, chart_refs=chart_refs or [], final_answer=final_answer)


def test_profit_variance_task_shows_core_charts():
    flags = build_agent_related_chart_flags(_result("请分析 2025-09 公司利润低于预算的主要原因。"))

    assert flags["show_bizline"]
    assert flags["show_pvm"]
    assert flags["show_branch_scatter"]


def test_brokerage_task_shows_pvm():
    flags = build_agent_related_chart_flags(_result("经纪业务收入低于预算，是交易量下降还是佣金率下降导致？"))

    assert flags["show_pvm"]
    assert flags["show_pvm_detail"]


def test_high_revenue_low_profit_task_shows_branch_drilldown():
    flags = build_agent_related_chart_flags(_result("为什么深圳营业部收入排名靠前，但经营利润率偏低？"))

    assert flags["show_high_low"]
    assert flags["show_branch_scatter"]


def test_what_if_task_shows_simulation():
    flags = build_agent_related_chart_flags(_result("如果经纪业务交易量恢复 5%，收入和利润能改善多少？"))

    assert flags["show_what_if"]


def test_empty_chart_refs_still_uses_keywords():
    flags = build_agent_related_chart_flags(_result("请下钻高收入低利润营业部。", chart_refs=[]))

    assert flags["show_high_low"]
    assert flags["show_branch_scatter"]


def test_bcg_task_shows_bcg_matrix():
    flags = build_agent_related_chart_flags(_result("请用 BCG 矩阵分析 2025-09 各业务线经营状态。"))

    assert flags["show_bcg"]
