import re
import pymupdf4llm
from pathlib import Path


def classify_line(line: str) -> str:
    stripped = line.strip()

    # ── non-table lines ─────────────────────────────────────────
    if not stripped.startswith("|"):
        if not stripped:                                return "skip"
        if re.match(r'^\d+$', stripped):               return "skip"
        if '==>' in stripped and '<==' in stripped:    return "skip"
        if stripped.startswith('#'):                   return "skip"
        if stripped.startswith('**Note:**'):           return "skip"  # ← add this
        return "continuation"

    # ── separator |---|---|---| ──────────────────────────────────
    if re.match(r'[\|\-\s]+$', stripped):
        return "continuation"

    cells = stripped.split("|")
    col1  = cells[1].strip() if len(cells) > 1 else ""
    col2  = cells[2].strip() if len(cells) > 2 else ""

    # ── first + second columns empty = continuation ─────────────
    if not col1 and not col2:
        return "continuation"

    # ── SECTION before KEY ──────────────────────────────────────
    content_cells   = [c.strip() for c in cells if c.strip()]
    first_cell_raw  = cells[1] if len(cells) > 1 else ""
    first_before_br = first_cell_raw.split('<br>')[0]
    first_clean     = re.sub(r'\*+|_+', '', first_before_br).strip()

    if re.match(r'^[IVXLCDM]+$', first_clean) and first_clean:
        return "section"

    pure_bold = [c for c in content_cells
                 if re.match(r'^\*\*[^*_<>]+\*\*$', c)]
    non_bold  = [c for c in content_cells
                 if not re.match(r'^\*\*[^*_<>]+\*\*$', c)]
    if pure_bold and not non_bold:
        return "section"

    # ── KEY ─────────────────────────────────────────────────────
    if re.search(r'\*\*_.+?_\*\*', stripped):
        return "key"

    if (len(content_cells) >= 2
            and re.match(r'^\*\*[^*_<>]+\*\*$', content_cells[0])):
        return "key"

    return "continuation"


def pdf_to_chunked_markdown(pdf_path: str) -> str:
    raw_md = pymupdf4llm.to_markdown(pdf_path)
    lines  = raw_md.splitlines()
    result = []

    for line in lines:
        c = classify_line(line)

        if c == "skip":
            continue

        elif c == "section":
            # marker BEFORE section
            result.append("---SECTION---")
            result.append(line)

        elif c == "key":
            # marker BEFORE key  ← THE FIX
            result.append("---KEY---")
            result.append(line)

        elif c == "continuation":
            # no marker — just attach to whatever is above
            result.append(f"  {line.strip()}")

    return "\n".join(result)


# ── Batch run ─────────────────────────────────────────────────
INPUT_DIR  = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\contract_summary_217")
OUTPUT_DIR = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\pymupdf_markdowns")
OUTPUT_DIR.mkdir(exist_ok=True)

for pdf_path in INPUT_DIR.glob("*.pdf"):
    try:
        md  = pdf_to_chunked_markdown(str(pdf_path))
        out = OUTPUT_DIR / pdf_path.with_suffix(".md").name
        out.write_text(md, encoding="utf-8")
        print(f"✅ {pdf_path.name}")
    except Exception as e:
        print(f"❌ {pdf_path.name} → {e}")