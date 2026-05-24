import json

from src.agent import run_management_accounting_agent_with_trace
from src.agent_trace import ReasoningTrace, StepType
from src.db import load_synthetic_data_to_duckdb
from src.seed_data import generate_synthetic_data


def setup_module():
    generate_synthetic_data()
    load_synthetic_data_to_duckdb()


def test_management_agent_trace_contains_required_steps():
    trace = run_management_accounting_agent_with_trace("请分析 2025-09 公司利润低于预算的主要原因。")

    assert isinstance(trace, ReasoningTrace)
    assert trace.steps
    step_types = {step.step_type for step in trace.steps}
    assert StepType.INTENT_RECOGNITION in step_types
    assert StepType.PLAN_GENERATION in step_types
    assert StepType.TOOL_CALL in step_types
    assert StepType.OBSERVATION in step_types
    assert StepType.CONCLUSION in step_types
    assert trace.final_answer
    tool_names = {step.tool_name for step in trace.steps if step.tool_name}
    assert "run_pvm_analysis" in tool_names or "calculate_bizline_profitability" in tool_names
    json.dumps(trace.to_dict(), ensure_ascii=False, default=str)


def test_management_agent_trace_contains_what_if_tool():
    trace = run_management_accounting_agent_with_trace("如果经纪业务交易量恢复 5%，收入和利润能改善多少？", period="2025-09")

    tool_names = {step.tool_name for step in trace.steps if step.tool_name}
    assert "simulate_brokerage_recovery" in tool_names
    assert trace.final_answer
    json.dumps(trace.to_dict(), ensure_ascii=False, default=str)
