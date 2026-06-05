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
# CORE KEYS — Canonical output columns in the Excel
# ─────────────────────────────────────────────────────────────

CORE_KEYS = [
    # ── General / Identity ────────────────────────────────────
    "Name of Hotel",
    "Hotel Opening Date",
    "No. of Rooms",
    "Site Details",                                        # composite: appends "Additional Construction, if any"
    "Region",
    "Owner / Lessor / Licensor Details and Address",       # alias
    "Operator / Lessee / Licensee Details and Address",    # alias
    "Nature of Right of Owner / Lessor / Licensor",        # alias
    "Nature of Right of Operator / Lessee / Licensee",     # alias
    "Mortgage Limit",

    # ── Term ──────────────────────────────────────────────────
    "Original Execution Date",
    "Original Term",
    "Valid From",
    "Valid Up To",
    "Lock-in Period",                                      # alias: "Lock-in Period, if any"

    # ── Renewal ───────────────────────────────────────────────
    "Renewal Term",
    "Conditions of Renewal",
    "Renewal Notice Period",

    # ── Supplemental / Renewal Agreement ──────────────────────
    "Supplemental / Renewal Agreement Summary",            # composite: multi-field summary

    # ── Operations ────────────────────────────────────────────
    "Operations Summary",                                  # composite: "Key Personnel" + "Appointment"

    # ── Annual Plan and Budget ────────────────────────────────
    "Approval of Owner",
    "Operating Budget",
    "Reserve Fund Work Budget",
    "Capital Expenditure",
    "FF&FE Contribution",
    "Notional FF&FE",
    "Working Capital Clause",

    # ── Compensation (Management Agreement) ───────────────────
    "Management Fee",
    "Incentive Fee",
    "Sales & Marketing Fee & Central Group Services Fee",
    "Loyalty Program Fee",
    "Reimbursables",
    "Earnest Money Deposit / Key Money",
    "Owner's Priority",

    # ── Consideration (Lease / License Agreement) ─────────────
    "Applicable Fee / Rent Fee / Consideration Payable",
    "Minimum Guarantee",                                   # alias: "Minimum Guarantee Fee"
    "Due Date of Payment",                                 # alias: "Due date of Payment"
    "Interest on Delayed Payment",                         # alias: fused License artifact
    "Reconciliation Schedule",                             # alias: fused License artifact
    "Non-Refundable Deposit",                              # alias: "Non Refundable Deposit"
    "Refundable Deposit",
    "Premium Paid",                                        # alias: "Premium paid"

    # ── Performance Test ──────────────────────────────────────
    "Performance Testing Terms",
    "Cure Period",

    # ── Termination ───────────────────────────────────────────
    "Termination at Will",
    "Termination by Owner / Lessor / Licensor",            # alias
    "Termination by Operator / Lessee / Licensee",         # alias
    "Consequences of Termination",
    "Liquidated Damages",

    # ── Miscellaneous ─────────────────────────────────────────
    "Non-compete Clause",
    "Sale Transfer Clause",
    "Premature Termination Compensation",
    "Governing Law and Jurisdiction",                      # alias: "Jurisdiction"
    "Arbitration",
    "Area of Protection",
]


# ─────────────────────────────────────────────────────────────
# ALIAS MAP — Raw template variants for each canonical key
#   Resolution order: canonical key first, then aliases in order
#   Each alias is tried with exact match, then fuzzy match
# ─────────────────────────────────────────────────────────────

ALIAS_MAP = {
    # ── General / Identity ────────────────────────────────────
    "Owner / Lessor / Licensor Details and Address": [
        "Owner Details and Address",
        "Lessor Details and address",
        "Licensor Details and address",
    ],
    "Operator / Lessee / Licensee Details and Address": [
        "Operator Details and Address",
        "Lessee Details and address",
        "Licensee Details and address",
    ],
    "Nature of Right of Owner / Lessor / Licensor": [
        "Nature of Right of Owner",
        "Nature of Right of Lessor",
        "Nature of Right of Licensor",
    ],
    "Nature of Right of Operator / Lessee / Licensee": [
        "Nature of Right of Operator",
        "Nature of Right of Lessee",
        "Nature of Right of Licensee",
    ],

    # ── Term ──────────────────────────────────────────────────
    "Lock-in Period": [
        "Lock-in Period, if any",
    ],

    # ── Consideration (Lease / License) ───────────────────────
    "Minimum Guarantee": [
        "Minimum Guarantee Fee",
    ],
    "Due Date of Payment": [
        "Due date of Payment",
    ],
    "Interest on Delayed Payment": [
        "Interest on delayed Payment",
        "Interest on delayed Payment Reconciliation Schedule",
    ],
    "Reconciliation Schedule": [
        "Interest on delayed Payment Reconciliation Schedule",
    ],
    "Non-Refundable Deposit": [
        "Non Refundable Deposit",
    ],
    "Premium Paid": [
        "Premium paid",
    ],

    # ── Termination ───────────────────────────────────────────
    "Termination by Owner / Lessor / Licensor": [
        "Termination by Owner",
        "Termination By Lessor",
        "Termination By Licensor",
    ],
    "Termination by Operator / Lessee / Licensee": [
        "Termination by Operator",
        "Termination By Lessee",
        "Termination By Licensee",
    ],

    # ── Miscellaneous ─────────────────────────────────────────
    "Governing Law and Jurisdiction": [
        "Jurisdiction",
    ],
}


# ─────────────────────────────────────────────────────────────
# COMPOSITE KEYS — Output columns built from multiple source keys
#   "append"      → primary value + secondary appended
#   "multi_field" → multiple source keys formatted as multi-line text
# ─────────────────────────────────────────────────────────────

COMPOSITE_KEYS = {
    "Site Details": {
        "type": "append",
        "primary": "Site Details",
        "secondary": "Additional Construction, if any",
        "fallback_secondary": "NOT Found",
    },
    "Supplemental / Renewal Agreement Summary": {
        "type": "multi_field",
        "section_filter": [
            "Supplemental / Renewal Agreement",
            "First Supplemental Agreement",
            "Second Supplemental Agreement",
            "Third Supplemental Agreement",
        ],
        "source_keys": [
            ("Execution Date",                                   "Execution Date"),
            ("Valid from",                                       "Valid From"),
            ("Valid up to",                                      "Valid Up To"),
            ("Any other amendments in the Supplemental Agreement", "Amendments"),
            ("Original Documents Location (place)",              "Original Documents Location"),
        ],
    },
    "Operations Summary": {
        "type": "multi_field",
        "section_filter": [
            "Operations",
        ],
        "source_keys": [
            ("Key Personnel",              "Key Personnel"),
            ("Key Personnel / Appointment", "Key Personnel / Appointment"),
        ],
    },
    "Sales & Marketing Fee & Central Group Services Fee": {
        "type": "multi_field",
        "skip_missing": True,
        "section_filter": ["Compensation"],
        "source_keys": [
            ("Sales & Marketing Fee",          "Sales & Marketing Fee"),
            ("Sales and Marketing Fee",        "Sales & Marketing Fee"),
            ("Central Group Services Fee",     "Central Group Services Fee"),
            ("Central Group Services Charge",  "Central Group Services Fee"),
        ],
    },
}


# Semantic fallback threshold (kept for potential future use)

# SEMANTIC_SCORE_THRESHOLD = 0.40 # semantic is currently disabled.
MIN_FUZZY_RECALL = 0.40   # At least 40% of canonical key's words must appear in raw key

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
# FUNCTION 1 — SCROLL ALL (paginated, safe for large collections)
# ─────────────────────────────────────────────────────────────

def scroll_all(scroll_filter=None, payload_fields=None) -> list:
    """
    Paginated scroll through Qdrant collection.
    Handles any collection size — keeps scrolling until
    next_offset is None.
    """
    all_points = []
    offset = None

    while True:
        points, next_offset = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=500,
            offset=offset,
            with_payload=payload_fields if payload_fields else True,
            with_vectors=False
        )
        all_points.extend(points)

        if next_offset is None:
            break
        offset = next_offset

    return all_points


# ─────────────────────────────────────────────────────────────
# FUNCTION 2 — GET ALL HOTEL NAMES (paginated)
# ─────────────────────────────────────────────────────────────

def get_all_hotels() -> list:
    """
    Get sorted list of all unique hotel names in the collection.
    Uses paginated scroll — safe for any collection size.
    """
    all_points = scroll_all(payload_fields=["hotel_name"])

    hotels = sorted(set(
        p.payload.get("hotel_name", "")
        for p in all_points
        if p.payload.get("hotel_name")
    ))
    return hotels

def get_all_files() -> list:
    """Get sorted list of all unique file names in the collection."""
    all_points = scroll_all(payload_fields=["file_name"])
    return sorted(set(
        p.payload.get("file_name", "")
        for p in all_points
        if p.payload.get("file_name")
    ))

# ─────────────────────────────────────────────────────────────
# FUNCTION 3 — FETCH ALL CHUNKS FOR ONE HOTEL
# ─────────────────────────────────────────────────────────────

def fetch_hotel_chunks(hotel_name: str) -> list:
    """
    Fetch ALL chunks for a single hotel in ONE paginated scroll.
    Returns list of payload dicts (not Qdrant point objects).
    """
    hotel_filter = Filter(must=[
        FieldCondition(key="hotel_name", match=MatchValue(value=hotel_name))
    ])

    points = scroll_all(scroll_filter=hotel_filter)
    return [point.payload for point in points]

def fetch_file_chunks(file_name: str) -> list:
    """Fetch ALL chunks for a single file in ONE paginated scroll."""
    file_filter = Filter(must=[
        FieldCondition(key="file_name", match=MatchValue(value=file_name))
    ])
    points = scroll_all(scroll_filter=file_filter)
    return [point.payload for point in points]

# ─────────────────────────────────────────────────────────────
# FUNCTION 4 — LOCAL MATCHING (exact + fuzzy, no API calls)
# ─────────────────────────────────────────────────────────────

def normalize_key(text: str) -> str:
    """
    Normalize key text for comparison.
    Handles <br> artifacts, extra whitespace, casing.
    """
    text = text.lower().strip()
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def find_exact_match(core_key: str, hotel_chunks: list) -> dict | None:
    """
    Exact match: normalized core_key == normalized chunk key_name.
    Cost: zero (in-memory).
    """
    target = normalize_key(core_key)

    for chunk in hotel_chunks:
        if normalize_key(chunk.get("key_name", "")) == target:
            return chunk

    return None

def has_negation_conflict(a: str, b: str) -> bool:
    """
    Prevent fuzzy matches between semantically opposite keys like:
      - Refundable Deposit vs Non-Refundable Deposit
    """
    a = normalize_key(a).replace("-", " ")
    b = normalize_key(b).replace("-", " ")

    a_words = set(a.split())
    b_words = set(b.split())

    # If one key has 'non' and the other doesn't, treat as conflict
    return ("non" in a_words) != ("non" in b_words)


def find_fuzzy_match(core_key: str, hotel_chunks: list) -> dict | None:
    """
    Safer fuzzy substring match:
      - allows close key variants
      - blocks semantically opposite matches such as
        'Non-Refundable Deposit' -> 'Refundable Deposit'
    """
    target = normalize_key(core_key)
    target_words = set(target.replace("-", " ").split())

    best_match = None
    best_overlap = 0

    for chunk in hotel_chunks:
        chunk_key = normalize_key(chunk.get("key_name", ""))

        # Skip semantic conflicts like refundable vs non-refundable
        if has_negation_conflict(target, chunk_key):
            continue

        if target in chunk_key or chunk_key in target:
            chunk_words = set(chunk_key.replace("-", " ").split())
            overlap = len(target_words & chunk_words)
            # ── 40% recall guard ─────────────────────
            recall = overlap / max(len(target_words), 1)
            if recall < MIN_FUZZY_RECALL:
                continue
            # ──────────────────────────────────────────────
            total = max(len(target_words), len(chunk_words), 1)
            score = overlap / total

            if score > best_overlap:
                best_overlap = score
                best_match = chunk

    return best_match


def find_containment_merge(core_key: str, hotel_chunks: list) -> dict | None:
    """
    100% Containment Merge — finds all raw keys where EVERY word of
    the canonical key appears in the raw key.
    
    If 1 match  → return it directly.
    If 2+ matches → merge all values into one combined chunk.
    
    Self-guarding: a raw key with fewer words than canonical can
    never pass containment (subset check fails automatically).
    """
    target = normalize_key(core_key)
    target_words = set(target.replace("-", " ").split())

    matched = []
    for chunk in hotel_chunks:
        chunk_key = normalize_key(chunk.get("key_name", ""))
        if chunk_key == target:
            continue  # exact matches handled earlier

        chunk_words = set(chunk_key.replace("-", " ").split())
        if target_words.issubset(chunk_words):
            matched.append(chunk)

    if not matched:
        return None

    if len(matched) == 1:
        return matched[0]

    # Merge all child values
    lines = [
        f"{m.get('key_name', '').strip()}: {sanitize_value(m.get('value', '').strip())}"
        for m in matched
    ]
    result = dict(matched[0])
    result["value"] = "\n".join(lines)
    result["key_name"] = core_key
    return result

# ─────────────────────────────────────────────────────────────
# FUNCTION 5 — SEMANTIC SEARCH (kept for future use, not in main flow)
# ─────────────────────────────────────────────────────────────

# def get_embedding(text: str) -> list:
#     """Get embedding vector for a text string."""
#     response = openai_client.embeddings.create(
#         input=[text],
#         model=EMBEDDING_MODEL
#     )
#     return response.data[0].embedding


# def semantic_search(query: str, hotel_name: str, top_k: int = 3) -> list:
#     """
#     Embed query and search Qdrant by cosine similarity,
#     filtered to a single hotel's chunks.

#     Currently NOT used in the main retrieval flow.
#     Kept for potential future use.
#     """
#     query_vector = get_embedding(query)

#     query_filter = Filter(must=[
#         FieldCondition(key="hotel_name", match=MatchValue(value=hotel_name))
#     ])

#     results = qdrant_client.query_points(
#         collection_name=COLLECTION_NAME,
#         query=query_vector,
#         query_filter=query_filter,
#         limit=top_k,
#         with_payload=True
#     )

#     return [
#         {**point.payload, "score": point.score}
#         for point in results.points
#     ]


# ─────────────────────────────────────────────────────────────
# FUNCTION 6 — KEY RESOLUTION LAYER
#   resolve_single_key   → exact + fuzzy for one key name
#   resolve_with_aliases → canonical + alias variants
#   resolve_composite    → build from multiple source keys
# ─────────────────────────────────────────────────────────────

def resolve_single_key(key: str, chunks: list) -> tuple:
    """
    Find value for a single key name using exact -> fuzzy.

    Args:
        key:    The key name to search for.
        chunks: List of chunk payloads to search within.

    Returns:
        (chunk_dict, value_string) if found.
        (None, None) if not found.
    """
    match = find_exact_match(key, chunks)
    if not match:
        match = find_fuzzy_match(key, chunks)

    if match:
        val = sanitize_value(match.get("value", "").strip())
        if val:
            return match, val
        return match, "N/A"

    return None, None


def resolve_with_aliases(core_key: str, hotel_chunks: list) -> tuple:
    """
    Try canonical key first, then each alias.
    For each variant: exact match first, then fuzzy.

    Resolution order:
      1. Exact match on canonical key
      2. Exact match on each alias (in order)
      3. Fuzzy match on canonical key
      4. Fuzzy match on each alias (in order)

    Args:
        core_key:     The canonical output key name.
        hotel_chunks: All chunks for this hotel.

    Returns:
        (match_dict, method_string) where method is "exact", "alias", or "fuzzy".
        (None, "miss") if nothing found.
    """
    aliases = ALIAS_MAP.get(core_key, [])

    # Pass 1: Exact match on canonical key
    match = find_exact_match(core_key, hotel_chunks)
    if match:
        return match, "exact"

    # Pass 2: Exact match on each alias
    for alias in aliases:
        match = find_exact_match(alias, hotel_chunks)
        if match:
            return match, "alias"
        
    # Pass 3: 100% Containment Merge  — canonical key is fully contained in one or more raw keys
    match = find_containment_merge(core_key, hotel_chunks)
    if match:
        return match, "containment_merge"

    # Pass 4: Fuzzy match on canonical key
    match = find_fuzzy_match(core_key, hotel_chunks)
    if match:
        return match, "fuzzy"

    # Pass 5: Fuzzy match on each alias
    for alias in aliases:
        match = find_fuzzy_match(alias, hotel_chunks)
        if match:
            return match, "fuzzy"

    return None, "miss"


def resolve_composite(core_key: str, hotel_chunks: list) -> dict | None:
    """
    Build a composite value from multiple source keys.

    Supports two types:
      "append"      — primary value + secondary appended in same cell
      "multi_field" — multiple source keys formatted as multi-line text

    For "multi_field" with a section_filter, only chunks from the
    specified sections are searched (prevents e.g. Term "Valid From"
    from being confused with Supplemental "Valid from").

    Returns:
        A chunk-like dict with the composite "value", or None if MISS.
    """
    config = COMPOSITE_KEYS[core_key]

    # ── Type: append ──────────────────────────────────────────
    if config["type"] == "append":
        primary_key  = config["primary"]
        secondary_key = config["secondary"]
        fallback     = config["fallback_secondary"]

        # Find primary (required)
        primary_match, primary_val = resolve_single_key(primary_key, hotel_chunks)
        if not primary_val:
            return None  # MISS — primary not found

        # Find secondary (optional)
        _, secondary_val = resolve_single_key(secondary_key, hotel_chunks)
        if not secondary_val:
            secondary_val = fallback

        # Build composite value
        if secondary_val and secondary_val != fallback:
            combined = f"{primary_val}\nAdditional Construction, if any: {secondary_val}"
        else:
            combined = primary_val

        result = dict(primary_match)
        result["value"] = combined
        result["key_name"] = core_key
        return result

    # ── Type: multi_field ─────────────────────────────────────
    elif config["type"] == "multi_field":
        source_keys = config["source_keys"]

        # Scope chunks to specific sections if configured
        if "section_filter" in config:
            allowed = [s.lower() for s in config["section_filter"]]
            scoped_chunks = [
                c for c in hotel_chunks
                if c.get("section", "").lower() in allowed
            ]
        else:
            scoped_chunks = hotel_chunks

        lines = []
        found_any = False
        base_chunk = None

        skip_missing = config.get("skip_missing", False)
        seen_labels = set()

        for source_key, label in source_keys:
            # Deduplicate by label — first found wins
            if label in seen_labels:
                continue

            match, val = resolve_single_key(source_key, scoped_chunks)

            if val:
                lines.append(f"{label}: {val}")
                found_any = True
                seen_labels.add(label)
                if base_chunk is None:
                    base_chunk = match
            elif not skip_missing:
                lines.append(f"{label}: NOT Found")
                seen_labels.add(label)

        if not found_any:
            return None  # MISS — none of the source keys found

        result = dict(base_chunk) if base_chunk else {}
        result["value"] = "\n".join(lines)
        result["key_name"] = core_key
        return result

    return None


# ─────────────────────────────────────────────────────────────
# FUNCTION 7 — RETRIEVE CORE ATTRIBUTES (HOTEL-CENTRIC)
#   Processes ONE hotel at a time
#   Resolution: composite -> alias -> exact -> fuzzy -> MISS
# ─────────────────────────────────────────────────────────────

def retrieve_core_attributes(hotel_name: str, hotel_chunks: list) -> list:
    """
    Retrieve the fixed set of core attributes for a SINGLE hotel.

    All matching runs against pre-fetched hotel_chunks (in-memory).
    No API calls are made (semantic search is disabled).

    Resolution order for each CORE_KEY:
      1. If composite key  -> build from multiple source keys
      2. If has aliases    -> try canonical + each alias (exact then fuzzy)
      3. Default           -> exact match then fuzzy match
      4. Else              -> MISS

    Each returned chunk is tagged with:
      - "core_key":          which CORE_KEY column this fills
      - "retrieval_method":  "composite", "exact", "alias", "fuzzy"

    Args:
        hotel_name:   The exact hotel_name as stored in Qdrant payload.
        hotel_chunks: Pre-fetched list of all chunk payloads for this hotel.

    Returns:
        List of chunk payloads for this hotel (one per matched CORE_KEY).
    """
    chunks = []

    for key in CORE_KEYS:

        # ── Step 0: Composite key ─────────────────────────────
        if key in COMPOSITE_KEYS:
            result = resolve_composite(key, hotel_chunks)
            if result:
                result = result.copy()
                result["retrieval_method"] = "composite"
                result["core_key"] = key
                chunks.append(result)
                print(f"    [COMPOSITE] '{key}'")
            else:
                print(f"    [MISS]      '{key}'")
            continue

        # ── Step 1+2: Alias-aware resolution ──────────────────
        #   exact(canonical) -> exact(aliases) -> fuzzy(canonical) -> fuzzy(aliases)
        match, method = resolve_with_aliases(key, hotel_chunks)

        if match:
            match = match.copy()
            match["retrieval_method"] = method
            match["core_key"] = key
            chunks.append(match)

            if method == "alias":
                print(f"    [ALIAS]     '{key}' -> '{match.get('key_name', '?')}'")
            elif method == "fuzzy":
                print(f"    [FUZZY]     '{key}' -> '{match.get('key_name', '?')}'")
            elif method == "containment_merge":
                print(f"    [CONTAIN]   '{key}' -> '{match.get('key_name', '?')}'")
            else:
                print(f"    [EXACT]     '{key}'")
            continue

        # ── Step 3: MISS ──────────────────────────────────────
        print(f"    [MISS]      '{key}'")

    return chunks


# ─────────────────────────────────────────────────────────────
# FUNCTION 8 — FIND VALUE FOR KEY (Excel column mapping)
#   Maps CORE_KEY column name -> chunk value
# ─────────────────────────────────────────────────────────────

def sanitize_value(text: str) -> str:
    """
    Remove AI-generated boilerplate note that sometimes leaks into
    the last row's value (e.g. Area of Protection).

    Case-insensitive, None-safe.
    """
    if text is None:
        return "N/A"

    text = str(text)

    # Remove AI-generated note and everything after it
    text = re.split(
        r'\s*(?:•\s*)?note:\s*this document is ai[- ]generated',
        text,
        maxsplit=1,
        flags=re.IGNORECASE
    )[0]

    text = text.strip()
    return text if text else "N/A"


def find_value_for_key(core_key: str, hotel_chunks: list) -> str:
    """
    Find the value for a given CORE_KEY from a hotel's chunks.

    Matching strategy (in order):
      0. Tagged match:  chunk was tagged with core_key during retrieval
      1. Exact match:   chunk key_name == core_key  (case-insensitive)
      2. Fuzzy match:   core_key is contained in chunk key_name
                        OR chunk key_name is contained in core_key

    Returns:
        The chunk's "value" field, or "N/A" if not found.
    """
    core_lower = core_key.lower().strip()

    # Pass 0: Tagged match
    for chunk in hotel_chunks:
        if chunk.get("core_key", "").lower().strip() == core_lower:
            raw = chunk.get("value", "").strip()
            return raw if raw else "N/A"

    # Pass 1: Exact match
    for chunk in hotel_chunks:
        if normalize_key(chunk.get("key_name", "")) == core_lower:
            raw = chunk.get("value", "").strip()
            return raw if raw else "N/A"

    # Pass 2: Fuzzy match
    for chunk in hotel_chunks:
        chunk_lower = normalize_key(chunk.get("key_name", ""))
        if core_lower in chunk_lower or chunk_lower in core_lower:
            raw = chunk.get("value", "").strip()
            return raw if raw else "N/A"

    return "NOT FOUND"


# ─────────────────────────────────────────────────────────────
# FUNCTION 9 — EXPORT TO EXCEL (PIVOTED — one row per hotel)
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



def parse_audit_from_creation_time(audit_trail: dict) -> dict:
    """
    Parse maker/checker details from the raw creation_time string.
    The embedding pipeline stuffed everything into creation_time
    instead of splitting into individual fields.
    """
    result = {
        "maker_name": "", "maker_email": "", 
        "maker_decision": "", "maker_date": "",
        "checker_name": "", "checker_email": "", 
        "checker_decision": "", "checker_date": "",
    }

    if not audit_trail:
        return result

    # First try the individual fields (in case they're populated)
    if audit_trail.get("maker_name"):
        result["maker_name"]     = audit_trail["maker_name"]
        result["maker_email"]    = audit_trail.get("maker_email", "")
        result["maker_decision"] = audit_trail.get("maker_decision", "")
        result["maker_date"]     = audit_trail.get("maker_date", "")
        result["checker_name"]   = audit_trail.get("checker_name", "")
        result["checker_email"]  = audit_trail.get("checker_email", "")
        result["checker_decision"] = audit_trail.get("checker_decision", "")
        result["checker_date"]   = audit_trail.get("checker_date", "")
        return result

    # Otherwise, parse from creation_time blob
    raw = audit_trail.get("creation_time", "")
    if not raw:
        return result

    # Normalize <br> variants
    text = re.sub(r'<br\s*/?>', '\n', raw)

    # ── Parse Maker block ─────────────────────────────
    maker_match = re.search(
        r'Maker:\s*(.+?)(?:\n|$)', text)
    if maker_match:
        result["maker_name"] = maker_match.group(1).strip()

    # Split at the "-----" separator to get maker vs checker sections
    sections = re.split(r'-{5,}', text)
    
    maker_section = sections[0] if len(sections) > 0 else ""
    checker_section = sections[1] if len(sections) > 1 else ""

    # ── Extract from Maker section ────────────────────
    m = re.search(r'Maker:\s*(.+?)(?:\n|$)', maker_section)
    if m:
        result["maker_name"] = m.group(1).strip()

    m = re.search(r'Email:\s*(.+?)(?:\n|$)', maker_section)
    if m:
        result["maker_email"] = m.group(1).strip()

    m = re.search(r'Decision:\s*(.+?)(?:\n|$)', maker_section)
    if m:
        result["maker_decision"] = m.group(1).strip()

    m = re.search(r'Response Date:\s*(.+?)(?:\n|$)', maker_section)
    if m:
        result["maker_date"] = m.group(1).strip()

    # ── Extract from Checker section ──────────────────
    m = re.search(r'Checker:\s*(.+?)(?:\n|$)', checker_section)
    if m:
        result["checker_name"] = m.group(1).strip()

    m = re.search(r'Email:\s*(.+?)(?:\n|$)', checker_section)
    if m:
        result["checker_email"] = m.group(1).strip()

    m = re.search(r'Decision:\s*(.+?)(?:\n|$)', checker_section)
    if m:
        result["checker_decision"] = m.group(1).strip()

    m = re.search(r'Response Date:\s*(.+?)(?:\n|$)', checker_section)
    if m:
        result["checker_date"] = m.group(1).strip()

    return result



def format_maker_details(audit_trail: dict) -> str:
    """Format maker details as multi-line string for Excel cell."""
    parsed = parse_audit_from_creation_time(audit_trail)
    name     = parsed["maker_name"] or "N/A"
    email    = parsed["maker_email"] or "N/A"
    decision = parsed["maker_decision"] or "N/A"
    date     = parsed["maker_date"] or "N/A"
    if name == "N/A" and email == "N/A":
        return "N/A"
    return f"Name: {name}\nEmail: {email}\nDecision: {decision}\nDate: {date}"




def format_checker_details(audit_trail: dict) -> str:
    """Format checker details as multi-line string for Excel cell."""
    parsed = parse_audit_from_creation_time(audit_trail)
    name     = parsed["checker_name"] or "N/A"
    email    = parsed["checker_email"] or "N/A"
    decision = parsed["checker_decision"] or "N/A"
    date     = parsed["checker_date"] or "N/A"
    if name == "N/A" and email == "N/A":
        return "N/A"
    return f"Name: {name}\nEmail: {email}\nDecision: {decision}\nDate: {date}"



def export_to_excel(chunks: list) -> Path:
    """
    Export chunk data to a PIVOTED Excel file.
    Layout: ONE ROW per hotel, each CORE_KEY is its own COLUMN.
    Last two columns: Maker Details, Checker Details.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Core Attributes"

    # ── Define column headers ─────────────────────────────────
    headers = ["#", "File Name", "Agreement Type"] + CORE_KEYS + ["Maker Details", "Checker Details"]

    # ── Row 1: Title bar (full width, light blue background) ──
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(
        row=1, column=1,
        value=f"Hotel Contracts Report — {datetime.now().strftime('%d %b %Y %H:%M')}"
    )
    title_cell.font = TITLE_FONT
    title_cell.fill = TITLE_FILL
    title_cell.alignment = TITLE_ALIGN
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

    # ── Group chunks by file_name ─────────────────────────────
    file_groups = {}
    for chunk in chunks:
        fname = chunk.get("file_name", "Unknown")
        if fname not in file_groups:
            file_groups[fname] = []
        file_groups[fname].append(chunk)

    # ── Write one row per file ───────────────────────────────
    row_idx = header_row + 1
    serial = 1

    for file_name in sorted(file_groups.keys()):
        file_chunks = file_groups[file_name]

        agreement_type = file_chunks[0].get("agreement_type", "N/A") or "N/A"
        row_fill = ALT_ROW_FILL if serial % 2 == 0 else WHITE_FILL

        # Column 1: Serial #
        ws.cell(row=row_idx, column=1, value=serial)
        # Column 2: File Name
        file_name = file_chunks[0].get("file_name", "N/A") or "N/A"
        if file_name.endswith(".md"):
            file_name = file_name[:-3] + ".pdf"
        ws.cell(row=row_idx, column=2, value=str(file_name))
        # Column 3: Agreement Type
        ws.cell(row=row_idx, column=3, value=str(agreement_type))

        # Columns 4+: One column per CORE_KEY
        for key_idx, core_key in enumerate(CORE_KEYS):
            col = 4 + key_idx
            value = find_value_for_key(core_key, file_chunks)
            ws.cell(row=row_idx, column=col, value=sanitize_value(str(value)))

        # Last two columns: Maker and Checker Details
        audit = file_chunks[0].get("audit_trail", {}) or {}
        maker_col   = 4 + len(CORE_KEYS)
        checker_col = 4 + len(CORE_KEYS) + 1
        ws.cell(row=row_idx, column=maker_col,   value=format_maker_details(audit))
        ws.cell(row=row_idx, column=checker_col,  value=format_checker_details(audit))

        # Apply styles to entire row
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = CELL_FONT
            cell.alignment = CELL_ALIGN
            cell.border = THIN_BORDER
            cell.fill = row_fill

        ws.cell(row=row_idx, column=1).alignment = Alignment(
            horizontal="center", vertical="top"
        )

        row_idx += 1
        serial += 1

    total_data_rows = row_idx - header_row - 1

    # ── Column widths ─────────────────────────────────────────
    col_widths = {
        1: 5,     # Serial
        2: 45,    # File Name
        3: 25,    # Agreement Type
    }
    for i in range(len(CORE_KEYS)):
        col_num = 4 + i
        header_len = len(CORE_KEYS[i])
        col_widths[col_num] = min(max(header_len + 4, 20), 40)
    col_widths[4 + len(CORE_KEYS)]     = 30  # Maker Details
    col_widths[4 + len(CORE_KEYS) + 1] = 30  # Checker Details

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
# FUNCTION 10 — RUN (Orchestrator — hotel-centric)
# ─────────────────────────────────────────────────────────────

def run(file_name: str = None):
    """
    Main entry point.

    Design: FILE-CENTRIC, DETERMINISTIC
      1. Discover all files in Qdrant (paginated)
      2. For EACH file:
         a. Fetch all chunks ONCE (one Qdrant scroll)
         b. Resolve each CORE_KEY
      3. Export pivoted Excel — one row per file
    """
    print()
    print("=" * 60)
    print("  IHCL Hotel Contracts — Core Attribute Extraction")
    print("=" * 60)

    files = [file_name] if file_name else get_all_files()

    print(f"\n  Files:      {len(files)}")
    print(f"  Core Keys:  {len(CORE_KEYS)}")
    print(f"  Aliases:    {len(ALIAS_MAP)} keys with aliases")
    print(f"  Composites: {len(COMPOSITE_KEYS)} composite keys")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  Strategy:   composite -> alias -> exact -> containment -> fuzzy -> MISS")
    print()

    print("[Step 1] Retrieving core attributes (file-centric)...\n")

    all_chunks = []
    total_exact     = 0
    total_alias     = 0
    total_fuzzy     = 0
    total_composite = 0
    total_contain   = 0

    for idx, fname in enumerate(files, 1):
        print(f"  [{idx}/{len(files)}] 📄 {fname}")

        file_chunks = fetch_file_chunks(fname)
        print(f"         ({len(file_chunks)} chunks in collection)")

        if not file_chunks:
            print(f"         ⚠ No chunks — skipping\n")
            continue

        h_name = file_chunks[0].get("hotel_name", "Unknown")
        print(f"         🏨 {h_name}")

        chunks = retrieve_core_attributes(
            hotel_name=h_name,
            hotel_chunks=file_chunks
        )
        all_chunks.extend(chunks)

        exact   = sum(1 for c in chunks if c.get("retrieval_method") == "exact")
        alias   = sum(1 for c in chunks if c.get("retrieval_method") == "alias")
        fuzzy   = sum(1 for c in chunks if c.get("retrieval_method") == "fuzzy")
        comp    = sum(1 for c in chunks if c.get("retrieval_method") == "composite")
        contain = sum(1 for c in chunks if c.get("retrieval_method") == "containment_merge")
        total_exact     += exact
        total_alias     += alias
        total_fuzzy     += fuzzy
        total_composite += comp
        total_contain   += contain

        print(
            f"         -> {len(chunks)}/{len(CORE_KEYS)} keys found "
            f"(exact={exact}, alias={alias}, fuzzy={fuzzy}, composite={comp}, contain={contain})\n"
        )

    files_found = sorted(set(c.get("file_name", "Unknown") for c in all_chunks))

    print(f"  {'─' * 50}")
    print(f"  Total chunks retrieved: {len(all_chunks)}")
    print(f"  Files processed:        {len(files_found)}")
    print(f"  Via exact match:        {total_exact}")
    print(f"  Via alias match:        {total_alias}")
    print(f"  Via fuzzy match:        {total_fuzzy}")
    print(f"  Via composite build:    {total_composite}")
    print(f"  Via containment merge:  {total_contain}")
    print(f"  API calls:              0  (fully deterministic)")

    if not all_chunks:
        print("\n  WARNING: No data found. Check Qdrant collection or key names.")
        return None

    print(f"\n[Step 2] Exporting to Excel (pivoted: one row per file)...")
    excel_path = export_to_excel(all_chunks)
    print(f"  Saved: {excel_path}")

    print(f"\n{'=' * 60}")
    print(f"  DONE — {len(files_found)} file(s), {len(CORE_KEYS)} columns each")
    print(f"{'=' * 60}")

    return excel_path


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:

        run()
        # Or extract for a specific hotel:
        # run(hotel_name="Taj Exotica Resort and Spa, The Palm, Dubai")

    finally:
        qdrant_client.close()