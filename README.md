# Academic Database and Dashboard

A plain-text CSV backend and [Quarto](https://quarto.org) dashboard front end for tracking
Brad Cannell's academic activity: publications, grants, presentations, teaching, service,
mentoring, awards, and professional memberships. This repo replaces a Google Sheet that
served the same purpose.

## Architecture

- **Data**: one CSV file per entity in `data/`, hand-edited or AI-assisted, versioned in git.
- **Access**: queried directly with R (`readr` / `dplyr`) — no database engine (no
  DuckDB/SQLite) in v1.
- **Presentation**: a Quarto dashboard (`format: dashboard`) rendered locally. No
  Shiny, no automated publishing (GitHub Pages/Netlify) yet — that decision is deferred
  until there's been time to weigh exposing award numbers and dollar amounts publicly.

## Conventions

- **One row per real-world thing.** Each CSV row represents a single publication, grant,
  presentation, etc.
- **Stable `id` keys** are used where a natural key doesn't already exist (e.g.
  `publications.id`, `grants.id`, `presentations.id`, `peer_reviews.id`). Other entities are
  keyed by their natural key (e.g. `mentee_name`, `organization`) since duplicates aren't
  expected.
- **Dates**: ISO 8601 (`YYYY-MM-DD`) where a full date is known. Where source data only has
  partial precision (e.g. a publication year but not a month), separate `year`/`month`/`day`
  columns are used instead, and unknown components are left blank.
- **Booleans**: `TRUE` / `FALSE`.
- **Blank vs. zero**: leave a cell blank when a value is unknown or not applicable; don't use
  `0` or `NA` as a stand-in for missing data.
- **Controlled vocabularies** are documented per-entity below. Use these exact values (case
  and spelling) so downstream filtering/grouping in the dashboard works without cleanup.

## Data model

### `data/publications.csv`

| column | description |
|---|---|
| `id` | stable identifier |
| `publication_type` | `peer_reviewed_article` \| `book` \| `chapter` \| `other` |
| `title` | publication title |
| `authors` | full author list, as cited |
| `journal_or_venue` | journal name or venue |
| `year`, `month`, `day` | publication date (partial precision allowed) |
| `DOI` | digital object identifier |
| `PMID` | PubMed ID |
| `url` | link to the publisher's online version of the article |
| `author_position` | Brad's position in the author list (e.g. `first`, `last`, `middle`) |
| `mentee_author` | `TRUE`/`FALSE` — a mentee is a co-author |
| `multi_institution` | `TRUE`/`FALSE` — authors span multiple institutions |
| `status` | `published` \| `in-press` \| `under-review` |
| `notes` | free text |

### `data/grants.csv`

| column | description |
|---|---|
| `id` | stable identifier |
| `award_number` | sponsor-assigned award/grant number |
| `mechanism` | funding mechanism (e.g. `R01`, `R21`, `K01`) |
| `sponsor` | full sponsor/funder name |
| `funder_abbreviation` | short funder code (e.g. `NIH`, `NIA`) |
| `title` | grant title |
| `role` | Brad's role (e.g. `PI`, `Co-I`, `Consultant`) |
| `status` | `planned` \| `submitted` \| `funded` \| `rejected` \| `completed` |
| `total_cost` | total award amount |
| `start_date`, `end_date` | ISO 8601 dates |
| `effort_percent` | Brad's effort commitment on this grant |

### `data/effort_by_year.csv`

| column | description |
|---|---|
| `year` | calendar or academic year |
| `effort_percentage` | total percent effort committed across all grants that year |

### `data/budget_years.csv` (optional)

| column | description |
|---|---|
| `grant_id` | references `grants.id` |
| `award_year_label` | e.g. `Year 1`, `Year 2` |
| `cost` | budget for that award year |

### `data/presentations.csv`

| column | description |
|---|---|
| `id` | stable identifier |
| `title` | presentation title |
| `presentation_type` | `invited` \| `conference-oral` \| `conference-poster` \| `panel` |
| `venue_name` | conference or event name |
| `location` | city/state or venue location |
| `year`, `month`, `day` | presentation date (partial precision allowed) |
| `authors` | full author/presenter list |
| `notes` | free text |

### `data/teaching.csv`

| column | description |
|---|---|
| `institution` | institution name |
| `department` | department name |
| `course_code` | course number/code |
| `course_title` | course title |
| `start_year`, `end_year` | years taught (blank `end_year` if ongoing) |
| `role` | `instructor-of-record` \| `course-director-other` |
| `notes` | free text |

### `data/service.csv`

| column | description |
|---|---|
| `start_year`, `end_year` | years of service (blank `end_year` if ongoing) |
| `category` | `community` \| `university` \| `profession` \| `editorial` |
| `role` | role/title held |
| `organization` | organization or committee name |
| `notes` | free text |

### `data/service_log.csv`

| column | description |
|---|---|
| `date` | ISO 8601 date |
| `hours`, `minutes` | time spent |
| `type` | type of service activity |
| `description` | free text |

### `data/reviewer_relationships.csv`

| column | description |
|---|---|
| `journal_or_venue` | journal or venue name |
| `relationship_type` | `editorial-board` \| `ad-hoc-reviewer` \| `software-reviewer` |
| `status` | `ongoing` \| `ended` |

### `data/peer_reviews.csv`

| column | description |
|---|---|
| `id` | stable identifier |
| `journal` | journal name |
| `manuscript_title` | title of the reviewed manuscript |
| `date_start`, `date_end` | ISO 8601 dates the review was open |
| `rounds` | number of review rounds completed |
| `published` | `TRUE`/`FALSE` — whether the manuscript was ultimately published |

### `data/mentoring.csv`

| column | description |
|---|---|
| `mentee_name` | mentee's name |
| `role` | `primary-advisor` \| `committee-member` \| `ra-ta-intern` \| `external-mentee` \| `postdoc-mentee` \| `faculty-mentee` |
| `degree_or_context` | degree program or mentoring context |
| `start_year`, `end_year` | years of the mentoring relationship (blank `end_year` if ongoing) |
| `primary_advisor` | `TRUE`/`FALSE` — Brad is the primary advisor |
| `current_status` | mentee's current status (e.g. `graduated`, `in-program`, `faculty`) |
| `role_detail` | free text elaborating on `role` |

### `data/advising_load.csv`

| column | description |
|---|---|
| `academic_year` | academic year (e.g. `2024-2025`) |
| `advisee_count` | number of advisees that year |

### `data/awards.csv`

| column | description |
|---|---|
| `year` | year received |
| `award_name` | award name |
| `granting_body` | organization that granted the award |
| `notes` | free text |

### `data/professional_memberships.csv`

| column | description |
|---|---|
| `organization` | full organization name |
| `abbreviation` | short code (e.g. `APHA`) |
| `start_year`, `end_year` | membership years (blank `end_year` if ongoing) |
| `notes` | free text |

## Status

- **Phase 0 — done.** Google Sheet and CV both audited; data model is final.
- **Phase 1 — done.** Repo scaffolding — schema defined, CSVs created.
- **Phase 2 — done.** Data migrated from the Google Sheet and CV into all 14 CSVs (CV wins
  where the two disagreed on funding/publications). `scripts/validate_csvs.py` passes clean.
- **Phase 3 — done.** `dashboard/index.qmd` renders cleanly with `quarto render
  dashboard/index.qmd` and has been visually verified across all four pages (Overview,
  Funding, Publications, Teaching & Mentoring).
- **Phase 4 — done.** The `add-academic-entry` skill (paste a citation/award notice/CV
  bullet, get a previewed CSV row, confirm, auto-validate) is built. ORCID/PubMed ingest
  (`scripts/ingest_orcid_pubmed.py`) is also built and has backfilled DOI/PMID values for
  existing publications from ORCID's public API. NIH RePORTER ingest
  (`scripts/ingest_nih_reporter.py`) is also built — a preview-only reconciliation report
  (never writes to any CSV) that already caught and fixed three real `grants.csv` errors on
  its first run: a stale award number and program-name-instead-of-project-title for the
  Roybal Center grant, and two no-cost-extension end dates that hadn't been updated. A
  scheduled monthly refresh (`.github/workflows/monthly-refresh.yml`) runs both ingest
  scripts and re-renders the dashboard as a smoke test on the 1st of each month, opening a
  GitHub Issue with the results — report-only, it never writes to a CSV or commits. Verified
  working via two manual test runs 2026-07-11. One open item from testing: RePORTER's
  budget-year coverage report flagged that grant-02's `budget_years.csv` total ($4,664,014
  across 3 rows) doesn't match RePORTER's 2 reported fiscal years ($3,056,003) — needs manual
  review, same category of issue as the grant-01/grant-05 gaps fixed earlier.
- **Phase 5 — not started.** Retire the Google Sheet once this system has handled a full
  month of real updates.

See `CLAUDE.md` for pointers back to the full planning notes.
