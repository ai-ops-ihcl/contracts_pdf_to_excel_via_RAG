import os
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

# Load environment variables from .env file
load_dotenv()

# ── Config ────────────────────────────────────────────────────
AZURE_API_KEY     = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT    = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
EMBEDDING_MODEL   = "text-embedding-3-large"
VECTOR_DIM        = 3072
COLLECTION_NAME   = "hotel_contracts"
QDRANT_PATH       = "./qdrant_local"
MD_DIR            = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\demo_markdowns")
BATCH_SIZE        = 50

# Validate required environment variables
if not AZURE_API_KEY or not AZURE_ENDPOINT or not AZURE_API_VERSION:
    raise ValueError(
        "Missing required Azure OpenAI credentials. "
        "Please check your .env file contains: "
        "AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION"
    )

# ── Clients ───────────────────────────────────────────────────
openai_client = AzureOpenAI(
    api_key        = AZURE_API_KEY,
    api_version    = AZURE_API_VERSION,
    azure_endpoint = AZURE_ENDPOINT
)
qdrant_client = QdrantClient(path=QDRANT_PATH)


# ─────────────────────────────────────────────────────────────
# STEP 1 — PARSE
# ─────────────────────────────────────────────────────────────

def is_section_row(line: str) -> bool:
    cells       = [c.strip() for c in line.split("|") if c.strip()]
    if not cells:
        return False
    first_clean = re.sub(r'\*+|_+', '', cells[0].split('<br>')[0]).strip()
    if re.match(r'^[IVXLCDM]+$', first_clean):
        return True
    if (len(cells) <= 2
            and re.sub(r'\s+', '', cells[0]).isupper()
            and not cells[0].isdigit()):
        return True
    return False


def parse_section_name(row: str) -> str:
    cells = [c.strip() for c in row.split("|") if c.strip()]
    for cell in cells:
        clean = re.sub(r'\*+|_+', '', cell.split('<br>')[0]).strip()
        if re.match(r'^[IVXLCDM]+$', clean):
            continue
        return re.sub(r'<br>', ' ', cell).strip()
    return ""


def parse_key_row(row: str) -> tuple[str, str]:
    """
    Extract (key_name, value) from pipe row.
    key_name = first short non-number cell
    value    = first long cell after key_name
    """
    cells    = [c.strip() for c in row.split("|") if c.strip()]
    key_name = ""
    value    = ""

    for cell in cells:
        if re.match(r'^\d+$', cell):        # skip row numbers
            continue
        if len(cell) < 2:                   # skip tiny cells
            continue
        if not key_name and len(cell) < 100:
            key_name = re.sub(r'<br>', ' ', cell).strip()
        elif key_name and not value:
            value = cell
            break

    return key_name, value


def parse_markdown(md_path: Path) -> list[dict]:
    """
    Parse chunked markdown into list of structured dicts.
    Each dict = one KEY chunk with section, key, value.
    """
    lines           = md_path.read_text(encoding="utf-8").splitlines()
    chunks          = []
    current_section = ""
    current_chunk   = None
    hotel_name      = ""
    expect_section  = False
    expect_key      = False

    for line in lines:
        line = line.strip()

        # ── markers ──────────────────────────────────────────
        if line == "---SECTION---":
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = None
            expect_section = True
            continue

        if line == "---KEY---":
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = None
            expect_key = True
            continue

        # ── skip empty or separator lines ────────────────────
        if not line or re.match(r'[\|\-\s]+$', line):
            continue

        # ── pipe rows ─────────────────────────────────────────
        if line.startswith("|"):
            if expect_section:
                current_section = parse_section_name(line)
                expect_section  = False

            elif expect_key:
                key_name, value = parse_key_row(line)
                if key_name:
                    current_chunk = {
                        "section": current_section,
                        "key":     key_name,
                        "value":   value
                    }
                    # capture hotel name for all chunks in this file
                    if key_name.lower() in ("name of hotel", "hotel name"):
                        hotel_name = re.sub(r'<br>', ' ', value).strip()
                expect_key = False

            elif current_chunk:
                # continuation pipe row → append to value
                extra = " ".join(c.strip() for c in line.split("|") if c.strip())
                if extra:
                    current_chunk["value"] += " " + extra

        # ── plain text lines ──────────────────────────────────
        else:
            if current_chunk:
                current_chunk["value"] += " " + line

    # save last chunk
    if current_chunk:
        chunks.append(current_chunk)

    # inject contract-level metadata into every chunk
    contract_id = md_path.stem
    for chunk in chunks:
        chunk["contract_id"] = contract_id
        chunk["hotel_name"]  = hotel_name or contract_id
        chunk["source_file"] = md_path.name

    return chunks


# ─────────────────────────────────────────────────────────────
# STEP 2 — CLEAN
# ─────────────────────────────────────────────────────────────

def clean_for_embedding(text: str) -> str:
    """
    Clean text for embedding:
    - <br>  → space
    - pipes → space
    - **_   → remove
    - normalize whitespace
    """
    text = re.sub(r'<br>', ' ', text)
    text = re.sub(r'\|+', ' ', text)
    text = re.sub(r'\*+|_+', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def build_embed_text(chunk: dict) -> str:
    """
    Format: "Section > Key: Value"
    All cleaned for embedding.
    """
    raw = f"{chunk['section']} > {chunk['key']}: {chunk['value']}"
    return clean_for_embedding(raw)


# ─────────────────────────────────────────────────────────────
# STEP 3 — EMBED
# ─────────────────────────────────────────────────────────────

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Batch embed using Azure OpenAI text-embedding-3-large."""
    response = openai_client.embeddings.create(
        input = texts,
        model = EMBEDDING_MODEL
    )
    return [item.embedding for item in response.data]


# ─────────────────────────────────────────────────────────────
# STEP 4 — STORE
# ─────────────────────────────────────────────────────────────

def init_collection():
    existing = [c.name for c in qdrant_client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        qdrant_client.create_collection(
            collection_name = COLLECTION_NAME,
            vectors_config  = VectorParams(
                size     = VECTOR_DIM,
                distance = Distance.COSINE
            )
        )
        print(f"✅ Collection '{COLLECTION_NAME}' created")
    else:
        print(f"✅ Collection '{COLLECTION_NAME}' already exists")


def store_chunks(chunks: list[dict], embeddings: list[list[float]]):
    """Store chunks in Qdrant with metadata payload."""
    points = []
    for chunk, vector in zip(chunks, embeddings):
        points.append(PointStruct(
            id      = str(uuid.uuid4()),
            vector  = vector,
            payload = {
                # ── identity ──────────────────────────────
                "contract_id": chunk["contract_id"],
                "hotel_name":  chunk["hotel_name"],
                "source_file": chunk["source_file"],
                # ── content ───────────────────────────────
                "section":     chunk["section"],
                "key":         chunk["key"],
                "value":       clean_for_embedding(chunk["value"])
                # value cleaned for display/Excel export
                # original pipes/<br> removed for readability
            }
        ))
    qdrant_client.upsert(
        collection_name = COLLECTION_NAME,
        points          = points
    )


# ─────────────────────────────────────────────────────────────
# STEP 5 — PIPELINE
# ─────────────────────────────────────────────────────────────

def run_pipeline():
    init_collection()

    md_files = list(MD_DIR.glob("*.md"))
    print(f"\nFound {len(md_files)} markdown files\n{'─'*50}")

    total_chunks    = 0
    total_contracts = 0

    for md_path in md_files:
        print(f"\n📄 {md_path.name}")

        # parse
        chunks = parse_markdown(md_path)
        if not chunks:
            print(f"  ⚠  No chunks found — skipping")
            continue

        print(f"  Parsed   : {len(chunks)} chunks")

        # build embed texts
        embed_texts = [build_embed_text(c) for c in chunks]

        # embed in batches
        all_embeddings = []
        for i in range(0, len(embed_texts), BATCH_SIZE):
            batch      = embed_texts[i : i + BATCH_SIZE]
            embeddings = get_embeddings(batch)
            all_embeddings.extend(embeddings)
            time.sleep(0.3)    # respect rate limits

        # store
        store_chunks(chunks, all_embeddings)

        total_chunks    += len(chunks)
        total_contracts += 1
        print(f"  Embedded : {len(chunks)} vectors stored ✅")

    print(f"\n{'─'*50}")
    print(f"✅ Pipeline complete")
    print(f"   Contracts : {total_contracts}")
    print(f"   Chunks    : {total_chunks}")
    print(f"   Collection: {COLLECTION_NAME}")
    print(f"   Storage   : {QDRANT_PATH}")


if __name__ == "__main__":
    try:
        run_pipeline()
    finally:
        qdrant_client.close()   # ← add this