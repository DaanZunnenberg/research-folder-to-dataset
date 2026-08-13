# Dataset: Batch A/B Salinity Growth Trial (example output)

This is the example output of the `research-folder-to-dataset` skill run against
`examples/input/`, a synthetic folder of messy plant-biology research files.

## What this dataset represents

One row per plant sample (`sample_id`, e.g. `S-01`) from a salinity-stress growth trial across
two experimental batches. Values were aggregated from five source documents that independently
describe overlapping subsets of the samples, with some cross-source disagreement left intact
rather than resolved.

## Schema

See `proposed_schema.md` for the field-by-field description, type, and required/optional status.
In short: `sample_id`, `species`, `treatment_mM_NaCl`, `final_height_cm`, `germination_days`,
`measurement_date`, `measured_by`, `source_batch`, `notes`.

## Normalization

- Heights normalized to **centimeters** (converted from inches and millimeters where sources
  used those units).
- Treatment concentrations normalized to **millimolar NaCl** (control mapped to `0`).
- Dates normalized to **ISO 8601** where unambiguous; one ambiguous numeric date
  (`04/03/2023`) was deliberately left `null` rather than guessed — see `extraction_report.md`
  §4.
- Wherever a value was normalized, the original as-seen text is preserved as `value_raw` on that
  field in `dataset.json` (e.g. S-05's height has `"value": 12.45, "value_raw": "4.9 in"`).

## Provenance conventions

Every field in `dataset.json` that has `status: "stated"`, `"normalized"`, or `"inferred"`
carries a `provenance` array with `file`, `location` (page/sheet/section), and a verbatim
`quote` from the source. Fields with `status: "missing"` have no provenance — there is nothing
to cite. `dataset.csv` does not carry provenance; use `dataset.json` for auditing.

## Confidence

Each field has a `confidence` score (0.0–1.0). Below 0.6 generally means the value was inferred
from context or normalized from an ambiguous source, rather than stated directly and cleanly.
See `extraction_report.md` §7 for the specific low-confidence fields in this run.

## Conflicts

Two fields (`S-01.final_height_cm`, `S-03.final_height_cm`, `S-03.germination_days`) have
disagreeing values across sources that were **not** auto-resolved. Their `value` is `null` in
the flattened `dataset.csv`; the full set of candidate values and sources is in each field's
`conflict` object in `dataset.json`. See `extraction_report.md` §6.

## Limitations

- `S-06`'s experimental batch could not be determined from any source and is left `null`.
- `S-06` is a statistical outlier (likely non-viable per the source's own note) and is retained,
  not excluded — filter it out explicitly if computing summary statistics.
- PDF text extraction in this run used the skill's stdlib fallback extractor (no `pypdf`
  dependency required); it handles simple text-based PDFs well but will not extract text from
  scanned/image-only PDFs.
- `dataset.xlsx` is only produced when `openpyxl` is available in the environment; `dataset.csv`
  and `dataset.json` are always produced and are the authoritative outputs.

## Files in this example

- `proposed_schema.md` — schema proposed before full extraction (the checkpoint step)
- `dataset.csv` — flattened dataset
- `dataset.json` — full dataset with provenance, confidence, status, conflicts
- `dataset.xlsx` — not included in this checked-in example (requires `openpyxl`; the skill
  produces it automatically when that dependency is present)
- `extraction_report.md` — audit summary of this run
- `validation_notes.json` — mechanical validation output from `scripts/build_outputs.py`
