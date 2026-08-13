# Extraction Report — Batch A/B Salinity Growth Trial

## 1. Files processed

| File | Type | Handling |
|---|---|---|
| `experiment_notes_batchA.md` | Markdown | Extracted cleanly; primary source for S-01–S-03 |
| `batchA_reanalysis.csv` | CSV | Extracted cleanly; reanalysis measurements for S-01–S-04 |
| `summary_report_batchA.docx` | DOCX | Extracted cleanly; corroborating/summary values for S-01–S-04 |
| `field_notes_batchB.pdf` | PDF | Extracted cleanly (no OCR needed — native text); source for S-05 |
| `master_sample_list.xlsx` | XLSX | Extracted cleanly; source for S-01–S-03 (unit cross-check) and S-06 |
| `experiment_notes_batchA copy.md` | Markdown | **Excluded** — identical SHA-256 hash to `experiment_notes_batchA.md`; treated as a redundant copy, not a separate source |
| `misc_lunch_order.txt` | Text | **Excluded** — content unrelated to the growth trial (team lunch order) |
| `.DS_Store` | OS metadata | **Ignored** — not a content file |

7 of 8 files were content-bearing; 1 was an exact duplicate and correctly excluded; 1 was
irrelevant; 1 was OS metadata. No files failed extraction or produced extraction errors.

## 2. Records created

**6 records**, one per plant sample (`S-01` through `S-06`). This unit of analysis was chosen
because "sample" is the only entity referenced consistently, with comparable measurements,
across all five content-bearing sources.

## 3. Inferred schema

See `proposed_schema.md` for the full table. No fields were added or removed during extraction;
all 9 proposed fields were populated at least partially.

## 4. Normalization performed

- **Dates**: `2023-03-15` values were already ISO 8601 in `batchA_reanalysis.csv`, used as-is.
  `experiment_notes_batchA.md`'s header date ("March 3, 2023") was not attached to a specific
  measurement and was not carried into any record's `measurement_date` (it's a notebook-entry
  date, not confirmed to be the measurement date for the disputed height readings). One date,
  `04/03/2023` in `field_notes_batchB.pdf` (S-05), was **not** normalized — the numeric
  slash format is locale-ambiguous (could be April 3 or March 4) with no corroborating source,
  so it was left `missing` with the raw text preserved.
- **Units**: `final_height_cm` normalized to centimeters throughout:
  - S-05: `4.9 in` → `12.45 cm` (× 2.54).
  - S-06: `11 mm` (from the `final_height_mm`-labeled column) → `1.1 cm` (÷ 10).
  - All other sources already reported centimeters.
- **Categorical values**: `"control (0 mM NaCl)"` normalized to `treatment_mM_NaCl: 0`;
  `"50mM NaCl"` / `"50 mM NaCl"` both normalized to `50`. Canonical unit chosen was mM NaCl since
  4 of 5 sources report treatment this way natively.
- **Numbers**: all treatment concentrations, heights, and germination days stored as numeric
  types (not strings) in `dataset.json`.

## 5. Missing data

| Field | Missing count (of 6) | Notes |
|---|---|---|
| `final_height_cm` | 2 (S-01, S-03) | Not missing from source — unresolved cross-source conflicts (see §6) |
| `germination_days` | 1 (S-03) | Same — conflict, see §6 |
| `measurement_date` | 3 (S-05, S-06, and effectively unset for S-04's original notebook date) | S-05: ambiguous format; S-06: not reported anywhere |
| `measured_by` | 1 (S-06) | Not reported in `master_sample_list.xlsx` |
| `source_batch` | 1 (S-06) | Sample not attributable to either Batch A or Batch B from available sources |
| `notes` | 2 (S-02, S-05) | No qualitative observations recorded for these samples |

## 6. Conflicts

- **S-01, `final_height_cm`**: `experiment_notes_batchA.md` reports 12.4 cm,
  `batchA_reanalysis.csv` reports 12.6 cm, `summary_report_batchA.docx` reports ~12.5 cm. All
  three are plausible measurements of the same plant at different times/instruments; the summary
  report explicitly attributes small discrepancies to equipment recalibration between the
  notebook and reanalysis passes. **Not resolved** — `value` is `null`, all three candidates are
  preserved in the field's `conflict` object.
- **S-03, `final_height_cm`**: notebook (8.2 cm) and summary report (8.2 cm) agree;
  `batchA_reanalysis.csv` reports 8.0 cm. Two-against-one is not sufficient justification to pick
  a winner automatically — the reanalysis may be a genuine, more accurate remeasurement. **Not
  resolved**, both values preserved.
- **S-03, `germination_days`**: notebook (6) and summary report (6) agree; reanalysis CSV reports
  7. Same treatment as above — **not resolved**.

## 7. Low-confidence fields

- `S-01.notes` (0.5) and `S-04.source_batch` / `S-04.notes` (0.6–0.7) — all `status: inferred`,
  derived from contextual mentions rather than a direct labeled statement.
- `measurement_date` and `measured_by` across S-01–S-04 (0.6–0.7) — directly stated in the
  reanalysis CSV, but that CSV only labels the *reanalysis* pass; it's not fully certain the same
  person/date applies to the original notebook readings referenced elsewhere for the same sample.
- `S-05.final_height_cm` (0.75) — normalized via a unit conversion (in → cm) rather than a
  same-unit source value.

## 8. Assumptions

- **Unit of analysis**: one row per sample ID, not per document. Chosen because sample IDs
  (`S-01`, etc.) are the only entity that recurs, in directly comparable form, across multiple
  independent sources.
- **Canonical units**: centimeters for height (majority convention), millimolar NaCl for
  treatment concentration (majority convention, with `0` representing the stated control group).
- **S-06 batch assignment**: left unassigned (`missing`) rather than guessed as "Batch A" (where
  it appears in a shared master list) or "Batch B" (where the sample-numbering sequence would
  otherwise continue) — no source states it directly.
- **S-06 outlier**: retained as a full record per the skill's "never silently exclude an outlier"
  rule, with an explicit flag in `notes` recommending exclusion from summary statistics unless
  independently justified.
