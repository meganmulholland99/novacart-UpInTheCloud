# NovaCart ETL Pipeline — New Joiner Lab

A reference Data Engineering project. Ingests heterogeneous source data (CSV,
nested JSON, SQLite) through a **Bronze → Silver → Gold** medallion architecture
into an analytics-ready star schema.

**Runs on macOS, Linux, and Windows.** Pure Python — no Docker, no cloud
services, no external dependencies beyond `pip install`.

---

## Quick start

You need **Python 3.10 or newer**. Check with `python --version` (or `python3 --version` on macOS).

### Option A — one command (recommended)

After unzipping the project and `cd`-ing into it:

**macOS / Linux:**
```bash
bash scripts/run_everything.sh
```

**Windows (Command Prompt or PowerShell):**
```bash
scripts\run_everything.bat
```

**Either OS (works everywhere):**
```bash
python scripts/run_everything.py
```

The script installs dependencies, generates sample data, runs the pipeline for
4 dates, and runs the test suite. Expected output ends with `14 passed`.

### Option B — step by step

**1. Create and activate a virtual environment** (optional but recommended):

| OS | Create | Activate |
|---|---|---|
| macOS / Linux | `python3 -m venv .venv` | `source .venv/bin/activate` |
| Windows (PowerShell) | `python -m venv .venv` | `.venv\Scripts\Activate.ps1` |
| Windows (cmd) | `python -m venv .venv` | `.venv\Scripts\activate.bat` |

> **Windows PowerShell only**: if you see "running scripts is disabled on this system", run this once: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**2. Install dependencies:**
```bash
pip install -r requirements.txt
```

**3. Generate sample data:**
```bash
python scripts/generate_sample_data.py
```

**4. Run the pipeline:**
```bash
python -m src.pipeline --date 2025-11-10 --backfill 3
```

**5. Run the tests:**
```bash
pytest -v
```

---

## What you'll see after a successful run

```
data/
├── landing/        # raw source files (already provided)
├── bronze/         # raw + ingestion metadata, partitioned by date
├── silver/         # validated, typed, deduped
├── gold/           # star schema: fact_orders, dim_customer, dim_product, dim_date
└── quarantine/     # rows that failed validation, with reasons
```

Quick peek at the output:
```bash
python -c "import pandas as pd; print(pd.read_parquet('data/gold/fact_orders.parquet'))"
```

See `SAMPLE_RUN_REPORT.md` for the full expected output, including the SCD-2
history tracking and the quarantine breakdown.

---

## What this project teaches

| Concept | Where it lives |
|---|---|
| Heterogeneous source ingestion (CSV, JSON, SQL) | `src/ingest/` |
| Schema contracts via pydantic | `src/utils/schemas.py` |
| Schema-drift detection (additive vs subtractive) | `src/transform/schema_check.py` |
| Quarantine pattern for bad rows | `src/transform/silver.py` |
| Incremental loading with watermarks | `src/ingest/products.py` + `src/utils/state.py` |
| SCD Type 1 and Type 2 | `src/transform/gold.py` |
| Idempotent partition-replace loads | `build_fact_orders` |
| Orchestration with run metadata | `src/pipeline.py` |
| Structured JSON logging | `src/utils/logging_setup.py` |
| Test-driven pipeline development | `tests/` |

---

## Project layout

```
novacart_pipeline/
├── config/pipeline.yaml         # all tunables live here
├── data/                        # landing + medallion layers
├── scripts/
│   ├── generate_sample_data.py  # creates the demo data
│   ├── run_everything.py        # cross-platform end-to-end runner
│   ├── run_everything.sh        # macOS / Linux wrapper
│   └── run_everything.bat       # Windows wrapper
├── src/
│   ├── ingest/                  # orders.py, customers.py, products.py
│   ├── transform/               # silver.py, gold.py, schema_check.py
│   ├── load/                    # (reserved for future targets, e.g. Postgres)
│   ├── utils/                   # config, logging, schemas, state, exceptions
│   └── pipeline.py              # orchestrator + CLI
├── tests/
│   ├── conftest.py              # fixtures
│   ├── test_pipeline_scenarios.py  # the 7 required scenarios
│   └── test_schemas.py
├── state/                       # watermarks + run history (created at runtime)
├── logs/                        # pipeline.jsonl (created at runtime)
└── requirements.txt
```

---

## The seven test scenarios

Every new joiner must implement and pass these. They map 1:1 to
`tests/test_pipeline_scenarios.py`.

1. **Happy path** — 3 valid orders in → 3 rows in `fact_orders`
2. **Duplicate handling** — duplicates collapse on primary key
3. **Bad data → quarantine** — invalid rows are isolated, not silently dropped
4. **Additive schema drift** — new column appears → warn, succeed
5. **Subtractive schema drift** — required column gone → fail loudly
6. **Idempotency** — running the same date twice yields identical Gold
7. **Backfill** — N sequential days produces the same Gold as N independent runs

---

## Resetting between runs

If you want a clean slate after experimenting:

**macOS / Linux:**
```bash
rm -rf data/bronze data/silver data/gold data/quarantine state logs
```

**Windows (PowerShell):**
```powershell
Remove-Item -Recurse -Force data\bronze, data\silver, data\gold, data\quarantine, state, logs
```

**Windows (cmd):**
```bat
rmdir /s /q data\bronze data\silver data\gold data\quarantine state logs
```

Then regenerate sample data and rerun. The `data/landing/` folder and `products.db`
are your sources of truth — don't delete those (or regenerate them with
`python scripts/generate_sample_data.py`).

---

## Common joiner mistakes to avoid

- Letting pandas infer types at ingest. Always read as string in Bronze; cast in Silver.
- Updating the watermark **before** the write succeeds → guaranteed data loss on failure.
- Bare `except Exception:` — hides bugs. Catch narrowly (`IngestionError`, `SchemaError`).
- Reading the same file three times in three stages — read once, pass DataFrames.
- Hardcoded paths or credentials — they belong in `config/` or environment variables.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `python: command not found` | Use `python3` instead (mostly macOS) |
| `pip: command not found` | Use `python -m pip install -r requirements.txt` |
| `ModuleNotFoundError: No module named 'src'` | You're not in the project root — `cd` into `novacart_pipeline/` first |
| `pytest: command not found` | Use `python -m pytest -v` |
| Windows: "running scripts is disabled" | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once |
| Windows: `.bat` opens then immediately closes | Open `cmd` or PowerShell first, then run `scripts\run_everything.bat` from there |
