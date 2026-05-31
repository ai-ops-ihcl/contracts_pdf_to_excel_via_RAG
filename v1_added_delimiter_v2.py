import re
import fitz
from pathlib import Path


def get_h_lines(page) -> list[float]:
    """
    Detect actual horizontal lines drawn in the PDF.
    Returns sorted list of y-positions.
    Ignores page breaks — only real drawn lines.
    """
    page_width = page.rect.width
    lines      = set()

    for path in page.get_drawings():
        for item in path["items"]:
            if item[0] == "l":                          # straight line
                p1, p2 = item[1], item[2]
                is_horizontal   = abs(p1.y - p2.y) < 2
                is_wide_enough  = abs(p2.x - p1.x) > page_width * 0.3  # spans 30%+ of page
                if is_horizontal and is_wide_enough:
                    lines.add(round((p1.y + p2.y) / 2))

    return sorted(lines)


def extract_with_fitz(pdf_path: str) -> str:
    doc    = fitz.open(pdf_path)
    result = []

    for page in doc:
        h_lines = get_h_lines(page)   # actual PDF lines only

        tables = page.find_tables()

        # ── no tables on this page ───────────────────────────────
        if not tables.tables:
            text = page.get_text("text").strip()
            for ln in text.splitlines():
                if ln.strip():
                    result.append(ln.strip())
            continue

        # ── tables found ─────────────────────────────────────────
        for table in tables.tables:
            rows = table.extract()

            for row_idx, row in enumerate(rows):
                # build pipe row
                cells = []
                for cell in row:
                    if cell is None:
                        cells.append("")
                    else:
                        text = str(cell).strip()
                        text = re.sub(r'\n+', '<br>', text)
                        cells.append(text)

                result.append("|" + "|".join(cells) + "|")

                # inject |---| only if a real PDF line follows this row
                # check if a horizontal line exists just below this row
                if row_idx < len(rows) - 1:
                    next_row_y = table.bbox[1] + (row_idx + 1) * (
                        (table.bbox[3] - table.bbox[1]) / max(len(rows), 1)
                    )
                    has_real_line = any(
                        abs(line_y - next_row_y) < 15
                        for line_y in h_lines
                    )
                    if has_real_line:
                        result.append("|---|---|---|")   # real line ✅

    doc.close()
    return "\n".join(result)


def classify_line(line: str) -> str:
    stripped = line.strip()

    if not stripped:
        return "skip"

    if not stripped.startswith("|"):
        if re.match(r'^\d+$', stripped):             return "skip"
        if '==>' in stripped and '<==' in stripped:  return "skip"
        if stripped.startswith('#'):                 return "skip"
        if stripped.startswith('**Note:**'):         return "skip"
        return "continuation"

    if re.match(r'[\|\-\s]+$', stripped):
        return "separator"

    cells = stripped.split("|")

    # ── use RAW cell positions ───────────────────────────────────
    col1 = cells[1].strip() if len(cells) > 1 else ""
    col2 = cells[2].strip() if len(cells) > 2 else ""

    # both empty = continuation
    if not col1 and not col2:
        return "continuation"

    content_cells = [c.strip() for c in cells if c.strip()]
    first         = content_cells[0] if content_cells else ""
    first_clean   = re.sub(r'\*+|_+', '', first.split('<br>')[0]).strip()

    # SECTION TYPE 1: Roman numeral
    if re.match(r'^[IVXLCDM]+$', first_clean) and first_clean:
        return "section"

    # SECTION TYPE 2: all-caps header
    if (len(content_cells) <= 2
            and re.sub(r'\s+', '', first).isupper()
            and not first.isdigit()):
        return "section"

    # KEY TYPE 1: first column is a number
    if re.match(r'^\d+$', col1):
        return "key"

    # KEY TYPE 2: col1 empty, col2 is short key name  ← THE FIX
    # handles: ||Assignment|value|
    if not col1 and col2 and len(col2) < 80:
        return "key"

    return "continuation"


def pdf_to_chunked_markdown(pdf_path: str) -> str:
    raw_md = extract_with_fitz(pdf_path)
    lines  = raw_md.splitlines()
    result = []
    in_table = False

    for line in lines:
        c = classify_line(line)

        if c in ("skip", "separator"):
            continue
        elif c == "section":
            in_table = True
            result.append("---SECTION---")
            result.append(line)
        elif c == "key":
            in_table = True
            result.append("---KEY---")
            result.append(line)
        elif c == "continuation":
            if in_table:
                result.append(line.strip())

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