import re
import pymupdf4llm
from pathlib import Path


def classify_line(line: str) -> str:
    stripped = line.strip()

    # ── non-table line ──────────────────────────────────────────
    if not stripped.startswith("|"):
        return "skip"

    # ── split into cells ────────────────────────────────────────
    cells = stripped.split("|")
    # cells[0] always empty (before first |)
    # cells[1] = first column
    # cells[2] = second column
    # cells[3] = third column (value)

    # ── separator |---|---|---| ──────────────────────────────────
    if re.match(r'[\|\-\s]+$', stripped):
        return "continuation"

    # ── YOUR RULE: first + second columns empty = continuation ──
    # |||GOP Performance Test...
    # ||||**Area**<br>**as**<br>...
    col1 = cells[1].strip() if len(cells) > 1 else ""
    col2 = cells[2].strip() if len(cells) > 2 else ""
    if not col1 and not col2:
        return "continuation"

    # ── KEY: row contains **_..._** (bold+italic) anywhere ──────
    # |**1**|**_Renewal Term_**|value|
    # |**_Management_**<br>**_Fee_**|value|
    if re.search(r'\*\*_.+?_\*\*', stripped):
        return "key"

    # ── SECTION TYPE 1: Roman numeral in first cell ─────────────
    # |**III**|**Renewal Details**||
    # |**II**|||
    content_cells = [c.strip() for c in cells if c.strip()]
    first_clean   = re.sub(r'\*+|_+', '', content_cells[0]).strip() if content_cells else ""
    if re.match(r'^[IVXLCDM]+$', first_clean) and first_clean:
        return "section"

    # ── SECTION TYPE 2: single bold header, no value ────────────
    # |**AUDIT TRAIL**||
    if (len(content_cells) == 1
            and re.match(r'^\*\*[^*]+\*\*$', content_cells[0])):
        return "section"

    # ── everything else = continuation ──────────────────────────
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
INPUT_DIR  = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\demo_217")
OUTPUT_DIR = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\demo_markdowns")
OUTPUT_DIR.mkdir(exist_ok=True)

for pdf_path in INPUT_DIR.glob("*.pdf"):
    try:
        md  = pdf_to_chunked_markdown(str(pdf_path))
        out = OUTPUT_DIR / pdf_path.with_suffix(".md").name
        out.write_text(md, encoding="utf-8")
        print(f"✅ {pdf_path.name}")
    except Exception as e:
        print(f"❌ {pdf_path.name} → {e}")