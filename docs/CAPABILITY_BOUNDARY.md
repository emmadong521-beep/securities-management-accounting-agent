# Capability Boundary

## Positioning

This project focuses on management accounting analysis for securities companies: business-line profitability, brokerage PVM analysis, branch profitability, high-revenue low-profit detection, and What-if simulation.

It is designed as a local finance AI PoC. The core management accounting calculations are deterministic and traceable, while the Agent layer helps organize the analysis path, observations, and final business conclusion.

## Capability Comparison

| Dimension | Traditional finance systems | BI / dashboards | LLM-only tools | This PoC |
|---|---|---|---|---|
| Management reports | Predefined reports | Strong visualization | Can summarize text | Generates structured analysis from deterministic calculations |
| PVM analysis | Requires model configuration | Possible if modeled | Not reliable for calculation | Code-based PVM decomposition |
| Branch profitability | Depends on allocation model | Visualizes calculated margins | Not reliable for cost allocation | Calculates allocated profitability and rank gaps |
| What-if simulation | Usually requires planning module | Limited ad hoc simulation | May invent numbers | Formula-based local simulation |
| Interaction | Menu-driven | Filter driven | Natural language | Natural language task plus visible tool trace |
| Traceability | Strong if integrated | Depends on model lineage | Weak if ungrounded | Traceable to synthetic tables and tool outputs |

## What This PoC Does

This project demonstrates how an Agent-style workflow can support management accounting analysis.

The workflow covers:

1. Calculate business-line profitability.
2. Run brokerage budget-vs-actual variance analysis.
3. Decompose brokerage revenue variance with PVM analysis.
4. Analyze branch profitability after allocated expenses.
5. Identify high-revenue low-profit branches.
6. Run What-if simulation for brokerage trading volume, commission rate, and expense assumptions.
7. Generate a structured operating analysis report.
8. Support follow-up questions based on the analysis context.

## What This PoC Does Not Do

This project does not attempt to replace a production planning, budgeting, or finance system.

It does not:

- connect to a real securities core system;
- process real customer, trade, budget, or voucher data;
- post or adjust accounting entries;
- perform regulatory reporting;
- use LLM output as the source of truth for financial numbers.

## Deterministic Calculation Boundary

Financial and management accounting calculations are handled by local code.

This includes:

- business-line profitability;
- branch profitability;
- brokerage PVM analysis;
- high-revenue low-profit detection;
- What-if simulation;
- operating insight generation;
- CFO-style report generation.

The LLM is used only for language-oriented tasks such as task interpretation, answer wording, and follow-up response generation.

## Data Boundary

The project uses synthetic detailed data.

Public audit-report figures may be used only for aggregate-scale calibration. Detailed business-line, branch, customer-segment, product, KPI, budget, actual, and expense data is generated for demonstration and testing.

The data does not represent any real company’s internal operating records.

## Relationship With Project One

This project can run independently with its own synthetic data.

It can also optionally read validated outputs from the month-end reconciliation project:

- `validated_actual_revenue.csv`
- `validated_allocated_expense.csv`

This design demonstrates how trusted month-end data can become the input layer for management accounting analysis.

## Current Limitations

- Local PoC only.
- Synthetic detailed data.
- Optional use of project-one validated outputs.
- No real planning system integration.
- No production workflow or permission control.
- LLM enhances task understanding and explanation only.
- The workflow focuses on selected management accounting scenarios rather than full enterprise performance management.
