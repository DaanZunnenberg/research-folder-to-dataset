# Proposed Schema — Batch A/B Salinity Growth Trial

**Inferred unit of analysis:** one row per plant sample (e.g. `S-01`), aggregated across all
source documents that mention it.

**Sources considered:** `experiment_notes_batchA.md`, `batchA_reanalysis.csv`,
`summary_report_batchA.docx`, `field_notes_batchB.pdf`, `master_sample_list.xlsx`
(`experiment_notes_batchA copy.md` was excluded as an exact duplicate of
`experiment_notes_batchA.md`; `misc_lunch_order.txt` was excluded as irrelevant to the trial;
`.DS_Store` was ignored as OS metadata).

**Expected records:** 6 (`S-01` through `S-06`).

| Field | Description | Type | Required | Examples |
|---|---|---|---|---|
| `sample_id` | Unique sample identifier used consistently across all source documents | string | required | `S-01`, `S-05` |
| `species` | Organism studied | string | required | `Arabidopsis thaliana` |
| `treatment_mM_NaCl` | Salinity treatment concentration, normalized to millimolar NaCl (0 = control) | number | required | `0`, `50`, `100`, `150`, `200` |
| `final_height_cm` | Final measured plant height, normalized to centimeters | number | required | `12.4`, `15.1` |
| `germination_days` | Days from planting to germination | number | optional | `3`, `4`, `9` |
| `measurement_date` | Date the measurement was recorded, normalized to ISO 8601 | date | optional | `2023-03-15` |
| `measured_by` | Person who took/recorded the measurement | string | optional | `K. Chen`, `M. Diallo` |
| `source_batch` | Which experimental batch the sample belongs to | categorical (`Batch A`, `Batch B`) | required | `Batch A` |
| `notes` | Free-text observations relevant to interpreting the record (e.g. viability concerns) | string | optional | `wilted by day 5, likely non-viable outlier` |

**Note on `treatment_mM_NaCl` and `final_height_cm`:** most sources report these directly, but
units and phrasing vary (e.g. `"50mM NaCl"` vs `"50 mM NaCl"` vs `"control"` for 0 mM; heights in
cm, mm, and inches across sources). Each is normalized to one consistent unit; the as-seen source
value is preserved per-field as `value_raw` in `dataset.json`.
