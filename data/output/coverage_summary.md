# Coverage Summary

Generated from a local run on Python 3.11.15.

## Command

```bash
python -m pytest --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml
```

## Result

- Tests: 31 passed
- Total coverage: 66%
- HTML report: `htmlcov/index.html`
- XML report: `coverage.xml`

## Low Coverage Modules

| Module | Coverage | Notes |
|---|---:|---|
| `src/app.py` | 0% | Streamlit UI is not covered by unit tests. |
| `src/project_metrics.py` | 0% | CLI reporting helper; exercised manually during release checks. |
| `src/load_audit_report.py` | 36% | PDF parsing fallback paths are intentionally not fully covered by synthetic test data. |
| `src/agent.py` | 68% | Mock Agent paths are covered; optional LLM branches and several fallback paths are lightly covered. |

## Terminal Coverage Table

```text
Name                            Stmts   Miss  Cover
---------------------------------------------------
src/__init__.py                     0      0   100%
src/agent.py                      320    101    68%
src/app.py                        230    230     0%
src/config.py                      14      0   100%
src/data_quality.py                84      4    95%
src/db.py                          27      5    81%
src/llm_client.py                  85     10    88%
src/load_audit_report.py           70     45    36%
src/profitability_insights.py      81      7    91%
src/project_metrics.py             45     45     0%
src/recon_data_loader.py           42      3    93%
src/schema.py                       3      0   100%
src/seed_data.py                  178      3    98%
src/validation.py                 143      8    94%
src/what_if.py                     17      0   100%
---------------------------------------------------
TOTAL                            1339    461    66%
```
