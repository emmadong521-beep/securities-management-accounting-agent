# Design Decisions

## Scope

This project is a securities management accounting AI PoC focused on:

- business-line profitability
- brokerage PVM analysis
- branch profitability
- What-if simulation
- CFO-style reporting

It keeps the analysis layer deterministic and uses the Agent layer to orchestrate
existing tools.

## Key Decisions

### Use synthetic detailed data

Public audit-report figures can calibrate aggregate scale, but branch,
customer-segment, product, budget, KPI, and expense details must remain
synthetic.

### Keep DuckDB local

Local DuckDB supports repeatable analytics without external service dependencies.

### Keep PVM and What-if math in code

Revenue, cost, PVM, and scenario calculations must be auditable and testable.

### Make project-one data optional

The app can run independently, while `RECON_PROJECT_OUTPUT_DIR` allows it to read
validated month-end outputs when available.

### Make LLM optional

The Volcengine Ark integration improves task parsing and language expression
only. Missing configuration or API errors use the deterministic fallback mode.

### Preserve drilldown

Management conclusions should be traceable to business line, branch, customer
segment, product, PVM effects, and cost drivers.

## Non-Goals

- No production planning, budgeting, or finance-system write-back.
- No claim that synthetic business patterns represent all securities-company
  operating conditions.
- No model-generated amount calculation.
- No dependency on project one for normal local execution.

## Quality Boundaries

Tests cover schema, seed data, profitability calculations, PVM identity,
management insights, high-revenue low-profit analysis, What-if simulation, Agent
behavior, LLM fallback, optional project-one data loading, and data quality
reporting.

Coverage is reported with `pytest-cov`; low-coverage modules are documented
rather than hidden.
