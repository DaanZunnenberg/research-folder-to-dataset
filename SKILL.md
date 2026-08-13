---
name: research-folder-to-dataset
description: Turn a messy folder of research/analyst files (PDFs, DOCX, XLSX/CSV, Markdown, TXT, images) into a clean, structured, auditable dataset with inferred schema, provenance, confidence scores, and a human-readable extraction report. Use when the user says things like "turn this folder into a dataset", "extract structured data from these files", "build a dataset from these papers/notes/reports", or points at a directory of research/lab/analyst documents and wants CSV/JSON/XLSX output.
---

# research-folder-to-dataset

## Purpose

Convert an unstructured folder of documents into:
1. A **proposed schema** the user can sanity-check before full extraction.
2. A **structured dataset** (`dataset.csv`, `dataset.json`, optionally `dataset.xlsx`) with
   one row per relevant entity/document/experiment/sample.
3. A **provenance trail** so every non-obvious value can be traced back to its source file,
   location, and quote.
4. A **human-readable extraction report** documenting what was done, what's missing, what
   conflicts, and what's low-confidence.

Optimize for **correctness and auditability over completeness**. A dataset that is 80% filled
in with clear gaps and honest confidence scores is far more useful — and trustworthy — than one
that is 100% filled in with fabricated values.

## When to use this skill

- The user points Claude Code at a folder of research files (lab notes, papers, experiment logs,
  survey exports, financial reports, interview transcripts, etc.) and asks for a dataset, table,
  or structured extraction.
- The user says "turn this folder into a dataset", "make this into a spreadsheet/CSV", "extract
  the key facts from these documents", or similar.
- General analyst/knowledge-worker use is fine too (e.g., a folder of vendor contracts, meeting
  notes, or product spec sheets) — the workflow is domain-agnostic.

Not a fit for: a single well-structured file that's already tabular and clean (just read it
directly), or truly free-form creative writing with no repeated structure to extract.

## Inputs

- `input_dir` — path to the folder to process (required; ask the user if not given, default to
  the current directory only if that's clearly what they mean).
- `output_dir` — where to write outputs (default: `<input_dir>/../dataset_output` or a
  user-specified path — confirm before writing outside the project directory).
- Optional user hints: a specific unit of analysis ("one row per patient", "one row per
  experiment run"), fields they already know they want, or a domain hint. Use these if given;
  otherwise infer.

## Outputs (all written to `output_dir`)

- `proposed_schema.md` — the schema proposal shown to the user *before* full extraction.
- `dataset.csv` — one row per record, flattened values only.
- `dataset.json` — full structured dataset including provenance, confidence, status, and
  raw/normalized value pairs per field.
- `dataset.xlsx` — same as CSV but with a `schema` sheet and conditional highlighting for
  low-confidence and conflicting cells (only if `openpyxl` is available in the environment; if
  not, note this in the report and skip it — do not treat it as a failure).
- `extraction_report.md` — human-readable audit summary (see structure below).
- `README.md` — explains the schema, transformations, provenance conventions, and limitations
  for whoever inherits this dataset next.

## Workflow

Work through these steps in order. Do not skip the schema-proposal checkpoint — extracting
straight to a dataset without confirming the shape wastes work when the inferred schema is wrong.

### Step 1 — Inventory and extract raw content (deterministic)

Run the bundled script to walk the folder recursively, classify every file, skip obvious junk,
and extract text/tabular content:

```bash
python3 scripts/extract_content.py <input_dir> <scratch>/inventory.json
```

This is stdlib-only (no required dependencies) and:
- Ignores OS metadata/temp/lock files automatically (`.DS_Store`, `Thumbs.db`, `~$*.docx`,
  `._*`, `*.tmp`, etc.) — see the script for the full ignore list.
- Extracts text from `.txt`/`.md`, `.csv`/`.tsv`, `.docx`, `.xlsx`/`.xlsm`, and `.pdf` using only
  the standard library (zipfile + XML parsing for OOXML formats; a small FlateDecode + Tj/TJ
  scanner for PDF text). If `pypdf` happens to be installed in the environment it will be used
  for more reliable PDF extraction, but nothing requires it.
- For images: does not perform OCR by default. If `pytesseract` + `PIL` are available it will
  OCR them; otherwise the image is listed as present-but-unextracted. Inspect such images
  visually (Read tool) if they look load-bearing for the schema.
- Flags exact-duplicate files by content hash (`duplicate_groups` in the output JSON) — these
  are almost certainly redundant copies, not distinct records.
- Never aborts on one bad file. Per-file failures show up as `extraction_error` on that file's
  entry; keep going and mention them in the report.

Read `inventory.json` (or grep/inspect relevant parts of it) to see what you're working with.
For any file where `extraction_error` is set or `skipped` is true, decide whether it matters
enough to inspect manually (e.g. open a scanned PDF with Read and look at it, or note it as an
unrecoverable source in the report).

### Step 2 — Infer the candidate schema

Read across the extracted text/tabular content and determine:

1. **Unit of analysis.** What does one row represent? Common cases: one row per document, one
   row per named entity/sample/subject mentioned repeatedly across documents, one row per
   experiment run, one row per line item in a table. Pick whichever unit the *majority* of the
   source material naturally supports. If genuinely ambiguous, pick the most defensible option
   and say so explicitly in the report's "Assumptions" section — don't ask the user unless the
   ambiguity is severe enough that any choice would silently discard information.
2. **Fields.** Look for information that recurs across multiple files/sections in comparable
   form (an identifier, a date, a measurement, a category, a name). A field that appears in only
   one source document out of many is usually not part of the common schema — treat it as
   document-specific detail, not a dataset column, unless the user's request is about that one
   document type specifically.
3. For each candidate field, determine: `type` (`string`, `number`, `date`, `boolean`,
   `categorical`, `array`), whether it's `required` (present in nearly all records with high
   confidence) or `optional`, and 2-3 real `examples` pulled from the source material.

Schema inference rules:
- Prefer fields with direct textual/tabular evidence over inferred/derived fields.
- If two sources use different granularity for what's plausibly the same field (e.g. "height in
  cm" vs "height in mm" vs "height category: short/medium/tall"), propose ONE normalized field
  plus a `*_raw` field to preserve the original — do not propose three separate columns.
  See "Normalization rules" below.
  the `*_raw` field.
- Do not propose fields for information that appears in zero or one document — that's not a
  schema, that's a one-off fact; mention it in the report instead.
- Cap the proposed schema at a reasonable size (typically 6-20 fields). If the material supports
  far more, group less-central fields as optional rather than omitting them, and say so.

### Step 3 — Present the Proposed Schema (checkpoint)

Before extracting the full dataset, write and show `proposed_schema.md` (and summarize it in
the chat) as a table:

| Field | Description | Type | Required | Examples |
|---|---|---|---|---|

Also state, in one or two sentences: the inferred unit of analysis, and roughly how many records
you expect to produce. If the user is present and interactive, give them a chance to correct the
schema before you do the full extraction pass — this is cheap to fix now and expensive to fix
after 40 records are written. If running non-interactively (e.g. as part of a longer autonomous
task), proceed directly but keep the file so the schema decision is auditable.

### Step 4 — Extract records

For each entity/document/unit-of-analysis identified in Step 2, extract each schema field as a
structured cell, not a bare value:

```json
{
  "value": "2023-03-14",
  "value_raw": "March 14, 2023",
  "status": "normalized",
  "confidence": 0.95,
  "provenance": [{"file": "notebook_p12.pdf", "location": "page 3", "quote": "Measured on March 14, 2023"}],
  "conflict": null
}
```

`status` must be exactly one of:
- `"stated"` — value taken directly from source, no transformation needed.
- `"normalized"` — value was reshaped (date format, unit conversion, categorical relabeling);
  `value_raw` MUST hold the original as-seen text.
- `"inferred"` — value was not stated explicitly but is a reasonable derivation from context
  (e.g. inferring "species: Arabidopsis thaliana" for a record that only says "the plant" but
  is clearly continuing a paragraph about that species). Use sparingly, and the provenance quote
  should point at the context that justifies the inference.
- `"missing"` — genuinely not available. `value` MUST be `null`. Do not guess. Do not use `""`,
  `"N/A"`, `"unknown"`, or `0` as a substitute for `null` — those are lossy and unauditable.

Never fabricate: citations, page numbers, measurements, dates, sample IDs, or any other
metadata. If you cannot point to where a value came from, it is `missing`, not a guess.

### Step 5 — Normalize

Apply these normalization rules, always preserving the original in `value_raw` when the
normalized form differs from the source text:

- **Dates → ISO 8601 (`YYYY-MM-DD`, or `YYYY-MM-DDTHH:MM:SS` if time matters).** Use
  `scripts/normalize_helpers.py date "<raw>"` for common formats. If it reports
  `"ambiguous": true` (e.g. `03/04/2023` with no other disambiguating context), do NOT guess —
  set `status: "missing"` for the normalized field, keep `value_raw`, and flag it in the report
  rather than silently picking MM/DD vs DD/MM.
- **Units → one consistent unit per field**, chosen by whichever unit the majority of sources
  use (or the field description states). Convert others to match. Use
  `scripts/normalize_helpers.py number "<raw>"` to split a numeric value from its unit suffix
  before doing the conversion arithmetic yourself (unit conversion factors are domain-specific,
  so this script does not guess conversion factors — you must apply them explicitly and state
  the factor used in the report if it's not a common one like cm↔mm or kg↔lb).
- **Categorical values → one consistent label set.** E.g. "control", "Control", "0 mM (control)"
  all map to one canonical label; keep the source wording in `value_raw`.
- **Numbers → actual numeric types** in `dataset.json` (not strings), even if the CSV
  representation stringifies them.
- If normalization is not obviously correct (e.g. a unit you can't confidently identify), leave
  `status: "stated"` with the original value and flag it as ambiguous in the report rather than
  normalizing incorrectly.

### Step 6 — Provenance

For every field with `status` in `stated`/`normalized`/`inferred`, include at least one
provenance entry:
- `file`: relative path from `input_dir`.
- `location`: page number (PDF), sheet+cell or sheet name (XLSX/CSV), section/heading (MD/DOCX),
  or a short description if no natural locator exists (e.g. "3rd paragraph").
- `quote`: a short (≤ ~200 char) verbatim excerpt supporting the value. Never invent a quote —
  if you can't produce a real one, the field shouldn't have `status: stated/normalized`.

`missing` fields have no provenance (nothing to cite). `inferred` fields should cite the
surrounding context that justifies the inference.

### Step 7 — Confidence

Assign `confidence` (0.0-1.0) per field when useful — required, non-obvious, or normalized/
inferred fields especially. Rough guide:
- `0.9-1.0`: directly stated, unambiguous, single source.
- `0.6-0.89`: normalized from clear source text, or stated but with minor ambiguity (e.g. OCR
  artifacts, informal phrasing).
- `0.3-0.59`: inferred from context, or normalized from an ambiguous source format.
- `< 0.3`: rarely used — essentially a guess; strongly prefer `missing` instead.
Confidence is optional on fields that are trivially unambiguous (e.g. a filename-derived ID) —
don't pad the dataset with meaningless 1.0s everywhere.

### Step 8 — Detect and handle problems

- **Missing fields**: leave as `status: "missing"`, `value: null`. Tally these per-field in the
  report so the user can see which fields are systematically underreported.
- **Contradictory values across files** (e.g. two sources give different heights for the same
  sample): do NOT silently pick one. Set `conflict` on the field:
  ```json
  "conflict": {
    "description": "Notebook reports 12.4 cm; reanalysis CSV reports 12.6 cm for the same sample.",
    "values": [
      {"value": 12.4, "source": "experiment_notes_batchA.md"},
      {"value": 12.6, "source": "batchA_reanalysis.csv"}
    ]
  }
  ```
  Pick a `value` only if there's a principled reason (e.g. the source explicitly supersedes the
  other, or one is clearly a typo confirmed elsewhere) and explain that reasoning in
  `conflict.description`; otherwise set `value: null`, `status: "missing"` and let the conflict
  object carry both candidates.
- **Suspicious/outlier values**: don't discard or "correct" them. Extract as normal, note the
  suspicion in the extraction report (e.g. "S-06 height of 11mm is ~10x smaller than any other
  sample in this condition; source note calls it non-viable — likely not comparable to other
  records"). Never silently exclude an outlier from the dataset.
- **Duplicate records**: use `_duplicate_of` (record id) and `_duplicate_confidence` (0-1) on the
  record. Only auto-collapse near-certain duplicates (identical source file hash, or same entity
  ID with functionally identical field values). When uncertain — same entity ID but differing
  values, or same values but different entity IDs — keep both records separate and flag with
  `_duplicate_of` pointing at the suspected match plus a note in the report. Never delete a
  record; conservative dedup means "flag, don't merge" by default.
- **Ambiguous mappings** (unclear which field a value belongs to, or which entity a document
  describes): extract your best-defensible interpretation, mark affected fields with lower
  confidence, and describe the ambiguity in the report's Assumptions section.

### Step 9 — Build final outputs (deterministic)

Author `dataset.json` in the shape documented in `scripts/build_outputs.py`'s docstring (schema
array + records array, each field a structured cell as in Step 4). Then run:

```bash
python3 scripts/build_outputs.py <dataset.json> <output_dir>
```

This validates the dataset against its own schema (required fields present, valid status values,
confidence in range, provenance present for stated/normalized fields) and writes
`dataset.csv`, `dataset.json` (re-serialized), `dataset.xlsx` (if `openpyxl` is available), and
`validation_notes.json`. Fix any `"level": "error"` issues it reports before finishing — these
indicate the dataset doesn't match its own declared schema. `"level": "warning"` issues are
worth reviewing but not necessarily blocking (e.g. an optional field missing provenance because
it was legitimately inferred from broad context).

### Step 10 — Write the extraction report

Write `extraction_report.md` covering:
1. **Files processed** — count, list, and how each was handled (extracted cleanly / had errors /
   was ignored as junk / was skipped as unsupported).
2. **Records created** — count and unit of analysis.
3. **Inferred schema** — repeat the proposed schema table (or link to `proposed_schema.md`) plus
   any changes made during extraction.
4. **Normalization performed** — what was normalized and how (date formats seen → ISO, units
   converted and the factors used, categorical labels collapsed).
5. **Missing data** — per-field counts of `missing` values, and any pattern worth flagging.
6. **Conflicts** — list every field-level conflict found, both values, and sources.
7. **Low-confidence fields** — fields/records with confidence < 0.6, and why.
8. **Assumptions** — unit-of-analysis choice, any ambiguous schema/mapping decisions, and the
   reasoning behind them.

### Step 11 — Write README.md

Explain, for someone who did not watch this process happen:
- What the dataset represents and its unit of analysis.
- The schema (field-by-field).
- How values were normalized (dates, units, categories) and where to find the original values
  (`*_raw` fields, `dataset.json` provenance).
- Provenance conventions (`file` / `location` / `quote` meaning).
- Confidence score meaning and how to filter on it.
- Known limitations (what wasn't extracted, what's uncertain, files that failed).

## Schema inference rules (summary)

- One row = the most common recurring identifiable unit across the source material.
- A field must appear, in comparable form, across multiple sources to earn a schema slot.
- Prefer fewer, well-evidenced fields over many speculative ones.
- Always include an implicit identifier field for the unit of analysis (e.g. `sample_id`,
  `document_id`) even if you have to construct one deterministically (e.g. from filename) — note
  when an ID was constructed rather than stated.

## Normalization rules (summary)

- Dates → ISO 8601; never guess ambiguous numeric dates.
- Units → one consistent unit per field, original preserved in `*_raw`.
- Categories → consistent canonical labels, original preserved in `*_raw`.
- Numbers → real numeric types in JSON.
- Any transformation must be reconstructable from `value_raw` — never normalize destructively.

## Provenance rules (summary)

- Every stated/normalized/inferred field cites `file` + `location` + `quote`.
- Quotes are verbatim and short. Never fabricated.
- Missing fields have no provenance by definition.

## Confidence rules (summary)

- 0.9-1.0 direct & unambiguous; 0.6-0.89 normalized/minor ambiguity; 0.3-0.59 inferred/ambiguous
  format; below 0.3 essentially never used — prefer `missing`.

## Conflict handling (summary)

- Never silently resolve. Carry both values plus sources in `conflict`. Only pick a winner with
  explicit, stated justification.

## Deduplication rules (summary)

- Exact file-content duplicates: safe to collapse to one record, note the dropped file paths.
- Same-entity-different-values or same-values-different-entity: keep separate, flag with
  `_duplicate_of` + `_duplicate_confidence`, never auto-merge.

## Output format requirements

- `dataset.csv`: one row per record, header = record id + all schema fields (flattened values)
  + duplicate flags.
- `dataset.json`: full fidelity — schema + records with all cell metadata (status, confidence,
  provenance, conflicts).
- `dataset.xlsx`: only when `openpyxl` is available; mirror of CSV plus a `schema` sheet and
  conditional highlighting for low-confidence/conflicting cells. Its absence is not a failure —
  say so plainly in the report.
- `extraction_report.md` and `README.md`: Markdown, human-readable, no placeholder text.

## Error handling

- A single unreadable/corrupt file must never abort the run. Record the error against that file
  and continue; mention it in the extraction report.
- If `input_dir` doesn't exist or is empty, say so clearly and stop — don't fabricate a dataset
  from nothing.
- If the environment lacks optional libraries (`pypdf`, `openpyxl`, `pytesseract`/`PIL`),
  degrade gracefully (use the stdlib fallback, or skip that output) and note it — do not treat
  it as a hard failure.
- If `build_outputs.py` reports validation errors, fix the underlying `dataset.json` and re-run
  rather than hand-patching `dataset.csv`/`dataset.xlsx` directly (they're derived, not sources
  of truth).

## Examples

See `examples/` for a full worked example: `examples/input/` contains 8 messy synthetic files
(lab notes in Markdown, a reanalysis CSV, a DOCX summary report, a PDF field-notes page, an XLSX
master sample list, a duplicate file, and an OS metadata file plus an irrelevant document) about
a plant salinity-stress growth trial with deliberately overlapping-but-inconsistent measurements
across sources. `examples/output/` contains the resulting `proposed_schema.md`, `dataset.csv`,
`dataset.json`, `extraction_report.md`, and `README.md` produced by running this skill's
workflow end to end. Use it as a reference for expected output shape and tone — not as a
template to hard-code, since the schema must always be inferred fresh from whatever folder is
provided.
