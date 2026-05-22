# securities-management-accounting-agent

中文名：证券公司管理会计多维经营分析 Agent

本项目模拟证券公司 CFO 月度经营分析场景，基于经纪、投行、资管、自营、信用、财富管理等业务线的预算、实际、费用分摊和多维经营数据，自动生成经营分析、预实差异归因和管理建议。

项目一用于保证月结数据准确、可追溯；项目二基于可信月结数据进行管理会计分析和经营决策支持。第一版以可演示、可解释、可测试为目标，不强依赖复杂 Agent 框架。

## 数据来源说明

审计报告路径通过 `.env` 的 `AUDIT_REPORT_PATH` 配置，默认指向：

`/Users/dongkaixin/Downloads/财务agent项目/管理会计多维盈利分析/长江证券2025年审计财报.pdf`

PDF 不会提交到仓库。`src/load_audit_report.py` 会尝试解析公开披露汇总指标，解析失败时使用 `data/raw/audit_report_metrics_template.yaml` 和代码内置 fallback。所有预算、实际、营业部、客户分层、产品、KPI 和洞察均为合成数据。

本项目仅用于个人学习和求职作品集。项目使用公开披露数据进行规模校准，明细数据均为合成数据，不代表长江证券真实客户、交易、凭证、营业部或内部经营数据，不包含任何未公开重大信息、客户隐私数据或商业秘密，不构成投资建议。

## 业务场景

- 业务线利润贡献分析
- 经纪业务预实差异归因
- 营业部盈利能力分析
- 费用分摊后经营利润分析
- CFO 月度经营分析报告自动生成

## 运行方式

```bash
cd /Users/dongkaixin/Downloads/财务agent项目/securities-management-accounting-agent
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m src.seed_data
.venv/bin/python -m src.db
.venv/bin/python -m pytest
.venv/bin/streamlit run src/app.py
```

## 主要表

`chart_of_accounts`, `biz_line_master`, `branch_master`, `customer_segment_master`, `product_master`, `monthly_budget`, `monthly_actual`, `brokerage_kpi`, `branch_expense`, `branch_profitability`, `bizline_profitability`, `pvm_analysis_result`, `management_insight`, `market_benchmark`

## 内置经营故事

- 经纪业务收入低于预算：市场交易量下降、机构客户佣金率下降。
- 上海营业部收入排名靠前，但分摊 IT 系统费用和总部管理费用后经营利润率较低。
- 财富管理收入增长，但营销激励费用上升更快，利润贡献低于预期。
- 信用业务利息收入低于预算：两融余额下降。
- 部分营业部表面收入高，但扣除费用分摊后利润贡献不高。

## Demo 截图占位

面试展示时可截取：CFO 首页看板、业务线利润贡献柱状图、预算 vs 实际、PVM 瀑布图、营业部收入 vs 经营利润率散点图、CFO 报告页面。

## 简历写法建议

- 构建证券公司管理会计多维经营分析 Agent PoC，基于公开审计报告汇总口径校准预算、实际、费用分摊和经营 KPI 合成数据。
- 实现经纪业务 PVM 预实差异拆解、业务线利润贡献、营业部盈利排名和 CFO 月报自动生成，金额由 pandas/DuckDB 计算，mock Agent 负责解释。

## 后续扩展方向

- 接入项目一修正后的月结数据作为 actual_revenue 和 allocated_expense 来源
- 增加产品、客户经理、渠道、投行项目等维度
- 接入 LLM API 生成更自然的管理建议，但保持所有金额由代码计算
