#!/usr/bin/env python3
"""Reconcile Brad's ORCID works against data/publications.csv.

Pulls the public ORCID works list (no auth required), matches each work to an
existing publications.csv row by DOI or fuzzy title match, and looks up
PubMed for PMIDs on any row where a DOI is known (from ORCID or already in
the CSV) but the PMID column is still blank.

Preview only by default -- nothing is written unless you pass --apply, and
even then only DOI/PMID backfills on *existing* rows are written. ORCID
works with no matching row are only ever previewed; use the
add-academic-entry skill to add them as new rows, since that step asks for
fields (authors, status, author_position, etc.) this script has no way to
fill in on its own.

Usage:

    python3 scripts/ingest_orcid_pubmed.py            # preview only
    python3 scripts/ingest_orcid_pubmed.py --apply     # write backfills, then re-run:
    python3 scripts/validate_csvs.py                   # confirm the CSV is still clean

Uses only the standard library so it runs without installing anything.
"""

import argparse
import csv
import difflib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ORCID_ID = "0000-0002-8711-6772"
ORCID_WORKS_URL = f"https://pub.orcid.org/v3.0/{ORCID_ID}/works"
EUTILS_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLICATIONS_CSV = REPO_ROOT / "data" / "publications.csv"

# Naive substring/exact matching misses trivial wording differences ("&" vs
# "and", "healthcare" vs "health care") that show up between how a title is
# recorded in ORCID/Crossref vs. how it was typed into the CSV from the CV.
# A similarity ratio absorbs those without needing hand-written cleanup rules.
TITLE_MATCH_THRESHOLD = 0.90

USER_AGENT = "academic-database-ingest/1.0 (personal use; brad.cannell@gmail.com)"


def normalize_title(title):
    title = re.sub(r"<[^>]+>", " ", title)  # ORCID titles sometimes carry stray markup, e.g. "<scp>DETECT</scp>"
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def fetch_json(url, params=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_orcid_works():
    data = fetch_json(ORCID_WORKS_URL)
    works = []
    for group in data["group"]:
        # Each "group" can bundle multiple sources (e.g. Crossref + a manual
        # entry) for the same work; the first work-summary is ORCID's own
        # picked representative, which is good enough for matching purposes.
        summary = group["work-summary"][0]
        title = summary["title"]["title"]["value"]
        pub_date = summary.get("publication-date") or {}
        year = (pub_date.get("year") or {}).get("value")
        doi = next(
            (e["external-id-value"] for e in group["external-ids"]["external-id"] if e["external-id-type"] == "doi"),
            None,
        )
        works.append({
            "title": title,
            "normalized_title": normalize_title(title),
            "year": year,
            "doi": doi.lower() if doi else None,
            "type": summary["type"],  # e.g. journal-article, preprint
        })
    return works


def load_publications():
    with open(PUBLICATIONS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    return rows, fieldnames


def partial_ratio(a, b):
    """Best alignment ratio of the shorter string against a same-length window of the longer one.

    Plain difflib ratio penalizes a short title for being a truncated
    prefix of a longer one -- and that's exactly what ORCID/Crossref often
    do, dropping a paper's subtitle (e.g. "...Results from the Florida
    Behavioral Risk Factor Surveillance System") that the CV-sourced CSV
    title kept. This searches for the best-aligning window in the longer
    string instead of scoring against the whole thing, so a dropped
    subtitle doesn't tank the score for what's still the same paper.
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


def match_work_to_row(work, rows_by_doi, rows):
    """Find the CSV row a given ORCID work represents, if any.

    DOI is authoritative when both sides have one. Otherwise fall back to
    the best fuzzy title match, accepted only above TITLE_MATCH_THRESHOLD so
    unrelated papers on similar topics don't get merged together.
    """
    if work["doi"] and work["doi"] in rows_by_doi:
        return rows_by_doi[work["doi"]], 1.0, "doi"

    best_row, best_ratio = None, 0.0
    for row in rows:
        ratio = partial_ratio(work["normalized_title"], normalize_title(row["title"]))
        if ratio > best_ratio:
            best_row, best_ratio = row, ratio

    if best_ratio >= TITLE_MATCH_THRESHOLD:
        return best_row, best_ratio, "title"
    return None, best_ratio, None


def lookup_pmid_by_doi(doi):
    time.sleep(0.34)  # stay under NCBI's ~3 req/sec limit for unauthenticated E-utilities calls
    try:
        result = fetch_json(EUTILS_ESEARCH_URL, {"db": "pubmed", "retmode": "json", "term": f"{doi}[doi]"})
    except urllib.error.URLError as e:
        print(f"    (PubMed lookup failed for {doi}: {e})")
        return None
    idlist = result.get("esearchresult", {}).get("idlist", [])
    return idlist[0] if idlist else None


def build_backfill_and_candidates(works, rows):
    rows_by_doi = {r["DOI"].strip().lower(): r for r in rows if r["DOI"].strip()}

    row_to_work = {}  # row id -> (work, ratio, match_kind)
    new_candidates = []
    skipped_preprints = []

    for work in works:
        row, ratio, kind = match_work_to_row(work, rows_by_doi, rows)
        if row:
            row_to_work[row["id"]] = (work, ratio, kind)
        elif work["type"] == "preprint":
            # A preprint with no matching row is very likely the pre-print
            # stage of a paper whose published version already matched a
            # different work in this same ORCID list -- not a distinct
            # publication worth its own row. Surface it separately rather
            # than silently dropping it, in case that assumption is wrong.
            skipped_preprints.append(work)
        else:
            new_candidates.append(work)

    # Backfill candidates come from *every* CSV row, not just ORCID-matched
    # ones -- a row can already have a DOI (e.g. entered by hand) and still
    # be missing its PMID, which ORCID never supplies either way.
    backfill = []
    for row in rows:
        existing_doi = row["DOI"].strip()
        work, ratio, kind = row_to_work.get(row["id"], (None, None, None))
        effective_doi = existing_doi.lower() or (work["doi"] if work else None)
        needs_doi = not existing_doi and effective_doi
        needs_pmid = not row["PMID"].strip() and effective_doi
        if needs_doi or needs_pmid:
            backfill.append({
                "row": row,
                "work": work,
                "match_kind": kind,
                "ratio": ratio,
                "effective_doi": effective_doi,
                "needs_doi": bool(needs_doi),
            })

    return backfill, new_candidates, skipped_preprints


def print_preview(backfill, new_candidates, skipped_preprints):
    print("\n=== Backfill candidates (existing rows, filling blank DOI/PMID) ===")
    if not backfill:
        print("  none")
    for item in backfill:
        row = item["row"]
        label = f"{item['match_kind']} match, ratio={item['ratio']:.2f}" if item["match_kind"] else "DOI already on file"
        print(f"  {row['id']} ({label}): {row['title'][:60]!r}")
        if item["needs_doi"]:
            print(f"      DOI:  (blank) -> {item['effective_doi']}")
        if item.get("pmid"):
            print(f"      PMID: (blank) -> {item['pmid']}")
        elif not row["PMID"].strip():
            print(f"      PMID: (blank) -> no match found on PubMed")

    print("\n=== New-row candidates (ORCID works with no match in publications.csv) ===")
    if not new_candidates:
        print("  none")
    for work in new_candidates:
        print(f"  {work['year']} | {work['doi']} | {work['title'][:70]!r}")
    if new_candidates:
        print("  -> use the add-academic-entry skill to add these; this script never writes new rows.")

    if skipped_preprints:
        print(f"\n=== Skipped ({len(skipped_preprints)} preprint(s) with no matching published row) ===")
        for work in skipped_preprints:
            print(f"  {work['year']} | {work['doi']} | {work['title'][:70]!r}")


def apply_backfill(backfill, rows, fieldnames):
    applied = 0
    for item in backfill:
        row = item["row"]
        changed = False
        if item["needs_doi"]:
            row["DOI"] = item["effective_doi"]
            changed = True
        if item.get("pmid"):
            row["PMID"] = item["pmid"]
            changed = True
        if changed:
            applied += 1

    with open(PUBLICATIONS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return applied


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write backfilled DOI/PMID values into data/publications.csv")
    args = parser.parse_args()

    print(f"Fetching ORCID works for {ORCID_ID}...")
    works = fetch_orcid_works()
    print(f"  {len(works)} works found on ORCID")

    rows, fieldnames = load_publications()
    backfill, new_candidates, skipped_preprints = build_backfill_and_candidates(works, rows)

    if backfill:
        print("\nChecking PubMed for PMIDs...")
        for item in backfill:
            if not item["row"]["PMID"].strip():
                item["pmid"] = lookup_pmid_by_doi(item["effective_doi"])
            else:
                item["pmid"] = None

    print_preview(backfill, new_candidates, skipped_preprints)

    if not args.apply:
        print("\nPreview only -- rerun with --apply to write DOI/PMID backfills into data/publications.csv")
        return

    if not backfill:
        print("\nNothing to apply.")
        return

    applied = apply_backfill(backfill, rows, fieldnames)
    print(f"\nWrote backfilled values for {applied} row(s) to {PUBLICATIONS_CSV}")
    print("Run scripts/validate_csvs.py to confirm the CSV is still clean.")


if __name__ == "__main__":
    main()
