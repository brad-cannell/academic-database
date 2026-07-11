---
description: Turn a pasted citation, award notice, CV bullet, or other academic-activity text into a new row in the right data/*.csv file, preview it, and validate before writing. Use when Brad wants to log a new publication, grant, presentation, teaching assignment, service role, mentoring relationship, award, professional membership, peer review, or reviewer relationship.
---

# add-academic-entry

Turn free-text academic activity (a pasted citation, a notice-of-award email, a CV bullet,
a quick description of a talk or committee role) into a properly formed row in the matching
`data/*.csv` file, without Brad having to hand-edit CSVs or remember the schema.

This is Phase 4's first automation step from
[[Create an Academic Database and Dashboard]] — build this before any ORCID/PubMed/NIH
RePORTER ingest, since it removes the most day-to-day capture friction.

## Instructions

1. Read the pasted text and any context Brad gives. Identify which entity it belongs to:
   `publications`, `grants`, `presentations`, `teaching`, `service`, `mentoring`, `awards`,
   `professional_memberships`, `peer_reviews`, or `reviewer_relationships`. If it's not
   obvious (e.g. the text could be a service role or a professional membership), ask.
2. Read `README.md` for that entity's exact column list and controlled vocabularies. Never
   invent a value outside a documented enum (e.g. `publication_type`, `status`,
   `presentation_type`, `role`, `category`, `relationship_type`) — ask Brad if the source
   text doesn't map cleanly onto one of the allowed values.
3. Draft the new row:
   - Generate a stable `id` for entities that use one (`publications`, `grants`,
     `presentations`, `peer_reviews`) — next `entity-NN` after the highest existing number
     in that CSV, zero-padded to match the existing width.
   - Leave a field blank when the source text doesn't say — never fabricate a value (DOI,
     dollar amount, dates, etc.) to fill a gap.
   - Match existing formatting conventions in the target CSV (date format, quoting,
     author-list style).
4. Show Brad the exact row(s) you're about to add, formatted as a diff or a clearly labeled
   preview, before writing anything.
5. On confirmation, append the row(s) to the correct CSV, preserving the existing header and
   column order. Then run the validator and fix anything it flags:

   ```bash
   python3 scripts/validate_csvs.py
   ```

6. Report what was added and the validation result. Do not `git commit` or `git push`
   automatically — leave that to Brad or a separate explicit request, same as any other
   write in this repo.

## Notes

- One row per real-world thing — if the pasted text describes multiple items (e.g. a CV
  section with several presentations), propose multiple rows and confirm the whole batch
  before writing.
- If the entity already looks like it might be a duplicate of an existing row (same title,
  same mentee, same grant number), flag that instead of silently adding a second row.
