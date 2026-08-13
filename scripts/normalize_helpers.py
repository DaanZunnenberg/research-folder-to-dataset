#!/usr/bin/env python3
"""
Small, dependency-free normalization helpers the agent can call from bash for
repetitive, mechanical conversions -- so dates/numbers aren't hand-normalized by eye.
These are intentionally conservative: if a value doesn't cleanly match a known pattern,
they return None rather than guessing, so the agent can fall back to explicit reasoning
or mark the field as ambiguous.

Usage examples:
    python3 normalize_helpers.py date "March 3, 2023"        -> 2023-03-03
    python3 normalize_helpers.py date "03/04/2023"           -> ambiguous (prints candidates)
    python3 normalize_helpers.py number "1,234.5 mg"         -> 1234.5
"""
import sys
import re
import json
import calendar

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def try_iso_date(raw):
    """Best-effort conversion of common date strings to ISO 8601 (YYYY-MM-DD).
    Returns a dict: {"iso": str|None, "ambiguous": bool, "candidates": [str], "note": str}
    """
    s = raw.strip()

    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', s)
    if m:
        return {"iso": s, "ambiguous": False, "candidates": [], "note": "already ISO 8601"}

    m = re.match(r'^([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})$', s)
    if m and m.group(1).lower() in MONTHS:
        mo, d, y = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
        return {"iso": f"{y:04d}-{mo:02d}-{d:02d}", "ambiguous": False, "candidates": [],
                "note": "parsed 'Month D, YYYY'"}

    m = re.match(r'^(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})$', s)
    if m and m.group(2).lower() in MONTHS:
        d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
        return {"iso": f"{y:04d}-{mo:02d}-{d:02d}", "ambiguous": False, "candidates": [],
                "note": "parsed 'D Month YYYY'"}

    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        candidates = []
        if a <= 12:
            candidates.append(f"{y:04d}-{a:02d}-{b:02d}")  # MM/DD/YYYY
        if b <= 12 and a != b:
            candidates.append(f"{y:04d}-{b:02d}-{a:02d}")  # DD/MM/YYYY
        if a > 12 and b <= 12:
            return {"iso": f"{y:04d}-{b:02d}-{a:02d}", "ambiguous": False, "candidates": [],
                    "note": "day > 12 disambiguates as DD/MM/YYYY"}
        if b > 12 and a <= 12:
            return {"iso": f"{y:04d}-{a:02d}-{b:02d}", "ambiguous": False, "candidates": [],
                    "note": "day > 12 disambiguates as MM/DD/YYYY"}
        deduped = list(dict.fromkeys(candidates))
        if len(deduped) == 1:
            # e.g. 05/05/2023: MM/DD and DD/MM interpretations coincide, so it isn't
            # actually ambiguous even though both branches above fired.
            return {"iso": deduped[0], "ambiguous": False, "candidates": [],
                    "note": "day == month, so MM/DD and DD/MM interpretations agree"}
        return {"iso": None, "ambiguous": True, "candidates": deduped,
                "note": "numeric slash date is locale-ambiguous; do not guess, ask/flag"}

    m = re.match(r'^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})$', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return {"iso": f"{y:04d}-{mo:02d}-{d:02d}", "ambiguous": False, "candidates": [],
                "note": "parsed 'YYYY/MM/DD'"}

    return {"iso": None, "ambiguous": True, "candidates": [], "note": "unrecognized date format"}


def try_number(raw):
    """Extract a bare numeric value from a string like '1,234.5 mg' -> 1234.5.
    Returns dict: {"number": float|None, "unit_suffix": str|None}
    """
    s = raw.strip()
    m = re.match(r'^[\$]?(-?[\d,]*\.?\d+)\s*([a-zA-Z%°/µμ]*)$', s)
    if not m:
        return {"number": None, "unit_suffix": None}
    num_str = m.group(1).replace(',', '')
    try:
        num = float(num_str)
        if num.is_integer():
            num = int(num)
        return {"number": num, "unit_suffix": m.group(2) or None}
    except ValueError:
        return {"number": None, "unit_suffix": None}


def main():
    if len(sys.argv) < 3:
        print("Usage: normalize_helpers.py <date|number> <raw value>", file=sys.stderr)
        sys.exit(2)
    kind, raw = sys.argv[1], ' '.join(sys.argv[2:])
    if kind == 'date':
        print(json.dumps(try_iso_date(raw), indent=2))
    elif kind == 'number':
        print(json.dumps(try_number(raw), indent=2))
    else:
        print(f"Unknown kind: {kind}", file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
