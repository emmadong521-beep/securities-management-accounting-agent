# Capability Boundary

## Positioning

This project focuses on management accounting analysis for securities companies: business-line profitability, brokerage PVM, branch profitability, high-revenue low-profit detection, and What-if simulation.

## Capability Comparison

| Dimension | Traditional finance systems | BI / dashboards | LLM-only tools | This PoC |
|---|---|---|---|---|
| Management reports | Predefined reports | Strong visualization | Can summarize text | Generates structured analysis from deterministic calculations |
| PVM analysis | Requires model configuration | Possible if modeled | Not reliable for calculation | Code-based PVM decomposition |
| Branch profitability | Depends on allocation model | Visualizes calculated margins | Not reliable for cost allocation | Calculates allocated profitability and rank gaps |
| What-if simulation | Usually requires planning module | Limited ad hoc simulation | May invent numbers | Formula-based local simulation |
| Interaction | Menu-driven | Filter driven | Natural language | Natural language task plus visible tool trace |
| Traceability | Strong if integrated | Depends on model lineage | Weak if ungrounded | Traceable to synthetic tables and tool outputs |

## Current Limitations

- Local PoC only.
- Synthetic detailed data.
- Optional use of project-one validated outputs.
- No real planning system integration.
- LLM enhances explanation only.
