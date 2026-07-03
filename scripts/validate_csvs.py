#!/usr/bin/env python3
"""Validate data/*.csv against the schema documented in README.md.

Run manually after editing any CSV:

    python3 scripts/validate_csvs.py

Checks, per file:
  - header matches the documented column list, in order
  - every row has the right number of fields
  - controlled-vocabulary columns only contain documented values
  - boolean columns are TRUE, FALSE, or blank
  - year / date columns parse and look sane (year <= end_year, etc.)
  - id columns are unique within their file
  - foreign keys (e.g. budget_years.grant_id) resolve to an existing row

Exits non-zero if any error was found. Warnings are printed but do not
affect the exit code.

Uses only the standard library so it runs without installing anything.
"""

import csv
import datetime as dt
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TRUE_FALSE = {"TRUE", "FALSE"}


def enum(*values):
    return {"kind": "enum", "values": set(values)}


def soft_enum(*values):
    # Documented with "e.g." in the README - not a closed list, so
    # anything outside it is a warning rather than an error.
    return {"kind": "soft_enum", "values": set(values)}


def boolean():
    return {"kind": "bool"}


def year():
    return {"kind": "year"}


def date():
    return {"kind": "date"}


def integer():
    return {"kind": "int"}


def number():
    return {"kind": "number"}


# Per-file schema: column order, and any type/vocab constraint per column.
# Columns with no entry here are treated as free text.
SCHEMAS = {
    "publications.csv": {
        "columns": [
            "id", "publication_type", "title", "authors", "journal_or_venue",
            "year", "month", "day", "DOI", "PMID", "url", "author_position",
            "mentee_author", "multi_institution", "status", "notes",
        ],
        "id_column": "id",
        "constraints": {
            "publication_type": enum("peer_reviewed_article", "book", "chapter", "other"),
            "year": year(),
            "month": integer(),
            "day": integer(),
            "author_position": soft_enum("first", "middle", "last"),
            "mentee_author": boolean(),
            "multi_institution": boolean(),
            "status": enum("published", "in-press", "under-review"),
        },
    },
    "grants.csv": {
        "columns": [
            "id", "award_number", "mechanism", "sponsor", "funder_abbreviation",
            "title", "role", "status", "total_cost", "start_date", "end_date",
            "effort_percent",
        ],
        "id_column": "id",
        "constraints": {
            "status": enum("planned", "submitted", "funded", "rejected", "completed"),
            "total_cost": number(),
            "start_date": date(),
            "end_date": date(),
            "effort_percent": number(),
        },
        "date_ranges": [("start_date", "end_date")],
    },
    "effort_by_year.csv": {
        "columns": ["year", "effort_percentage"],
        "constraints": {
            "year": year(),
            "effort_percentage": number(),
        },
    },
    "budget_years.csv": {
        "columns": ["grant_id", "award_year_label", "cost"],
        "constraints": {
            "cost": number(),
        },
        "foreign_keys": [("grant_id", "grants.csv", "id")],
    },
    "presentations.csv": {
        "columns": [
            "id", "title", "presentation_type", "venue_name", "location",
            "year", "month", "day", "authors", "notes",
        ],
        "id_column": "id",
        "constraints": {
            "presentation_type": enum("invited", "conference-oral", "conference-poster", "panel"),
            "year": year(),
            "month": integer(),
            "day": integer(),
        },
    },
    "teaching.csv": {
        "columns": [
            "institution", "department", "course_code", "course_title",
            "start_year", "end_year", "role", "notes",
        ],
        "constraints": {
            "start_year": year(),
            "end_year": year(),
            "role": enum("instructor-of-record", "course-director-other"),
        },
        "year_ranges": [("start_year", "end_year")],
    },
    "service.csv": {
        "columns": ["start_year", "end_year", "category", "role", "organization", "notes"],
        "constraints": {
            "start_year": year(),
            "end_year": year(),
            "category": enum("community", "university", "profession", "editorial"),
        },
        "year_ranges": [("start_year", "end_year")],
    },
    "service_log.csv": {
        "columns": ["date", "hours", "minutes", "type", "description"],
        "constraints": {
            "date": date(),
            "hours": number(),
            "minutes": number(),
        },
    },
    "reviewer_relationships.csv": {
        "columns": ["journal_or_venue", "relationship_type", "status"],
        "constraints": {
            "relationship_type": enum("editorial-board", "ad-hoc-reviewer", "software-reviewer"),
            "status": enum("ongoing", "ended"),
        },
    },
    "peer_reviews.csv": {
        "columns": [
            "id", "journal", "manuscript_title", "date_start", "date_end",
            "rounds", "published",
        ],
        "id_column": "id",
        "constraints": {
            "date_start": date(),
            "date_end": date(),
            "rounds": integer(),
            "published": boolean(),
        },
        "date_ranges": [("date_start", "date_end")],
    },
    "mentoring.csv": {
        "columns": [
            "mentee_name", "role", "degree_or_context", "start_year", "end_year",
            "primary_advisor", "current_status", "role_detail",
        ],
        "constraints": {
            "role": enum(
                "primary-advisor", "committee-member", "ra-ta-intern",
                "external-mentee", "postdoc-mentee", "faculty-mentee",
            ),
            "start_year": year(),
            "end_year": year(),
            "primary_advisor": boolean(),
        },
        "year_ranges": [("start_year", "end_year")],
    },
    "advising_load.csv": {
        "columns": ["academic_year", "advisee_count"],
        "constraints": {
            "advisee_count": integer(),
        },
    },
    "awards.csv": {
        "columns": ["year", "award_name", "granting_body", "notes"],
        "constraints": {
            "year": year(),
        },
    },
    "professional_memberships.csv": {
        "columns": ["organization", "abbreviation", "start_year", "end_year", "notes"],
        "constraints": {
            "start_year": year(),
            "end_year": year(),
        },
        "year_ranges": [("start_year", "end_year")],
    },
}


class Result:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, filename, row_num, msg):
        self.errors.append(f"{filename}:{row_num}: {msg}")

    def warning(self, filename, row_num, msg):
        self.warnings.append(f"{filename}:{row_num}: {msg}")


def check_year(value):
    return value.isdigit() and len(value) == 4


def check_date(value):
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def check_int(value):
    try:
        int(value)
        return True
    except ValueError:
        return False


def check_number(value):
    try:
        float(value)
        return True
    except ValueError:
        return False


def check_value(kind_spec, value):
    """Return True if value satisfies the constraint (blank always passes)."""
    if value == "":
        return True
    kind = kind_spec["kind"]
    if kind in ("enum", "soft_enum"):
        return value in kind_spec["values"]
    if kind == "bool":
        return value in TRUE_FALSE
    if kind == "year":
        return check_year(value)
    if kind == "date":
        return check_date(value)
    if kind == "int":
        return check_int(value)
    if kind == "number":
        return check_number(value)
    return True


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows


def validate_file(filename, schema, result, all_ids):
    path = DATA_DIR / filename
    if not path.exists():
        result.error(filename, 0, "file is missing")
        return

    rows = load_csv(path)
    if not rows:
        result.error(filename, 0, "file has no header row")
        return

    header, data_rows = rows[0], rows[1:]
    expected = schema["columns"]
    if header != expected:
        result.error(
            filename, 1,
            f"header mismatch\n    expected: {expected}\n    found:    {header}",
        )
        # Still try to validate using the documented column order below,
        # since a header typo shouldn't stop us from checking the data.

    ncols = len(expected)
    constraints = schema.get("constraints", {})
    id_column = schema.get("id_column")
    seen_ids = set()

    for i, row in enumerate(data_rows, start=2):  # +1 for header, +1 for 1-index
        if len(row) != len(header):
            result.error(filename, i, f"expected {len(header)} fields, found {len(row)}")
            continue

        record = dict(zip(header, row))

        for col, kind_spec in constraints.items():
            if col not in record:
                continue
            value = record[col].strip()
            if not check_value(kind_spec, value):
                allowed = kind_spec.get("values")
                label = f"one of {sorted(allowed)}" if allowed else kind_spec["kind"]
                sev = result.warning if kind_spec["kind"] == "soft_enum" else result.error
                sev(filename, i, f"column '{col}' = {value!r} is not {label}")

        if id_column and id_column in record:
            rid = record[id_column].strip()
            if rid == "":
                result.error(filename, i, f"column '{id_column}' is blank")
            elif rid in seen_ids:
                result.error(filename, i, f"duplicate id '{rid}'")
            else:
                seen_ids.add(rid)

        for start_col, end_col in schema.get("year_ranges", []):
            s, e = record.get(start_col, ""), record.get(end_col, "")
            if s and e and check_year(s) and check_year(e) and int(s) > int(e):
                result.error(filename, i, f"{start_col} ({s}) is after {end_col} ({e})")

        for start_col, end_col in schema.get("date_ranges", []):
            s, e = record.get(start_col, ""), record.get(end_col, "")
            if s and e and check_date(s) and check_date(e) and s > e:
                result.error(filename, i, f"{start_col} ({s}) is after {end_col} ({e})")

    if id_column:
        all_ids[filename] = seen_ids


def validate_foreign_keys(filename, schema, result, all_ids):
    for col, ref_file, ref_col in schema.get("foreign_keys", []):
        path = DATA_DIR / filename
        if not path.exists():
            continue
        rows = load_csv(path)
        if not rows:
            continue
        header, data_rows = rows[0], rows[1:]
        if col not in header:
            continue
        ref_ids = all_ids.get(ref_file)
        if ref_ids is None:
            result.warning(filename, 0, f"cannot check foreign key '{col}' -> {ref_file}.{ref_col} (no id data loaded)")
            continue
        idx = header.index(col)
        for i, row in enumerate(data_rows, start=2):
            if idx >= len(row):
                continue
            value = row[idx].strip()
            if value and value not in ref_ids:
                result.error(filename, i, f"'{col}' = {value!r} does not match any {ref_file}.{ref_col}")


def main():
    result = Result()
    all_ids = {}

    for filename, schema in SCHEMAS.items():
        validate_file(filename, schema, result, all_ids)

    for filename, schema in SCHEMAS.items():
        validate_foreign_keys(filename, schema, result, all_ids)

    # Flag any data/*.csv not covered by SCHEMAS (e.g. a new file added
    # without updating this script or README.md).
    known = set(SCHEMAS)
    on_disk = {p.name for p in DATA_DIR.glob("*.csv")}
    for extra in sorted(on_disk - known):
        result.warning(extra, 0, "file exists but is not documented in this script's SCHEMAS")

    if result.warnings:
        print(f"{len(result.warnings)} warning(s):")
        for w in result.warnings:
            print(f"  WARNING {w}")
        print()

    if result.errors:
        print(f"{len(result.errors)} error(s):")
        for e in result.errors:
            print(f"  ERROR {e}")
        print()
        print("FAILED")
        return 1

    print("All CSVs valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
