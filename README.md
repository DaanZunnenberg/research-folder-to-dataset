# Alchemist

A Claude Code skill that turns a messy folder of research/analyst files (PDFs, DOCX,
XLSX/CSV, Markdown, TXT, images) into a clean, structured, auditable dataset — with an
inferred schema, per-field provenance, confidence scores, and a human-readable extraction
report.

## Install

Copy the `alchemist/` directory into your Claude Code skills directory:

```bash
cp -r alchemist ~/.claude/skills/
```

(Or into a project-local `.claude/skills/` directory if you want it scoped to one repo.)

No installation step beyond copying the files is required — the bundled scripts
(`scripts/extract_content.py`, `scripts/build_outputs.py`, `scripts/normalize_helpers.py`) use
only the Python 3 standard library. If `pypdf`, `openpyxl`, or `pytesseract`+`Pillow` happen to
be installed in the environment, the skill uses them for better PDF extraction, `.xlsx` output,
and image OCR respectively — but none are required.

## Usage

Point Claude Code at a folder and ask:

> Turn this folder into a dataset.

or more specifically:

> Use Alchemist on `./my_research_folder`, output to `./dataset_output`.

Claude will:
1. Inventory and extract content from every file (ignoring OS junk/duplicates).
2. Propose a schema and show it to you before extracting the full dataset.
3. Extract one record per sample/document/entity, normalizing dates/units/categories while
   preserving original values.
4. Track provenance and confidence for every field, and flag conflicts/outliers/duplicates
   instead of silently resolving them.
5. Write `dataset.csv`, `dataset.json`, `dataset.xlsx` (if available), `extraction_report.md`,
   and a dataset-specific `README.md` to the output directory.

See `SKILL.md` for the full workflow, schema-inference rules, normalization rules, provenance
conventions, confidence rubric, and conflict/deduplication handling that Claude follows.

## Worked example

`examples/input/` contains 8 synthetic, deliberately messy files about a plant salinity-stress
growth trial — lab notes, a reanalysis CSV, a summary DOCX, a PDF field-notes page, an XLSX
master list, an exact-duplicate file, an irrelevant file, and an OS metadata file. Several
sources report conflicting measurements for the same samples on purpose.

`examples/output/` contains the full result of running Alchemist's workflow against that input:
`proposed_schema.md`, `dataset.csv`, `dataset.json`, `extraction_report.md`, and a
dataset-specific `README.md`. Use it as a reference for expected output shape, tone, and how
conflicts/missing data/outliers should be represented — not as a template to copy schema from,
since every real folder needs its own schema inferred from its own content.

## Directory layout

```
alchemist/
  SKILL.md                       # full instructions Claude follows
  scripts/
    extract_content.py           # stdlib-only file inventory + text/table extraction
    build_outputs.py             # validates dataset.json, writes csv/json/xlsx
    normalize_helpers.py         # date/number normalization helpers (CLI)
  examples/
    input/                       # synthetic messy source files
    output/                      # expected end-to-end output for the example
  README.md                      # this file
```

## Design principles

- **Correctness and auditability over completeness.** Missing or conflicting values are
  reported as such, never guessed.
- **Deterministic code for the mechanical parts** (file parsing, CSV/JSON/XLSX serialization,
  schema validation), reasoning/judgment left to the agent (schema inference, unit-of-analysis
  choice, conflict interpretation).
- **Domain-agnostic.** Nothing in the scripts encodes the example's plant-biology schema — the
  schema is always inferred fresh from whatever folder is provided.
