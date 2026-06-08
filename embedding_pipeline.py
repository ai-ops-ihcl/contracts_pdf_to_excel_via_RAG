import os

import shutil
import re
import time
import uuid
from pathlib import Path
from dotenv import load_dotenv
from openai import AzureOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct
)

load_dotenv()

# ── Config ──────────────────────────────────────────────────
AZURE_API_KEY      = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT     = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION  = os.getenv("AZURE_OPENAI_API_VERSION")
EMBEDDING_MODEL    = "text-embedding-3-large"
VECTOR_DIM         = 3072
COLLECTION_NAME    = "hotel_contracts"
QDRANT_PATH        = "./qdrant_local"
MD_DIR             = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\Generated_markdowns")
BATCH_SIZE         = 50

# ── Clients ─────────────────────────────────────────────────
openai_client = AzureOpenAI(
    api_key        = AZURE_API_KEY,
    api_version    = AZURE_API_VERSION,
    azure_endpoint = AZURE_ENDPOINT
)
qdrant_client = QdrantClient(path=QDRANT_PATH)


# ─────────────────────────────────────────────────────────────
# FUNCTION 1 — PARSE FILE NAME
# ─────────────────────────────────────────────────────────────

def parse_file_name(file_name: str) -> dict:
    """
    Extract agreement_type, contract_id, hotel_hint from file name.
    
    Handles:
      "(HMA) 000334 - Taj Exotica Resort and Spa The Palm Dubai (25-Jan-2026_12-04_PM_IST).md"
      "(HMA) Gateway Ahmedabad (07-Mar-2026_08-18_AM_IST).md"
      "(LA) 000412 - Taj Lands End Mumbai (10-Feb-2026_03-15_PM_IST).md"
      "(LLA) Vivanta Goa (15-Apr-2026_09-30_AM_IST).md"
    """
    result = {
        "agreement_type": "Unknown",
        "contract_id": None,
        "hotel_hint": file_name  # worst-case fallback
    }

    # ── Agreement Type ──────────────────────────────────────
    prefix_map = {
        "(HMA)":     "Hotel Management Agreement",
        "(LA)":      "Lease Agreement",
        "(LEASE)":   "Lease Agreement",
        "(LLA)":     "Leave and License Agreement",
        "(LICENSE)": "Leave and License Agreement",
    }
    for prefix, ag_type in prefix_map.items():
        if file_name.upper().startswith(prefix):
            result["agreement_type"] = ag_type
            break

    # ── Contract ID (optional) ──────────────────────────────
    # Look for 3-6 digit number after prefix
    id_match = re.search(r'\)\s*(\d{3,6})\s*-', file_name)
    if id_match:
        result["contract_id"] = id_match.group(1)

    # ── Hotel Hint (fallback if "Name of Hotel" key missing) ─
    # Strip: prefix, contract_id, timestamp, extension
    hint = file_name
    # Remove prefix like "(HMA) "
    hint = re.sub(r'^\([A-Z]+\)\s*', '', hint)
    # Remove contract_id like "000334 - "
    hint = re.sub(r'^\d{3,6}\s*-\s*', '', hint)
    # Remove timestamp like "(25-Jan-2026_12-04_PM_IST)"
    hint = re.sub(r'\(\d{2}-\w{3}-\d{4}_[\d\-_]+[APM_IST]+\)', '', hint)
    # Remove file extension
    hint = re.sub(r'\.(md|pdf)$', '', hint, flags=re.IGNORECASE)
    # Clean up
    hint = hint.strip().strip('-').strip()

    if hint:
        result["hotel_hint"] = hint

    return result


# ─────────────────────────────────────────────────────────────
# FUNCTION 2 — PARSE MARKDOWN (TWO-PASS)
# ─────────────────────────────────────────────────────────────

def parse_section_name(row: str) -> str:
    """Extract section name from pipe row like '||VII||Compensation||'"""
    cells = [c.strip() for c in row.split("|") if c.strip()]
    for cell in cells:
        clean = re.sub(r'\*+|_+', '', cell.split('<br>')[0]).strip()
        # Skip roman numerals — we want the name, not the number
        if re.match(r'^[IVXLCDM]+$', clean):
            continue
        return re.sub(r'<br>', ' ', cell).strip()
    return ""


def parse_key_row(row: str) -> tuple:
    cells = [c.strip() for c in row.split("|") if c.strip()]
    key_name = ""
    value = ""

    for cell in cells:
        if len(cell) < 2:          # skip tiny cells
            continue
        if not key_name:
            if re.match(r'^\d+$', cell):   # skip row numbers ONLY before key is found
                continue
            if len(cell) < 100:
                key_name = re.sub(r'<br>', ' ', cell).strip()
        elif not value:
            value = cell           # ← numeric values like "20" now pass through
            break

    return key_name, value


def parse_page_from_delimiter(line: str) -> int:
    """Extract page number from '---KEY:PAGE=4---' or '---SECTION:PAGE=1---'"""
    match = re.search(r'PAGE=(\d+)', line)
    return int(match.group(1)) if match else 0


def extract_audit_trail(chunks: list) -> dict:
    """
    Pull audit trail info from chunks that belong to AUDIT TRAIL section.
    Returns dict with maker/checker/status info.
    """
    audit = {
        "ai_generated_by": "",
        "creation_time": "",
        "maker_name": "",
        "maker_email": "",
        "maker_decision": "",
        "maker_date": "",
        "checker_name": "",
        "checker_email": "",
        "checker_decision": "",
        "checker_date": "",
        "approval_status": "Unknown"
    }

    for chunk in chunks:
        key_lower = chunk["key"].lower().strip()
        value = chunk["value"].strip()

        if key_lower in ("ai draft generated by",):
            audit["ai_generated_by"] = value

        elif key_lower in ("creation time",):
            audit["creation_time"] = value

        elif key_lower in ("human approval", "approval trail"):
            # Parse the maker/checker block
            # Maker block
            maker_match = re.search(
                r'Maker:\s*(.+?)(?:\n|Email:)',
                value, re.IGNORECASE
            )
            if maker_match:
                audit["maker_name"] = maker_match.group(1).strip()

            maker_email = re.search(
                r'Maker.*?Email:\s*(\S+)',
                value, re.IGNORECASE | re.DOTALL
            )
            if maker_email:
                audit["maker_email"] = maker_email.group(1).strip()

            maker_decision = re.search(
                r'Maker.*?Decision:\s*(\w+)',
                value, re.IGNORECASE | re.DOTALL
            )
            if maker_decision:
                audit["maker_decision"] = maker_decision.group(1).strip()

            maker_date = re.search(
                r'Maker.*?Response Date:\s*(.+?)(?:\n|Decision)',
                value, re.IGNORECASE | re.DOTALL
            )
            if maker_date:
                audit["maker_date"] = maker_date.group(1).strip()

            # Checker block
            checker_match = re.search(
                r'Checker:\s*(.+?)(?:\n|Email:)',
                value, re.IGNORECASE
            )
            if checker_match:
                audit["checker_name"] = checker_match.group(1).strip()

            checker_email = re.search(
                r'Checker.*?Email:\s*(\S+)',
                value, re.IGNORECASE | re.DOTALL
            )
            if checker_email:
                audit["checker_email"] = checker_email.group(1).strip()

            checker_decision = re.search(
                r'Checker.*?Decision:\s*(\w+)',
                value, re.IGNORECASE | re.DOTALL
            )
            if checker_decision:
                audit["checker_decision"] = checker_decision.group(1).strip()

            checker_date = re.search(
                r'Checker.*?Response Date:\s*(.+?)(?:\n|Decision)',
                value, re.IGNORECASE | re.DOTALL
            )
            if checker_date:
                audit["checker_date"] = checker_date.group(1).strip()

    # Derive approval status
    maker_ok = audit["maker_decision"].lower() == "approve"
    checker_ok = audit["checker_decision"].lower() in ("approve", "checked")

    if maker_ok and checker_ok:
        audit["approval_status"] = "Fully Approved"
    elif maker_ok and not audit["checker_decision"]:
        audit["approval_status"] = "Pending Checker"
    elif not audit["maker_decision"]:
        audit["approval_status"] = "Pending"
    else:
        audit["approval_status"] = "Partial"

    return audit


def parse_markdown(md_path: Path, file_info: dict) -> tuple:
    """
    Two-pass parser.
    
    Returns:
        doc_meta    : dict with {agreement_type, hotel_name}
        chunks      : list of {section, key, value, page_no}
        audit_trail : dict with maker/checker/status
    """
    lines = md_path.read_text(encoding="utf-8").splitlines()

    # ─────────────────────────────────────────────────────────
    # SINGLE PASS — Parse all chunks + identify doc metadata
    # ─────────────────────────────────────────────────────────
    all_chunks = []
    current_section = ""
    current_chunk = None
    expect_section = False
    expect_key = False
    current_page = 0

    for line in lines:
        line_stripped = line.strip()

        # ── Delimiters ──────────────────────────────────────
        if line_stripped.startswith("---SECTION:PAGE="):
            if current_chunk:
                all_chunks.append(current_chunk)
                current_chunk = None
            current_page = parse_page_from_delimiter(line_stripped)
            expect_section = True
            continue

        if line_stripped.startswith("---KEY:PAGE="):
            if current_chunk:
                all_chunks.append(current_chunk)
                current_chunk = None
            current_page = parse_page_from_delimiter(line_stripped)
            expect_key = True
            continue

        # ── Skip empty / separator ──────────────────────────
        if not line_stripped or re.match(r'^[\|\-\s]+$', line_stripped):
            continue

        # ── Pipe rows ───────────────────────────────────────
        if line_stripped.startswith("|"):
            if expect_section:
                new_section = parse_section_name(line_stripped)
                if new_section:
                    current_section = new_section
                expect_section = False


            elif expect_key:
                key_name, value = parse_key_row(line_stripped)
                if key_name:
                    current_chunk = {
                        "section": current_section,
                        "key": key_name,
                        "value": value,
                        "page_no": current_page
                    }
                expect_key = False

            elif current_chunk:
                # Continuation row → append to value
                extra = " ".join(
                    c.strip() for c in line_stripped.split("|") if c.strip()
                )
                if extra:
                    current_chunk["value"] += " " + extra

        # ── Plain text continuation ─────────────────────────
        else:
            if current_chunk:
                current_chunk["value"] += " " + line_stripped

    # Save last chunk
    if current_chunk:
        all_chunks.append(current_chunk)

    # ─────────────────────────────────────────────────────────
    # SEPARATE — Audit trail vs contract chunks
    # ─────────────────────────────────────────────────────────
    audit_section_names = {"AUDIT TRAIL", "AUDIT"}
    audit_keys = {
        "ai draft generated by", "creation time",
        "human approval", "approval trail"
    }

    audit_chunks = []
    contract_chunks = []

    for chunk in all_chunks:
        if (chunk["section"].upper().strip() in audit_section_names
                or chunk["key"].lower().strip() in audit_keys):
            audit_chunks.append(chunk)
        else:
            contract_chunks.append(chunk)

    # ── Extract audit trail metadata ────────────────────────
    audit_trail = extract_audit_trail(audit_chunks)

    # ── Extract hotel_name from contract chunks ─────────────
    hotel_name = file_info.get("hotel_hint", "")
    for chunk in contract_chunks:
        if chunk["key"].lower().strip() in ("name of hotel", "hotel name"):
            cleaned = clean_for_embedding(chunk["value"])
            if cleaned and cleaned.upper() != "N/A":
                hotel_name = cleaned
            break

    # ── Build doc_meta ──────────────────────────────────────
    doc_meta = {
        "agreement_type": file_info["agreement_type"],
        "hotel_name": hotel_name,
    }

    return doc_meta, contract_chunks, audit_trail


# ─────────────────────────────────────────────────────────────
# FUNCTION 3 — CLEAN FOR EMBEDDING
# ─────────────────────────────────────────────────────────────

def clean_for_embedding(text: str) -> str:
    """
    Clean raw pipe/markdown text into natural language.
    Used for:
      - chunk value (payload + display)
      - building embed text
    """
    # 1. <br> → space
    text = re.sub(r'<br\s*/?>', ' ', text)
    # 2. Remove pipes
    text = re.sub(r'\|+', ' ', text)
    # 3. Remove bold/italic markers
    text = re.sub(r'\*{1,2}|_{1,2}', '', text)
    # # 4. Remove stray row numbers at start (e.g., "1 Name of Hotel")
    # text = re.sub(r'^\d+\s+', '', text.strip())
    # 5. Remove delimiter remnants
    text = re.sub(r'---+', '', text)
    # 6. Collapse whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


# ─────────────────────────────────────────────────────────────
# FUNCTION 4 — BUILD CHUNK TEXT (WITH METADATA HEADER)
# ─────────────────────────────────────────────────────────────

def build_chunk_text(chunk: dict, doc_meta: dict) -> str:
    """
    Build self-contained chunk with metadata header.
    This is what gets EMBEDDED and sent to LLM.
    """
    header = (
        f"AGREEMENT TYPE: {doc_meta['agreement_type']}\n"
        f"HOTEL: {doc_meta['hotel_name']}\n"
        f"SECTION: {chunk['section']}\n"
        f"KEY: {chunk['key']}\n"
        f"PAGE: {chunk['page_no']}"
    )

    content = clean_for_embedding(chunk["value"])

    return f"{header}\n---\n{content}"


# ─────────────────────────────────────────────────────────────
# FUNCTION 5 — EMBEDDING
# ─────────────────────────────────────────────────────────────

def get_embeddings(texts: list) -> list:
    """Batch embed using Azure OpenAI text-embedding-3-large."""
    response = openai_client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL
    )
    return [item.embedding for item in response.data]


# ─────────────────────────────────────────────────────────────
# FUNCTION 6 — QDRANT STORAGE
# ─────────────────────────────────────────────────────────────

def init_collection():
    """Create Qdrant collection if it doesn't exist."""
    existing = [c.name for c in qdrant_client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_DIM,
                distance=Distance.COSINE
            )
        )
        print(f"✅ Collection '{COLLECTION_NAME}' created")
    else:
        print(f"✅ Collection '{COLLECTION_NAME}' already exists")


def create_payload_indexes():
    """Create payload indexes for fast filtering."""
    indexes = {
        "key_name":        "keyword",
        "hotel_name":      "keyword",
        "agreement_type":  "keyword",
        "section":         "keyword",
        "page_no":         "integer",
        "file_name":       "keyword",   # ← add this
    }
    for field, schema in indexes.items():
        try:
            qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema
            )
            print(f"  📇 Index created: {field} ({schema})")
        except Exception as e:
            print(f"  ⚠ Index {field}: {e}")


def store_chunks(points: list):
    """Upsert points into Qdrant."""
    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )


# ─────────────────────────────────────────────────────────────
# FUNCTION 7 — RUN PIPELINE
# ─────────────────────────────────────────────────────────────


def run_pipeline():

    global qdrant_client

    # Replace the existing delete block with:
    if os.path.exists(QDRANT_PATH):
        qdrant_client.close()
        shutil.rmtree(QDRANT_PATH)
        print(f"🗑️  Deleted Qdrant storage at '{QDRANT_PATH}'")
        # Re-init client after directory nuke
        qdrant_client = QdrantClient(path=QDRANT_PATH)

    init_collection()

    md_files = list(MD_DIR.glob("*.md"))
    print(f"\nFound {len(md_files)} markdown files\n{'─' * 50}")

    total_chunks = 0
    total_contracts = 0

    for md_path in md_files:
        print(f"\n📄 {md_path.name}")

        # ── Step 1: Parse file name ─────────────────────────
        file_info = parse_file_name(md_path.name)
        print(f"  Type     : {file_info['agreement_type']}")
        print(f"  ID       : {file_info['contract_id'] or 'N/A'}")

        # ── Step 2: Parse markdown (two-pass) ────────────────
        doc_meta, chunks, audit_trail = parse_markdown(md_path, file_info)
        print(f"  Hotel    : {doc_meta['hotel_name']}")
        print(f"  Chunks   : {len(chunks)}")
        print(f"  Approval : {audit_trail['approval_status']}")

        if not chunks:
            print(f"  ⚠ No chunks found — skipping")
            continue

        # ── Step 3: Build chunk texts + payloads ─────────────
        chunk_texts = []
        payloads = []

        for chunk in chunks:
            # Build embeddable text (with metadata header)
            chunk_text = build_chunk_text(chunk, doc_meta)
            chunk_texts.append(chunk_text)

            # Build payload
            cleaned_value = clean_for_embedding(chunk["value"])
            payload = {
                # ── In chunk text (embedded) ────────────
                "agreement_type": doc_meta["agreement_type"],
                "hotel_name":     doc_meta["hotel_name"],
                "section":        chunk["section"],
                "key_name":       chunk["key"],
                "page_no":        chunk["page_no"],
                "chunk_text":     chunk_text,

                # ── Payload only (not embedded) ─────────
                "contract_id":    file_info["contract_id"],  # or None
                "file_name":      md_path.name,
                "value":          cleaned_value,
                "audit_trail":    audit_trail,
            }
            payloads.append(payload)

        # ── Step 4: Batch embed ──────────────────────────────
        all_embeddings = []
        for i in range(0, len(chunk_texts), BATCH_SIZE):
            batch = chunk_texts[i : i + BATCH_SIZE]
            embeddings = get_embeddings(batch)
            all_embeddings.extend(embeddings)
            time.sleep(0.3)  # respect rate limits

        # ── Step 5: Build Qdrant points ──────────────────────
        points = []
        for payload, vector in zip(payloads, all_embeddings):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=payload
            ))

        # ── Step 6: Store ────────────────────────────────────
        store_chunks(points)
        total_chunks += len(chunks)
        total_contracts += 1
        print(f"  Stored   : {len(chunks)} vectors ✅")

    # ── Create indexes after all data is loaded ──────────────
    print(f"\n{'─' * 50}")
    print("Creating payload indexes...")
    create_payload_indexes()

    print(f"\n{'─' * 50}")
    print(f"✅ Pipeline complete")
    print(f"  Contracts : {total_contracts}")
    print(f"  Chunks    : {total_chunks}")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  Storage   : {QDRANT_PATH}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run_pipeline()
    finally:
        qdrant_client.close()