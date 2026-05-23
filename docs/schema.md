# 表结构

- `chart_of_accounts`：总账科目表，两个项目保持一致。
- `biz_line_master`：业务线主数据。
- `branch_master`：营业部主数据。
- `customer_segment_master`：客户分层主数据。
- `product_master`：产品主数据。
- `monthly_budget`：月度预算，含收入、直接成本、分摊费用、利润、
  交易量和佣金率。
- `monthly_actual`：月度实际，与预算表维度一致。
- `brokerage_kpi`：经纪业务交易量、佣金率、客户数 KPI。
- `branch_expense`：营业部薪酬、租金、营销、IT、行情和总部分摊费用。
- `branch_profitability`：营业部分摊后盈利能力。
- `bizline_profitability`：业务线利润贡献。
- `pvm_analysis_result`：经纪业务价量结构拆解结果，维度为期间、营业部、
  客户分层和产品类型。
- `management_insight`：管理洞察和建议。
- `market_benchmark`：市场交易量和佣金率基准。

## 输出报告

- `data_quality_report`：由 `python -m src.data_quality` 生成，包含行数、
  主键、外键、金额空值、利润勾稽、PVM 恒等关系、经营故事检测、
  公开指标校准和检查结论。
