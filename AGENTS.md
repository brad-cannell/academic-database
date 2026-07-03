# AGENTS.md

Project context for Codex when working in this repo.

## What this is

Brad Cannell's academic database: a plain-text CSV backend (`data/*.csv`) plus a Quarto
dashboard front end, replacing a Google Sheet that previously tracked publications, grants,
presentations, teaching, service, mentoring, and awards.

See `README.md` for the full data model (all 14 CSVs, their columns, and controlled
vocabularies). Read it before adding or editing data — column names and allowed values are
documented there and should be followed exactly so the dashboard doesn't need cleanup logic.

## Origin and planning notes

Full planning for this project happened in the `knowledge-workbench` vault, at:

- `Notes/ADR/Academic Database and Dashboard Plan.md` — the architecture decision record
  with full rationale.
- `Tasks/KWB/Create an Academic Database and Dashboard.md` — the task breakdown.

If `knowledge-workbench` is ever attached alongside this repo in a session, consult those
notes for anything not covered here, and register this repo in its `_context/satellites.md`
(follow the existing entry format: path/github/domain/status/claude-md/last-touched/note).

## Decisions already made (do not re-litigate)

1. **Architecture**: one CSV file per entity, queried directly with R (`readr`/`dplyr`),
   rendered as a Quarto dashboard (`format: dashboard`). No DuckDB/SQLite/Shiny in v1.
2. **Repo**: a new satellite repo (this one), not a folder inside an existing repo.
3. **Publishing**: local rendering only for now — no GitHub Pages/Netlify. The repo is
   public, but the publish decision is deferred until there's been time to weigh exposing
   award numbers/dollar amounts.
4. **Scope**: v1 includes presentations, teaching, and awards (sourced from Brad's CV), not
   just the Google Sheet's original six entities.
5. **`professional_memberships.csv`** is included in v1, not deferred.
6. **Source of truth on conflicts**: where the Google Sheet and CV disagree (funding,
   publications), the CV wins during migration.

## Conventions

- Stable `id` keys where a natural key doesn't already exist.
- ISO 8601 dates, or separate `year`/`month`/`day` columns where source data only has
  partial precision.
- Controlled vocabularies documented in `README.md` — use exact values.
- One row per real-world thing.

## Phased plan

- **Phase 0 — done.** Google Sheet and CV both audited; data model is final.
- **Phase 1 — done (this commit).** Repo scaffolding: `CLAUDE.md`/`AGENTS.md`, `README.md`, empty CSVs
  (header row only) for all 14 entities.
- **Phase 2 — migrate.** Convert the Google Sheet's rows and the CV's sections into the
  CSVs, reconciling overlaps per decision #6 (CV wins).
- **Phase 3 — dashboard v1.** Quarto dashboard: headline counts by year, funding summary,
  teaching load, active mentoring/service tables.
- **Phase 4 — automation.** AI entry skill first, then ORCID/PubMed ingest, then NIH
  RePORTER, then a scheduled monthly refresh.
- **Phase 5 — retire the Google Sheet** once the new system has handled a full month of
  real updates.

## AI skills

This repo has no `_ai/agent-workflows/` canonical-source-and-sync-script setup like
knowledge-workbench does — skills here are hand-authored directly into each mirror location,
and any edit has to be applied to both mirrors by hand.

To add a new skill `<name>`:

1. Write `.claude/skills/<name>/SKILL.md` (Claude Code) with YAML frontmatter (`name`,
   `description`), a `## Usage` section showing both invocations, and an `## Instructions`
   section with the exact command(s) to run.
2. Copy that file verbatim to `.agents/skills/<name>/SKILL.md` (Codex mirror), and add
   `.agents/skills/<name>/agents/openai.yaml` with:
   ```yaml
   policy:
     allow_implicit_invocation: true
   ```
3. Optionally add a legacy command mirror at `.claude/commands/<name>.md` — same body as the
   skill, minus the `name:` frontmatter field and the `## Usage` section.
4. Document the skill's purpose here in `CLAUDE.md`/`AGENTS.md` if it changes how the repo
   should be worked in (e.g. a new required pre-commit check).

Existing skills:

- **`validate-csvs`** — runs `scripts/validate_csvs.py` against `data/*.csv` and reports
  errors/warnings. See "Working in this repo" below for when to run it.

## Working in this repo

- Don't add a database engine, Shiny, or a publishing pipeline — those are explicitly out
  of scope for v1 per the decisions above.
- When migrating data (Phase 2), prefer small, reviewable batches per entity over one giant
  commit, so Brad can spot-check accuracy against the CV/Google Sheet as we go.
- After editing any `data/*.csv`, run `python3 scripts/validate_csvs.py` (stdlib only, no
  install needed) and fix anything it flags before committing. It checks headers, controlled
  vocabularies, booleans, dates/years, id uniqueness, and foreign keys (e.g.
  `budget_years.grant_id` → `grants.id`) against the schema in `README.md`. It's manual for
  now (run it yourself); wiring it into a pre-commit hook or CI is planned once the schema
  has settled.
