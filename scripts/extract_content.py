#!/usr/bin/env python3
"""
Deterministic file inventory + text/content extraction for research-folder-to-dataset.

Design goals:
- Zero required third-party dependencies (uses only the Python standard library).
- Optional acceleration/quality boost if pypdf, python-docx, or openpyxl happen to be
  installed -- but never fails if they are not.
- Never raises on a single bad file: records the failure and moves on (partial-failure
  tolerant), so one corrupt file cannot abort the whole run.

Usage:
    python3 extract_content.py <input_dir> <output_json>

Output JSON shape:
{
  "files": [
    {
      "path": "relative/path.pdf",
      "abs_path": "/abs/path.pdf",
      "size_bytes": 12345,
      "sha256": "...",
      "ext": ".pdf",
      "kind": "pdf",
      "skipped": false,
      "skip_reason": null,
      "text": "...extracted text...",
      "sections": [{"label": "page 1", "text": "..."}],
      "extraction_error": null
    },
    ...
  ],
  "ignored_files": [{"path": "...", "reason": "OS metadata file"}],
  "duplicate_groups": [["a.pdf", "b.pdf"]]
}
"""
import sys
import os
import json
import csv
import hashlib
import io
import re
import zlib
import zipfile
import xml.etree.ElementTree as ET

# --------------------------------------------------------------------------
# Files to ignore outright (never extracted, never counted as records)
# --------------------------------------------------------------------------
IGNORE_NAME_PATTERNS = [
    r'^\.DS_Store$',
    r'^Thumbs\.db$',
    r'^desktop\.ini$',
    r'^\._.*',            # macOS AppleDouble sidecar files
    r'^~\$.*',             # Office lock files
    r'.*\.tmp$',
    r'.*\.temp$',
    r'.*\.swp$',
    r'^\.gitignore$',
    r'^\.gitkeep$',
]
IGNORE_DIR_NAMES = {'.git', '__MACOSX', 'node_modules', '.ipynb_checkpoints', '.venv', '__pycache__'}

TEXT_EXTS = {'.txt', '.md', '.markdown', '.rst', '.log'}
CSV_EXTS = {'.csv', '.tsv'}
DOCX_EXTS = {'.docx'}
XLSX_EXTS = {'.xlsx', '.xlsm'}
PDF_EXTS = {'.pdf'}
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.tiff', '.bmp'}


def is_ignored_name(name):
    for pat in IGNORE_NAME_PATTERNS:
        if re.match(pat, name):
            return True
    return False


def sha256_of_file(path):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def classify_ext(ext):
    ext = ext.lower()
    if ext in TEXT_EXTS:
        return 'text'
    if ext in CSV_EXTS:
        return 'csv'
    if ext in DOCX_EXTS:
        return 'docx'
    if ext in XLSX_EXTS:
        return 'xlsx'
    if ext in PDF_EXTS:
        return 'pdf'
    if ext in IMAGE_EXTS:
        return 'image'
    return 'other'


# --------------------------------------------------------------------------
# Extractors -- each returns (text, sections, error)
# sections is a list of {"label": str, "text": str} for provenance (page/sheet/etc.)
# --------------------------------------------------------------------------

def extract_text_plain(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
        return text, [{"label": "full document", "text": text}], None
    except Exception as e:
        return None, [], f"text read error: {e}"


def extract_csv(path):
    try:
        sections = []
        rows = []
        with open(path, 'r', encoding='utf-8', errors='replace', newline='') as f:
            sniff = f.read(4096)
            f.seek(0)
            delim = '\t' if path.lower().endswith('.tsv') else (
                ';' if sniff.count(';') > sniff.count(',') else ','
            )
            reader = csv.reader(f, delimiter=delim)
            for row in reader:
                rows.append(row)
        preview = rows[:50]
        text = '\n'.join(delim.join(r) for r in preview)
        sections.append({"label": "sheet: (csv)", "text": text})
        return text, sections, None, rows
    except Exception as e:
        return None, [], f"csv read error: {e}", []


def _docx_xml_to_text(xml_bytes):
    try:
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        root = ET.fromstring(xml_bytes)
        paras = []
        for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
            runs = p.findall('.//w:t', ns)
            line = ''.join((r.text or '') for r in runs)
            paras.append(line)
        return '\n'.join(paras)
    except Exception:
        return ''


def extract_docx(path):
    try:
        with zipfile.ZipFile(path) as z:
            body = z.read('word/document.xml')
            text = _docx_xml_to_text(body)
        sections = [{"label": "document body", "text": text}]
        return text, sections, None
    except Exception as e:
        return None, [], f"docx read error: {e}"


def _col_letter_to_index(letter):
    idx = 0
    for ch in letter:
        idx = idx * 26 + (ord(ch.upper()) - ord('A') + 1)
    return idx - 1


def extract_xlsx(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            shared = []
            if 'xl/sharedStrings.xml' in names:
                root = ET.fromstring(z.read('xl/sharedStrings.xml'))
                ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in root.findall('a:si', ns):
                    texts = si.findall('.//a:t', ns)
                    shared.append(''.join((t.text or '') for t in texts))

            # Map sheet name -> worksheet XML part via the workbook's relationship IDs
            # (r:id), NOT by positional order -- <sheet> order in workbook.xml does not
            # reliably match sheetN.xml numbering, especially for reordered/renamed sheets.
            r_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            rel_targets = {}  # rId -> target path relative to xl/
            if 'xl/_rels/workbook.xml.rels' in names:
                rel_root = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
                for rel in rel_root:
                    rel_targets[rel.get('Id')] = rel.get('Target')

            ordered_sheets = []  # [(name, worksheet_path)] in workbook-declared order
            if 'xl/workbook.xml' in names:
                wb_root = ET.fromstring(z.read('xl/workbook.xml'))
                ns_wb = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for i, sheet in enumerate(wb_root.findall('.//a:sheets/a:sheet', ns_wb), start=1):
                    name = sheet.get('name', f'Sheet{i}')
                    rid = sheet.get(f'{{{r_ns}}}id')
                    target = rel_targets.get(rid)
                    if target:
                        path = target if target.startswith('xl/') else f'xl/{target.lstrip("/")}'
                    else:
                        # Malformed/missing relationship -- fall back to positional guess.
                        path = f'xl/worksheets/sheet{i}.xml'
                    if path in names:
                        ordered_sheets.append((name, path))

            if not ordered_sheets:
                # No workbook.xml / rels found at all -- fall back to filename order with
                # generic names rather than failing outright.
                sheet_files = sorted(
                    [n for n in names if re.match(r'xl/worksheets/sheet\d+\.xml$', n)],
                    key=lambda n: int(re.search(r'\d+', n).group())
                )
                ordered_sheets = [(f'Sheet{i}', sf) for i, sf in enumerate(sheet_files, start=1)]

            ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            sections = []
            all_text_parts = []
            sheets_data = {}
            for sheet_name, sf in ordered_sheets:
                root = ET.fromstring(z.read(sf))
                grid = {}
                max_row, max_col = 0, 0
                for c in root.findall('.//a:c', ns):
                    ref = c.get('r', '')
                    m = re.match(r'([A-Z]+)(\d+)', ref)
                    if not m:
                        continue
                    col = _col_letter_to_index(m.group(1))
                    row = int(m.group(2))
                    max_row = max(max_row, row)
                    max_col = max(max_col, col)
                    t = c.get('t')
                    v_el = c.find('a:v', ns)
                    val = v_el.text if v_el is not None else ''
                    if t == 's' and val is not None and val.isdigit():
                        try:
                            val = shared[int(val)]
                        except (IndexError, ValueError):
                            pass
                    grid[(row, col)] = val
                rows_out = []
                for r in range(1, max_row + 1):
                    row_vals = [grid.get((r, c), '') for c in range(0, max_col + 1)]
                    rows_out.append(row_vals)
                sheets_data[sheet_name] = rows_out
                preview = '\n'.join(','.join(str(v) for v in row) for row in rows_out[:50])
                sections.append({"label": f"sheet: {sheet_name}", "text": preview})
                all_text_parts.append(preview)
            text = '\n\n'.join(all_text_parts)
            return text, sections, None, sheets_data
    except Exception as e:
        return None, [], f"xlsx read error: {e}", {}


def _pdf_decompress_streams(raw):
    """Very small best-effort PDF text extractor using only zlib/re (no pypdf)."""
    text_chunks = []
    for m in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', raw, re.DOTALL):
        chunk = m.group(1)
        try:
            chunk = zlib.decompress(chunk)
        except Exception:
            pass  # not flate-encoded or already plain; try as-is
        text_chunks.append(chunk)
    return text_chunks


def _pdf_stream_to_text(stream_bytes):
    """Extract text shown via Tj / TJ operators from a decoded PDF content stream."""
    out = []
    for m in re.finditer(rb'\((?:[^()\\]|\\.)*\)\s*Tj', stream_bytes):
        s = m.group(0)
        inner = s[1:s.rfind(b')')]
        out.append(_pdf_unescape(inner))
    for m in re.finditer(rb'\[(.*?)\]\s*TJ', stream_bytes, re.DOTALL):
        parts = re.findall(rb'\((?:[^()\\]|\\.)*\)', m.group(1))
        for p in parts:
            out.append(_pdf_unescape(p[1:-1]))
    return ' '.join(out)


def _pdf_unescape(b):
    try:
        s = b.decode('latin-1', errors='replace')
        s = s.replace('\\(', '(').replace('\\)', ')').replace('\\\\', '\\')
        return s
    except Exception:
        return ''


def extract_pdf(path):
    """
    Best-effort stdlib PDF text extraction. Uses pypdf if available (more reliable);
    otherwise falls back to a homemade FlateDecode + Tj/TJ scanner. Scanned/image-only
    PDFs will yield little or no text -- this is reported, not silently ignored.
    """
    try:
        import pypdf  # optional
        try:
            reader = pypdf.PdfReader(path)
            sections = []
            parts = []
            for i, page in enumerate(reader.pages, start=1):
                t = page.extract_text() or ''
                sections.append({"label": f"page {i}", "text": t})
                parts.append(t)
            return '\n'.join(parts), sections, None
        except Exception as e:
            return None, [], f"pypdf read error: {e}"
    except ImportError:
        pass

    try:
        with open(path, 'rb') as f:
            raw = f.read()
        streams = _pdf_decompress_streams(raw)
        page_texts = [_pdf_stream_to_text(s) for s in streams]
        page_texts = [t for t in page_texts if t.strip()]
        sections = [{"label": f"page {i+1} (best-effort, no pypdf)", "text": t}
                    for i, t in enumerate(page_texts)]
        text = '\n'.join(page_texts)
        if not text.strip():
            return '', [], "no extractable text found (may be scanned/image-only PDF; OCR not available)"
        return text, sections, None
    except Exception as e:
        return None, [], f"pdf read error: {e}"


def extract_image(path):
    """
    Images are not OCR'd by default (no OCR dependency is bundled). If pytesseract +
    PIL happen to be installed, attempt OCR; otherwise report the file as present but
    unextracted so the agent can decide whether to inspect it visually.
    """
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(path)
        text = pytesseract.image_to_string(img)
        return text, [{"label": "OCR", "text": text}], None
    except ImportError:
        return None, [], "image content not extracted (no OCR library available); consider visual inspection"
    except Exception as e:
        return None, [], f"image OCR error: {e}"


def walk_input_dir(input_dir):
    files = []
    ignored = []
    for root, dirs, filenames in os.walk(input_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIR_NAMES and not d.startswith('.')]
        for name in filenames:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, input_dir)
            if is_ignored_name(name):
                ignored.append({"path": rel, "reason": "OS metadata / temp / lock file"})
                continue
            files.append((rel, full))
    return files, ignored


def process_file(rel, full):
    ext = os.path.splitext(full)[1].lower()
    kind = classify_ext(ext)
    size = os.path.getsize(full)
    digest = sha256_of_file(full)

    record = {
        "path": rel,
        "abs_path": full,
        "size_bytes": size,
        "sha256": digest,
        "ext": ext,
        "kind": kind,
        "skipped": False,
        "skip_reason": None,
        "text": None,
        "sections": [],
        "extraction_error": None,
        "tabular_rows": None,  # for csv/xlsx: {sheet_name: [[row...]]} or list of rows
    }

    try:
        if kind == 'text':
            text, sections, err = extract_text_plain(full)
            record["text"], record["sections"], record["extraction_error"] = text, sections, err
        elif kind == 'csv':
            text, sections, err, rows = extract_csv(full)
            record["text"], record["sections"], record["extraction_error"] = text, sections, err
            record["tabular_rows"] = rows
        elif kind == 'docx':
            text, sections, err = extract_docx(full)
            record["text"], record["sections"], record["extraction_error"] = text, sections, err
        elif kind == 'xlsx':
            text, sections, err, sheets = extract_xlsx(full)
            record["text"], record["sections"], record["extraction_error"] = text, sections, err
            record["tabular_rows"] = sheets
        elif kind == 'pdf':
            text, sections, err = extract_pdf(full)
            record["text"], record["sections"], record["extraction_error"] = text, sections, err
        elif kind == 'image':
            text, sections, err = extract_image(full)
            record["text"], record["sections"], record["extraction_error"] = text, sections, err
        else:
            record["skipped"] = True
            record["skip_reason"] = f"unsupported file type ({ext or 'no extension'})"
    except Exception as e:
        record["extraction_error"] = f"unexpected error: {e}"

    return record


def find_duplicate_groups(records):
    by_hash = {}
    for r in records:
        if not r["sha256"]:
            continue
        by_hash.setdefault(r["sha256"], []).append(r["path"])
    return [paths for paths in by_hash.values() if len(paths) > 1]


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 extract_content.py <input_dir> <output_json>", file=sys.stderr)
        sys.exit(2)
    input_dir, output_json = sys.argv[1], sys.argv[2]
    if not os.path.isdir(input_dir):
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    files, ignored = walk_input_dir(input_dir)
    records = []
    for rel, full in files:
        try:
            records.append(process_file(rel, full))
        except Exception as e:
            records.append({
                "path": rel, "abs_path": full, "size_bytes": None, "sha256": None,
                "ext": os.path.splitext(full)[1].lower(), "kind": "unknown",
                "skipped": True, "skip_reason": f"processing crashed: {e}",
                "text": None, "sections": [], "extraction_error": str(e), "tabular_rows": None,
            })

    duplicate_groups = find_duplicate_groups(records)

    out = {
        "input_dir": os.path.abspath(input_dir),
        "files": records,
        "ignored_files": ignored,
        "duplicate_groups": duplicate_groups,
    }
    os.makedirs(os.path.dirname(os.path.abspath(output_json)) or '.', exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Processed {len(records)} files ({len(ignored)} ignored, "
          f"{sum(1 for r in records if r.get('extraction_error'))} with extraction errors, "
          f"{len(duplicate_groups)} duplicate group(s)).")
    print(f"Wrote inventory to {output_json}")


if __name__ == '__main__':
    main()
