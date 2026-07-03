---
name: validate-csvs
description: Validate data/*.csv files against the schema documented in README.md. Use after adding or editing any CSV in data/.
---

# validate-csvs

Validate all `data/*.csv` files in the academic database against the schema documented in
`README.md`.

Run this after adding or editing rows in any CSV, and before committing.

## Usage

Claude Code:

```text
/validate-csvs
```

Codex:

```text
$validate-csvs
```

## What it checks

Per file: header matches the documented column list (in order), every row has the right
number of fields, controlled-vocabulary columns only contain documented values, boolean
columns are `TRUE`/`FALSE`/blank, year/date columns parse and look sane, `id` columns are
unique, and foreign keys (e.g. `budget_years.grant_id` → `grants.id`) resolve to an existing
row. See the docstring and schema constants at the top of `scripts/validate_csvs.py` for the
full rule set; the canonical human-readable schema is in `README.md`.

Exits non-zero if any error was found. Warnings are printed but do not affect the exit code.

## Instructions

Run the validation script from the repo root and report the results. If there are errors,
summarize what needs fixing and offer to correct the affected CSV(s).

```bash
python3 /Users/bradcannell/Desktop/Git/Academia/academic-database/scripts/validate_csvs.py
```
