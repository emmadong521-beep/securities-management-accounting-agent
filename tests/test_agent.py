from src.agent import AgentResult, answer_management_followup, run_management_accounting_agent
from src.db import load_synthetic_data_to_duckdb
from src.seed_data import generate_synthetic_data


def setup_module():
    generate_synthetic_data()
    load_synthetic_data_to_duckdb()


def test_run_management_agent_returns_result():
    result = run_management_accounting_agent("请分析 2025-09 公司利润低于预算的主要原因。")
    assert isinstance(result, AgentResult)
    assert result.plan
    assert result.steps
    assert result.final_answer


def test_agent_steps_include_core_tools():
    result = run_management_accounting_agent("经纪业务收入低于预算，是交易量下降还是佣金率下降导致？", period="2025-09")
    tool_names = {step.tool_name for step in result.steps}
    assert "run_pvm_analysis" in tool_names or "calculate_bizline_profitability" in tool_names


def test_management_followup_answers_pvm_and_recommendation():
    result = run_management_accounting_agent("请分析 2025-09 公司利润低于预算的主要原因。")
    pvm_answer = answer_management_followup("交易量影响和佣金率影响哪个更大？", result)
    suggestion_answer = answer_management_followup("有什么管理建议？", result)
    assert "交易量影响" in pvm_answer or "佣金率影响" in pvm_answer
    assert "管理建议" in suggestion_answer
