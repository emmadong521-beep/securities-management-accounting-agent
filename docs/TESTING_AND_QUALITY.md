# Testing And Data Quality

## Local Commands

```bash
python3 scripts/check_markdown_format.py
python -m pytest -q
python -m pytest --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml
python -m src.data_quality
python -m src.project_metrics
```

The same checks are wired into `.github/workflows/tests.yml`.

## Format Checks

`python3 scripts/check_markdown_format.py` verifies that README, engineering
docs, and workflow files are real multi-line Markdown or YAML files. It checks
line counts, long lines, required README sections, fenced code-block balance,
Mermaid fences, and GitHub Actions YAML structure.

## Test Coverage Areas

- Core table schemas and primary keys.
- Synthetic data generation and dimensional consistency.
- Business-line profitability calculation.
- Branch profitability calculation.
- Brokerage PVM identity: total variance equals volume effect plus rate effect plus mix effect.
- Management insight detection.
- High-revenue low-profit branch detection and explanation.
- Brokerage What-if simulation.
- Optional project-one validated data loading and fallback.
- Agent planning, tool calls, final answer, and follow-up behavior.
- LLM unavailable fallback.
- Data quality report generation.

## Data Quality Checks

`python -m src.data_quality` writes:

- `data/output/data_quality_report.md`
- `data/output/data_quality_report.json`

The report includes:

- Row counts for core tables.
- Primary-key uniqueness checks.
- Foreign-key integrity checks.
- Critical amount-field null checks.
- Budget and actual dimension consistency.
- Profitability calculation checks.
- PVM identity checks.
- Seeded operating story detection.
- Public aggregate calibration check.
- Final `PASS / WARNING / FAIL` status.

## Coverage Reports

`python -m pytest --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml` writes:

- `htmlcov/index.html`
- `coverage.xml`

The current terminal summary is recorded in `data/output/coverage_summary.md`.
