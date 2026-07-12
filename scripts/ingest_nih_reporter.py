#!/usr/bin/env python3
"""Reconcile Brad's NIH RePORTER projects against data/grants.csv and data/budget_years.csv.

Unlike ingest_orcid_pubmed.py, this script never writes anything. Every NIH
grant row in grants.csv already has award_number/mechanism/total_cost/dates
filled in -- there's no blank-field backfill to do. So this is a
reconciliation *report*: it flags places where the live NIH RePORTER record
disagrees with the CSV (wrong award number, a no-cost extension that moved
the end date, a project marked "completed" that RePORTER still shows as
active) so Brad can fix them by hand, plus any NIH projects where he's PI
that have no matching grants.csv row at all (add those via the
add-academic-entry skill).

Matching is by PI name (first "Michael", last "Cannell"), not by
organization, since RePORTER's pi_names search is what actually finds every
award where he's an official PI regardless of which institution held it at
the time. Note this means awards where he's listed only as a *site* PI on
someone else's prime award (e.g. a subcontract) won't show up here --
RePORTER's PI list only carries the prime award's officially registered
PIs/MPIs, not every institution's site lead on a multi-site trial. That's
expected, not a bug: those grants.csv rows will just never get RePORTER
flags, and non-NIH sponsors (Hartford, DOJ, VA, CMS, CDC, HRSA, etc.) never
appear here at all since RePORTER only covers NIH-funded projects.

Usage:

    python3 scripts/ingest_nih_reporter.py

Uses only the standard library so it runs without installing anything.
"""

import csv
import difflib
import json
import re
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

REPORTER_SEARCH_URL = "https://api.reporter.nih.gov/v2/projects/search"
PI_FIRST_NAME = "Michael"
PI_LAST_NAME = "Cannell"

REPO_ROOT = Path(__file__).resolve().parent.parent
GRANTS_CSV = REPO_ROOT / "data" / "grants.csv"
BUDGET_YEARS_CSV = REPO_ROOT / "data" / "budget_years.csv"

# Same threshold/approach as ingest_orcid_pubmed.py's title matching -- a
# straight equality check on award_number catches most rows, but titles let
# us still recognize a project whose CSV award_number is stale or wrong
# (e.g. a pre-award/application number that got superseded once NIH issued
# the actual Notice of Award), instead of miscounting it as a brand-new grant.
TITLE_MATCH_THRESHOLD = 0.85

USER_AGENT = "academic-database-ingest/1.0 (personal use; brad.cannell@gmail.com)"

INCLUDE_FIELDS = [
    "ProjectNum", "ProjectTitle", "CoreProjectNum", "ActivityCode",
    "FiscalYear", "AwardAmount", "DirectCostAmt", "IndirectCostAmt",
    "ProjectStartDate", "ProjectEndDate", "AgencyIcAdmin", "ContactPiName",
]


def normalize_title(title):
    title = re.sub(r"<[^>]+>", " ", title)
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def partial_ratio(a, b):
    """Best alignment ratio of the shorter string against a same-length window of the longer one.

    Copied from ingest_orcid_pubmed.py: absorbs a dropped subtitle or
    reworded parenthetical without tanking the score for what's still the
    same project.
    """
    if len(a) > len(b):
        a, b = b, a
    if not a:
        return 0.0
    matcher = difflib.SequenceMatcher(None, a, b)
    best = 0.0
    for block in matcher.get_matching_blocks():
        start = max(0, block.b - block.a)
        window = b[start:start + len(a)]
        best = max(best, difflib.SequenceMatcher(None, a, window).ratio())
    return best


def parse_date(s):
    return s.split("T")[0] if s else None


def fetch_reporter_projects():
    """Fetch every RePORTER project record where Brad is a registered PI/MPI.

    One record per project per fiscal year it was funded in -- a multi-year
    award shows up as multiple records sharing the same core_project_num.
    Paginated defensively even though a personal PI history is nowhere near
    the API's 500-per-request limit.
    """
    all_results = []
    offset = 0
    limit = 500
    while True:
        body = {
            "criteria": {"pi_names": [{"first_name": PI_FIRST_NAME, "last_name": PI_LAST_NAME}]},
            "include_fields": INCLUDE_FIELDS,
            "offset": offset,
            "limit": limit,
        }
        req = urllib.request.Request(
            REPORTER_SEARCH_URL,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        all_results.extend(data["results"])
        total = data["meta"]["total"]
        offset += limit
        if offset >= total:
            break
    return all_results


def group_by_core_project(records):
    """Group per-fiscal-year records by core_project_num, newest fiscal year first."""
    groups = defaultdict(list)
    for r in records:
        groups[r["core_project_num"]].append(r)
    for recs in groups.values():
        recs.sort(key=lambda r: r["fiscal_year"], reverse=True)
    return groups


def load_csv(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def match_project_to_grant(core_project_num, latest_record, grants):
    """Find the grants.csv row a RePORTER project represents, if any.

    Exact award_number match is authoritative. Otherwise fall back to a
    fuzzy title match, so a stale/wrong award_number in the CSV still gets
    recognized as "this project, flag the number" instead of "brand-new
    grant." As a last resort, fall back to an exact project_start_date match
    -- some CSV rows hold a center/program's generic name (e.g. "Edward R.
    Roybal Centers for Translational Research...") rather than this specific
    award's actual project title, which defeats fuzzy title matching too,
    but NIH start dates are precise enough that an exact match is still a
    reliable signal nothing else would produce by coincidence.
    """
    for row in grants:
        if row["award_number"].strip() == core_project_num:
            return row, 1.0, "award_number"

    best_row, best_ratio = None, 0.0
    normalized_reporter_title = normalize_title(latest_record["project_title"])
    for row in grants:
        ratio = partial_ratio(normalized_reporter_title, normalize_title(row["title"]))
        if ratio > best_ratio:
            best_row, best_ratio = row, ratio

    if best_ratio >= TITLE_MATCH_THRESHOLD:
        return best_row, best_ratio, "title"

    reporter_start_date = parse_date(latest_record["project_start_date"])
    for row in grants:
        if reporter_start_date and row["start_date"].strip() == reporter_start_date:
            return row, best_ratio, "start_date"

    return None, best_ratio, None


def build_flags(row, core_project_num, match_kind, ratio, latest_record):
    """Compare a matched grants.csv row against RePORTER's latest record for it."""
    flags = []

    if match_kind == "title":
        flags.append(
            f"award_number mismatch: CSV has {row['award_number'] or '(blank)'!r}, "
            f"RePORTER's live core project number is {core_project_num!r} "
            f"(matched by title similarity, ratio={ratio:.2f}) -- "
            f"CSV may hold a pre-award/application number superseded by the Notice of Award."
        )
    elif match_kind == "start_date":
        flags.append(
            f"award_number mismatch: CSV has {row['award_number'] or '(blank)'!r}, "
            f"RePORTER's live core project number is {core_project_num!r} "
            f"(matched by exact project_start_date since the CSV title -- {row['title'][:60]!r} -- "
            f"looks like a program/center name rather than this award's actual project title, "
            f"which is {latest_record['project_title'][:60]!r} in RePORTER)"
        )

    reporter_mechanism = latest_record["activity_code"]
    if row["mechanism"].strip() and row["mechanism"].strip() != reporter_mechanism:
        flags.append(f"mechanism: CSV {row['mechanism']!r} vs RePORTER {reporter_mechanism!r}")

    reporter_end_date = parse_date(latest_record["project_end_date"])
    csv_end_date = row["end_date"].strip()
    if reporter_end_date and csv_end_date and reporter_end_date != csv_end_date:
        flags.append(
            f"end_date: CSV {csv_end_date} vs RePORTER (latest reported FY {latest_record['fiscal_year']}) "
            f"{reporter_end_date} -- possible no-cost extension or CSV needs updating"
        )

    today = date.today().isoformat()
    csv_status = row["status"].strip()
    if reporter_end_date:
        reporter_active = reporter_end_date >= today
        if csv_status == "completed" and reporter_active:
            flags.append(f"status: CSV says 'completed' but RePORTER shows the award active through {reporter_end_date}")
        elif csv_status == "funded" and not reporter_active:
            flags.append(f"status: CSV says 'funded' (active) but RePORTER's latest reported end date {reporter_end_date} has passed")

    return flags


def print_report(matched_flags, new_candidates, budget_coverage):
    print("\n=== Reconciliation flags (matched grants.csv rows) ===")
    if not matched_flags:
        print("  none -- all matched NIH grants agree with RePORTER")
    for grant_id, title, flags in matched_flags:
        print(f"\n  {grant_id}: {title[:70]!r}")
        for flag in flags:
            print(f"      - {flag}")

    print("\n=== New NIH grant candidates (Brad is PI on RePORTER, no grants.csv match) ===")
    if not new_candidates:
        print("  none")
    for core_project_num, latest in new_candidates:
        print(
            f"  {core_project_num} | {latest['activity_code']} | "
            f"{latest['agency_ic_admin']['abbreviation']} | FY{latest['fiscal_year']} | "
            f"{latest['project_title'][:70]!r}"
        )
    if new_candidates:
        print("  -> use the add-academic-entry skill to add these.")

    print("\n=== budget_years.csv coverage (matched grants only, informational) ===")
    if not budget_coverage:
        print("  none")
    for grant_id, reporter_fys, reporter_total, existing_rows, existing_total in budget_coverage:
        print(f"\n  {grant_id}: RePORTER reports {len(reporter_fys)} fiscal year(s), budget_years.csv has {existing_rows} row(s)")
        for fy, amt in reporter_fys:
            print(f"      FY{fy}: ${amt:,}")
        print(f"      RePORTER total (obligated to date): ${reporter_total:,}  |  budget_years.csv total: ${existing_total:,}")
        if len(reporter_fys) != existing_rows:
            print("      -> row count differs from RePORTER's fiscal-year count; review for a possibly missing/extra year")


def main():
    print(f"Fetching NIH RePORTER projects for PI {PI_FIRST_NAME} {PI_LAST_NAME}...")
    records = fetch_reporter_projects()
    projects = group_by_core_project(records)
    print(f"  {len(records)} fiscal-year record(s) across {len(projects)} project(s) found")

    grants, _ = load_csv(GRANTS_CSV)
    budget_years, _ = load_csv(BUDGET_YEARS_CSV)
    budget_years_by_grant = defaultdict(list)
    for row in budget_years:
        budget_years_by_grant[row["grant_id"]].append(row)

    matched_flags = []
    new_candidates = []
    budget_coverage = []

    for core_project_num, recs in projects.items():
        latest = recs[0]
        row, ratio, match_kind = match_project_to_grant(core_project_num, latest, grants)

        if row is None:
            new_candidates.append((core_project_num, latest))
            continue

        flags = build_flags(row, core_project_num, match_kind, ratio, latest)
        if flags:
            matched_flags.append((row["id"], row["title"], flags))

        reporter_fys = sorted({(r["fiscal_year"], r["award_amount"]) for r in recs})
        reporter_total = sum(amt for _, amt in reporter_fys)
        existing = budget_years_by_grant.get(row["id"], [])
        existing_total = sum(int(r["cost"]) for r in existing if r["cost"].strip())
        budget_coverage.append((row["id"], reporter_fys, reporter_total, len(existing), existing_total))

    print_report(matched_flags, new_candidates, budget_coverage)
    print("\nThis script never writes to any CSV -- it's a review report only.")
    print("Fix grants.csv by hand for reconciliation flags; use the add-academic-entry skill for new grants.")


if __name__ == "__main__":
    main()
