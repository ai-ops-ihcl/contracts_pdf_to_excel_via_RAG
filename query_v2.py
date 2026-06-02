import os
import re
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime
from pathlib import Path
from openai import AzureOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

AZURE_API_KEY      = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT     = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION  = os.getenv("AZURE_OPENAI_API_VERSION")
EMBEDDING_MODEL    = "text-embedding-3-large"
COLLECTION_NAME    = "hotel_contracts"
QDRANT_PATH        = "./qdrant_local"
OUTPUT_DIR         = Path("./query_results")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────
# CORE KEYS — The only attributes we extract
#   Each key becomes a COLUMN in the output Excel
# ─────────────────────────────────────────────────────────────

CORE_KEYS = [
    # Identity
    "Name of Hotel",
    "Hotel Opening Date",
    "No. of Rooms",
    "Site Details",  

    "Termination by Owner",
    "Termination by Operator",
    # Fee-related
    "Management Fee",
    "Incentive Fee",
    "Fee Threshold",
    "Sales & Marketing Fee",
    "Central Group Services Fee",
    "Loyalty Program Fee",
]

# Semantic fallback: discard results below this cosine similarity score
SEMANTIC_SCORE_THRESHOLD = 0.40

# ─────────────────────────────────────────────────────────────
# CLIENTS
# ─────────────────────────────────────────────────────────────

openai_client = AzureOpenAI(
    api_key        = AZURE_API_KEY,
    api_version    = AZURE_API_VERSION,
    azure_endpoint = AZURE_ENDPOINT
)
qdrant_client = QdrantClient(path=QDRANT_PATH)

# ─────────────────────────────────────────────────────────────
# FUNCTION 1 — EMBEDDING (for semantic fallback only)
# ─────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list:
    """Get embedding vector for a text string."""
    response = openai_client.embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding

# ─────────────────────────────────────────────────────────────
# FUNCTION 2 — KEYWORD SEARCH (exact match on Qdrant payload)
# ─────────────────────────────────────────────────────────────

def keyword_search(key_name: str, hotel_name: str = None, limit: int = 100) -> list:
    """
    Exact keyword filter on key_name (and optionally hotel_name).
    Returns list of chunk payloads directly from Qdrant.
    """
    conditions = [
        FieldCondition(key="key_name", match=MatchValue(value=key_name))
    ]
    if hotel_name:
        conditions.append(
            FieldCondition(key="hotel_name", match=MatchValue(value=hotel_name))
        )

    results = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=conditions),
        limit=limit,
        with_payload=True,
        with_vectors=False
    )[0]

    return [point.payload for point in results]

# ─────────────────────────────────────────────────────────────
# FUNCTION 3 — SEMANTIC SEARCH (cosine similarity fallback)
#   Uses query_points() — the new API (qdrant-client >= 1.12)
# ─────────────────────────────────────────────────────────────

def semantic_search(query: str, top_k: int = 5) -> list:
    """
    Embed query and search Qdrant by cosine similarity.
    Returns list of payloads with scores.
    Used ONLY when keyword search returns 0 results.

    NOTE: Uses query_points() (not the deprecated .search() method).
    """
    query_vector = get_embedding(query)

    results = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True
    )

    return [
        {**point.payload, "score": point.score}
        for point in results.points
    ]

# ─────────────────────────────────────────────────────────────
# FUNCTION 4 — RETRIEVE CORE ATTRIBUTES
#   Keyword-first, semantic-fallback per key
# ─────────────────────────────────────────────────────────────

def retrieve_core_attributes(hotel_name: str = None) -> list:
    """
    Retrieve the fixed set of core attributes from Qdrant.

    Strategy for each key in CORE_KEYS:
      Step 1: keyword_search(key_name) -> exact match on payload
              Found? -> use it, skip to next key
      Step 2: semantic_search(key_name) -> catches naming variations
              e.g., "Name of Hotel" ~ "Name of Hotels"
              Filtered by score > 0.40
              If hotel_name specified, further filtered to that hotel

    Deduplicates by (hotel_name, key_name).

    Args:
        hotel_name: If provided, retrieves only for that hotel.
                    If None, retrieves across ALL hotels.

    Returns:
        List of raw chunk payloads (exact data from Qdrant).
    """
    all_chunks = []
    seen = set()  # (hotel_name, key_name) dedup tracker

    for key in CORE_KEYS:
        # ── Step 1: Keyword search (exact match) ──────────────
        results = keyword_search(key_name=key, hotel_name=hotel_name)

        if results:
            for chunk in results:
                dedup_key = (chunk.get("hotel_name", ""), chunk.get("key_name", ""))
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    chunk["retrieval_method"] = "keyword"
                    all_chunks.append(chunk)
            print(f"    [OK] '{key}' -> {len(results)} chunk(s) via keyword search")
            continue  # Found via keyword -> skip semantic

        # ── Step 2: Semantic fallback ─────────────────────────
        fallback_query = f"{key} {hotel_name}" if hotel_name else key
        sem_results = semantic_search(fallback_query, top_k=5)

        # Filter by score threshold
        sem_results = [r for r in sem_results if r.get("score", 0) > SEMANTIC_SCORE_THRESHOLD]

        # If hotel_name specified, further filter to matching hotel
        if hotel_name:
            sem_results = [
                r for r in sem_results
                if hotel_name.lower() in r.get("hotel_name", "").lower()
            ]

        added = 0
        for chunk in sem_results:
            dedup_key = (chunk.get("hotel_name", ""), chunk.get("key_name", ""))
            if dedup_key not in seen:
                seen.add(dedup_key)
                chunk["retrieval_method"] = "semantic"
                all_chunks.append(chunk)
                added += 1

        if added > 0:
            print(f"    [SEMANTIC] '{key}' -> {added} chunk(s) via semantic fallback")
        else:
            print(f"    [MISS] '{key}' -> not found (keyword miss + semantic below threshold)")

    return all_chunks

# ─────────────────────────────────────────────────────────────
# FUNCTION 5 — FUZZY KEY MATCHING
#   Handles naming variations from semantic fallback
# ─────────────────────────────────────────────────────────────

def find_value_for_key(core_key: str, hotel_chunks: list) -> str:
    """
    Find the value for a given CORE_KEY from a hotel's chunks.

    Matching strategy (in order):
      1. Exact match:    chunk key_name == core_key  (case-insensitive)
      2. Fuzzy match:    core_key is contained in chunk key_name
                         OR chunk key_name is contained in core_key
                         (case-insensitive)

    This handles semantic fallback variations like:
      "Sales & Marketing Fee" matching "Sales & Marketing Fee & Central Group Services Fee"
      "Earnest Money Deposit / Key Money" matching "Earnest Money Deposit"

    Args:
        core_key:     The CORE_KEY column name to find.
        hotel_chunks: All retrieved chunks for one hotel.

    Returns:
        The chunk's "value" field, or "N/A" if not found.
    """
    core_lower = core_key.lower().strip()

    # Pass 1: Exact match
    for chunk in hotel_chunks:
        chunk_key = chunk.get("key_name", "").strip()
        chunk_lower = chunk_key.lower()

        if chunk_lower == core_lower:
            return chunk.get("value", "N/A")

    # Pass 2: Fuzzy match (substring — only if exact match not found)
    for chunk in hotel_chunks:
        chunk_key = chunk.get("key_name", "").strip()
        chunk_lower = chunk_key.lower()

        if core_lower in chunk_lower or chunk_lower in core_lower:
            return chunk.get("value", "N/A")

    return "N/A"

# ─────────────────────────────────────────────────────────────
# FUNCTION 6 — EXPORT TO EXCEL (PIVOTED — one row per hotel)
# ─────────────────────────────────────────────────────────────

# ── Style constants ────────────────────────────────────────────
TITLE_FONT     = Font(name="Calibri", bold=True, size=12, color="000000")
TITLE_FILL     = PatternFill(start_color="B8D4E8", end_color="B8D4E8", fill_type="solid")
TITLE_ALIGN    = Alignment(horizontal="left", vertical="center")

HEADER_FONT    = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
HEADER_FILL    = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
HEADER_ALIGN   = Alignment(horizontal="center", vertical="center", wrap_text=True)

CELL_FONT      = Font(name="Calibri", size=10)
CELL_ALIGN     = Alignment(horizontal="left", vertical="top", wrap_text=True)

THIN_BORDER    = Border(
    left=Side(style="thin", color="B0B0B0"),
    right=Side(style="thin", color="B0B0B0"),
    top=Side(style="thin", color="B0B0B0"),
    bottom=Side(style="thin", color="B0B0B0"),
)

ALT_ROW_FILL   = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")
WHITE_FILL     = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")


def export_to_excel(chunks: list) -> Path:
    """
    Export chunk data to a PIVOTED Excel file.
    Layout: ONE ROW per hotel, each CORE_KEY is its own COLUMN.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Core Attributes"

    # ── Define column headers ─────────────────────────────────
    headers = ["#", "File Name", "Agreement Type"] + CORE_KEYS

    # ── Row 1: Title bar (full width, light blue background) ──
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(
        row=1, column=1,
        value=f"Hotel Contracts Report — {datetime.now().strftime('%d %b %Y %H:%M')}"
    )
    title_cell.font = TITLE_FONT
    title_cell.fill = TITLE_FILL
    title_cell.alignment = TITLE_ALIGN
    # Apply title fill across all merged cells
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).fill = TITLE_FILL
    ws.row_dimensions[1].height = 28

    # ── Row 2: Headers (dark blue, white text) ────────────────
    header_row = 2
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER
    ws.row_dimensions[header_row].height = 20

    # ── Group chunks by hotel_name ────────────────────────────
    hotel_groups = {}
    for chunk in chunks:
        hotel = chunk.get("hotel_name", "Unknown")
        if hotel not in hotel_groups:
            hotel_groups[hotel] = []
        hotel_groups[hotel].append(chunk)

    # ── Write one row per hotel ───────────────────────────────
    row_idx = header_row + 1
    serial = 1

    for hotel_name in sorted(hotel_groups.keys()):
        hotel_chunks = hotel_groups[hotel_name]

        # Get metadata from any chunk in this hotel's group
        agreement_type = hotel_chunks[0].get("agreement_type", "N/A") or "N/A"

        # Determine row fill (alternating)
        row_fill = ALT_ROW_FILL if serial % 2 == 0 else WHITE_FILL

        # Column 1: Serial #
        ws.cell(row=row_idx, column=1, value=serial)
        # Column 2: File Name
        file_name = hotel_chunks[0].get("file_name", "N/A") or "N/A"
        ws.cell(row=row_idx, column=2, value=str(file_name))
        # Column 3: Agreement Type
        ws.cell(row=row_idx, column=3, value=str(agreement_type))

        # Columns 4+: One column per CORE_KEY
        for key_idx, core_key in enumerate(CORE_KEYS):
            col = 4 + key_idx
            value = find_value_for_key(core_key, hotel_chunks)
            ws.cell(row=row_idx, column=col, value=str(value))

        # Apply styles to entire row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = CELL_FONT
            cell.alignment = CELL_ALIGN
            cell.border = THIN_BORDER
            cell.fill = row_fill

        # Center-align the # column
        ws.cell(row=row_idx, column=1).alignment = Alignment(
            horizontal="center", vertical="top"
        )

        row_idx += 1
        serial += 1

    total_data_rows = row_idx - header_row - 1

    # ── Column widths (fixed, clean) ──────────────────────────
    col_widths = {
        1: 5,     # #
        2: 45,    # File Name
        3: 25,    # Agreement Type
    }
    # CORE_KEY columns: auto-calculate but cap at 40
    for i in range(len(CORE_KEYS)):
        col_num = 4 + i
        header_len = len(CORE_KEYS[i])
        col_widths[col_num] = min(max(header_len + 4, 20), 40)

    for col_num, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_num)].width = width

    # ── Freeze header row ─────────────────────────────────────
    ws.freeze_panes = f"A{header_row + 1}"

    # ── Auto-filter ───────────────────────────────────────────
    if total_data_rows > 0:
        ws.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(len(headers))}{header_row + total_data_rows}"
        )

    # ── Save ──────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"core_attributes_{ts}.xlsx"
    wb.save(str(out_path))
    return out_path

# ─────────────────────────────────────────────────────────────
# FUNCTION 7 — RUN (Orchestrator)
# ─────────────────────────────────────────────────────────────

def run(hotel_name: str = None):
    """
    Main entry point. Retrieves core attributes and exports to Excel.

    Args:
        hotel_name: If provided, extract for that hotel only.
                    If None, extract across ALL hotels in Qdrant.
    """
    print()
    print("=" * 60)
    print("  IHCL Hotel Contracts — Core Attribute Extraction")
    print("=" * 60)

    target = hotel_name if hotel_name else "ALL HOTELS"
    print(f"\n  Target:     {target}")
    print(f"  Core Keys:  {len(CORE_KEYS)}")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  Strategy:   Keyword search -> Semantic fallback (threshold={SEMANTIC_SCORE_THRESHOLD})")
    print()

    # ── Step 1: Retrieve ──────────────────────────────────────
    print("[Step 1] Retrieving core attributes...")
    chunks = retrieve_core_attributes(hotel_name=hotel_name)

    # ── Stats ─────────────────────────────────────────────────
    hotels_found = sorted(set(c.get("hotel_name", "Unknown") for c in chunks))
    keys_found = sorted(set(c.get("key_name", "Unknown") for c in chunks))
    keyword_count = sum(1 for c in chunks if c.get("retrieval_method") == "keyword")
    semantic_count = sum(1 for c in chunks if c.get("retrieval_method") == "semantic")

    print(f"\n  Total chunks retrieved: {len(chunks)}")
    print(f"  Hotels found:           {len(hotels_found)}")
    print(f"  Keys found:             {len(keys_found)} / {len(CORE_KEYS)}")
    print(f"  Via keyword search:     {keyword_count}")
    print(f"  Via semantic fallback:  {semantic_count}")

    if hotels_found:
        print(f"\n  Hotels:")
        for h in hotels_found:
            hotel_chunks = [c for c in chunks if c.get("hotel_name") == h]
            print(f"    - {h} ({len(hotel_chunks)} attributes)")

    if not chunks:
        print("\n  WARNING: No data found. Check Qdrant collection or key names.")
        return None

    # ── Step 2: Export (pivoted) ──────────────────────────────
    print(f"\n[Step 2] Exporting to Excel (pivoted: one row per hotel)...")
    excel_path = export_to_excel(chunks)
    print(f"  Saved: {excel_path}")

    print(f"\n{'=' * 60}")
    print(f"  DONE — {len(hotels_found)} hotel(s), {len(CORE_KEYS)} columns each")
    print(f"{'=' * 60}")

    return excel_path

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        # Extract core attributes for ALL hotels
        run()

        # Or extract for a specific hotel:
        # run(hotel_name="Taj Exotica Resort and Spa, The Palm, Dubai")

    finally:
        qdrant_client.close()
