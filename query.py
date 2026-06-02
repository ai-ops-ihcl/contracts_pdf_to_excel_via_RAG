import re
import json
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime
from pathlib import Path
from openai import AzureOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────
AZURE_API_KEY     = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT    = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
EMBEDDING_MODEL   = "text-embedding-3-large"
CHAT_MODEL        = "gpt-4.1"
COLLECTION_NAME   = "hotel_contracts"
QDRANT_PATH       = "./qdrant_local"
OUTPUT_DIR        = Path("./query_results")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Clients ───────────────────────────────────────────────────
openai_client = AzureOpenAI(
    api_key        = AZURE_API_KEY,
    api_version    = AZURE_API_VERSION,
    azure_endpoint = AZURE_ENDPOINT
)
qdrant_client = QdrantClient(path=QDRANT_PATH)


# ─────────────────────────────────────────────────────────────
# FUNCTION 1 — PARSE QUESTION (LLM Call 1)
# ─────────────────────────────────────────────────────────────

PARSE_SYSTEM_PROMPT = """You are a hotel contract query parser.
Given a natural language question, return ONLY a JSON object.

Known contract keys (use exact spelling):
- Name of Hotel, Owner Details and Address, Operator details and Address
- Region, No. of Rooms, Hotel Opening Date, Nature of Right of Owner
- Site Details, Additional Construction, Mortgage Limit
- Original Execution Date, Original Term, Valid from, Valid up to, Lock-in Period
- Renewal Term, Renewal Notice Period, Conditions of Renewal
- Execution Date, Any other amendments in the Supplemental Agreement
- Key Personnel, Key Personnel / Appointment
- Approval of Owner, Operating Budget, Reserve Fund Work Budget
- Capital Expenditure, FF&FE Contribution, Notional FF&FE, Working Capital Clause
- Management Fee, Incentive Fee, Fee Threshold, Sales & Marketing Fee
- Central Group Services Fee, Loyalty Program Fee, Reimbursables
- Earnest Money Deposit / Key Money, Owner's Priority
- Signatory, Cap
- Performance Testing Terms, Cure Period
- Termination at Will, Termination by Owner, Termination by Operator
- Consequences of Termination, Liquidated Damages
- Non-compete Clause, Sale Transfer Clause, Premature Termination Compensation
- Governing Law and Jurisdiction, Arbitration, Owner's Approval
- Area of Protection, Assignment, Owner's Privileges

Return one of these formats:

FORMAT 1 — Structured query (field + condition):
{"type": "structured", "key": "exact key name", "operator": "gt|lt|eq|contains|after|before", "value": "comparison value"}

FORMAT 2 — Fetch all values for a key:
{"type": "fetch_all", "key": "exact key name"}

FORMAT 3 — Fetch specific hotel's key:
{"type": "fetch_hotel", "key": "exact key name", "hotel": "hotel name from question"}

FORMAT 4 — Semantic / analytical query:
{"type": "semantic", "query": "rephrased search query"}

FORMAT 5 — Multi-key query (comparing multiple attributes):
{"type": "multi_key", "keys": ["key1", "key2"], "hotel": "optional hotel name or null"}

Examples:
Q: "Find hotels where management fee is above 2%"
A: {"type": "structured", "key": "Management Fee", "operator": "gt", "value": "2"}

Q: "Show me all hotel opening dates"
A: {"type": "fetch_all", "key": "Hotel Opening Date"}

Q: "What is the management fee for Taj Exotica Dubai?"
A: {"type": "fetch_hotel", "key": "Management Fee", "hotel": "Taj Exotica"}

Q: "Find contracts with strict termination clauses"
A: {"type": "semantic", "query": "strict termination conditions"}

Q: "Compare management fee and incentive fee across all hotels"
A: {"type": "multi_key", "keys": ["Management Fee", "Incentive Fee"], "hotel": null}

Q: "Which hotel has the highest management fee?"
A: {"type": "semantic", "query": "highest management fee comparison"}

Q: "Tell me about Taj Tirupati contract"
A: {"type": "semantic", "query": "Taj Tirupati contract overview"}

Return ONLY valid JSON. No explanation."""


def parse_question(question: str) -> dict:
    """
    LLM Call 1 — Parse natural language question into structured query.
    Returns dict with query type and parameters.
    """
    response = openai_client.chat.completions.create(
        model       = CHAT_MODEL,
        messages    = [
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {"role": "user",   "content": question}
        ],
        temperature = 0,
        max_tokens  = 300
    )
    raw = response.choices[0].message.content.strip()
    # Clean markdown code blocks if present
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback to semantic search
        return {"type": "semantic", "query": question}


# ─────────────────────────────────────────────────────────────
# FUNCTION 2 — RETRIEVE CHUNKS FROM QDRANT (No LLM)
# ─────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list:
    """Get embedding vector for a text string."""
    response = openai_client.embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding


def keyword_search(key_name: str, hotel_name: str = None, limit: int = 100) -> list:
    """
    Exact keyword filter on key_name (and optionally hotel_name).
    Returns list of payloads.
    """
    conditions = [
        FieldCondition(key="key_name", match=MatchValue(value=key_name))
    ]
    if hotel_name:
        conditions.append(
            FieldCondition(key="hotel_name", match=MatchValue(value=hotel_name))
        )

    results, _ = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=conditions),
        limit=limit,
        with_payload=True,
        with_vectors=False
    )
    return [point.payload for point in results]


def semantic_search(query: str, top_k: int = 10) -> list:
    """
    Embed query and search Qdrant by cosine similarity.
    Returns list of payloads with scores.
    """
    query_vector = get_embedding(query)

    try:
        results = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k,
            with_payload=True
        ).points
    except AttributeError:
        results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True
        )

    return [
        {**point.payload, "_score": round(point.score, 4)}
        for point in results
    ]


def hybrid_search(query: str, key_name: str = None, top_k: int = 10) -> list:
    """
    Combine keyword filter with semantic ranking.
    If key_name provided: filter by key, then rank by similarity.
    If key_name is None: pure semantic search.
    """
    query_vector = get_embedding(query)

    search_filter = None
    if key_name:
        search_filter = Filter(
            must=[FieldCondition(key="key_name", match=MatchValue(value=key_name))]
        )

    try:
        results = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True
        ).points
    except AttributeError:
        results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True
        )

    return [
        {**point.payload, "_score": round(point.score, 4)}
        for point in results
    ]


def multi_key_search(keys: list, hotel_name: str = None) -> list:
    """
    Fetch chunks for multiple keys.
    Returns combined list of payloads.
    """
    all_results = []
    for key in keys:
        results = keyword_search(key, hotel_name)
        all_results.extend(results)
    return all_results


# ── Condition Helpers ─────────────────────────────────────────

def extract_number(value: str):
    """Extract first number from a value string."""
    match = re.search(r'[\d,]+\.?\d*', value.replace(',', ''))
    return float(match.group()) if match else None


def apply_condition(value: str, operator: str, threshold: str) -> bool:
    """Apply comparison condition to a value string."""
    if operator == "contains":
        return threshold.lower() in value.lower()

    num_val = extract_number(value)
    num_thr = extract_number(threshold)

    if num_val is None or num_thr is None:
        return False

    if operator == "gt":     return num_val > num_thr
    if operator == "lt":     return num_val < num_thr
    if operator == "eq":     return num_val == num_thr
    if operator == "after":  return num_val > num_thr
    if operator == "before": return num_val < num_thr

    return False


# ── Main Retrieval Router ─────────────────────────────────────

def retrieve_chunks(parsed: dict) -> list:
    """
    Route parsed query to the correct retrieval method.
    Returns list of chunk payloads.
    """
    qtype = parsed.get("type", "semantic")

    if qtype == "fetch_all":
        results = keyword_search(parsed["key"])
        print(f"  🔍 Keyword search: key='{parsed['key']}' → {len(results)} chunks")
        return results

    elif qtype == "fetch_hotel":
        # First try exact hotel match
        results = keyword_search(parsed["key"], parsed.get("hotel"))
        if not results:
            # Fallback: get all for that key, then semantic rank
            results = hybrid_search(
                query=f"{parsed.get('hotel', '')} {parsed['key']}",
                key_name=parsed["key"],
                top_k=5
            )
        print(f"  🔍 Hotel search: key='{parsed['key']}', hotel='{parsed.get('hotel')}' → {len(results)} chunks")
        return results

    elif qtype == "structured":
        all_results = keyword_search(parsed["key"])
        filtered = [
            r for r in all_results
            if apply_condition(r.get("value", ""), parsed["operator"], parsed["value"])
        ]
        print(f"  🔍 Structured: key='{parsed['key']}' {parsed['operator']} {parsed['value']} → {len(filtered)}/{len(all_results)} chunks")
        return filtered

    elif qtype == "multi_key":
        results = multi_key_search(parsed["keys"], parsed.get("hotel"))
        print(f"  🔍 Multi-key: keys={parsed['keys']} → {len(results)} chunks")
        return results

    elif qtype == "semantic":
        results = semantic_search(parsed["query"], top_k=10)
        print(f"  🔍 Semantic: query='{parsed['query']}' → {len(results)} chunks")
        return results

    return []


# ─────────────────────────────────────────────────────────────
# FUNCTION 3 — GENERATE RESPONSE (LLM Call 2 — THE RAG STEP)
# ─────────────────────────────────────────────────────────────

GENERATE_SYSTEM_PROMPT = """You are a hotel contract analysis assistant.

You will receive:
1. A user's question about hotel contracts
2. Retrieved contract chunks (each with metadata: hotel name, section, key, page, and value)

Your job:
- Read and understand ALL the retrieved chunks
- Answer the user's question accurately based ONLY on the provided chunks
- Output a structured JSON response

RESPONSE FORMAT:
{
    "answer": "Brief natural language answer to the question",
    "data": [
        {
            "hotel_name": "Hotel name",
            "agreement_type": "Agreement type",
            "section": "Section name",
            "key": "Key name",
            "value": "Extracted/structured value",
            "page_no": page number,
            "notes": "Any additional context or observations (optional)"
        }
    ],
    "summary": "Brief comparison or analysis if applicable (optional)"
}

RULES:
1. Use ONLY information from the provided chunks. Never fabricate data.
2. If a value is "N/A", include it as "N/A" — do not skip it.
3. For complex values (fee structures, multi-condition clauses), break them down into readable format.
4. If the question asks for comparison, include a "summary" field with your analysis.
5. If chunks don't contain enough information to answer, say so in the "answer" field.
6. Keep "value" concise but complete — restructure long paragraphs into key points.
7. Return ONLY valid JSON. No explanation outside JSON."""


def generate_response(question: str, chunks: list) -> dict:
    """
    LLM Call 2 — THE RAG STEP.
    Send question + retrieved chunks to LLM for structured extraction.
    """
    if not chunks:
        return {
            "answer": "No relevant contract data found for this query.",
            "data": [],
            "summary": ""
        }

    # ── Build context from retrieved chunks ──────────────────
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        chunk_text = chunk.get("chunk_text", "")
        if not chunk_text:
            # Fallback: build from payload fields
            chunk_text = (
                f"HOTEL: {chunk.get('hotel_name', 'Unknown')}\n"
                f"SECTION: {chunk.get('section', 'Unknown')}\n"
                f"KEY: {chunk.get('key_name', 'Unknown')}\n"
                f"PAGE: {chunk.get('page_no', '?')}\n"
                f"---\n"
                f"{chunk.get('value', 'N/A')}"
            )

        score = chunk.get("_score", "")
        score_str = f" [relevance: {score}]" if score else ""

        context_parts.append(f"--- CHUNK {i}{score_str} ---\n{chunk_text}")

    context = "\n\n".join(context_parts)

    # ── Build user message ───────────────────────────────────
    user_message = f"""QUESTION: {question}

RETRIEVED CONTRACT CHUNKS ({len(chunks)} chunks):

{context}

Based on the above chunks, provide a structured JSON response answering the question."""

    # ── LLM Call ─────────────────────────────────────────────
    response = openai_client.chat.completions.create(
        model       = CHAT_MODEL,
        messages    = [
            {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
            {"role": "user",   "content": user_message}
        ],
        temperature = 0,
        max_tokens  = 4000
    )

    raw = response.choices[0].message.content.strip()
    # Clean markdown code blocks
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # If LLM returns non-JSON, wrap it
        return {
            "answer": raw,
            "data": [{"hotel_name": c.get("hotel_name", ""), "key": c.get("key_name", ""), "value": c.get("value", "")} for c in chunks],
            "summary": ""
        }


# ─────────────────────────────────────────────────────────────
# FUNCTION 4 — EXPORT TO EXCEL
# ─────────────────────────────────────────────────────────────

def export_to_excel(response: dict, question: str) -> Path:
    """
    Export structured JSON response to formatted Excel.
    Returns path to the generated file.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"

    # ── Styles ───────────────────────────────────────────────
    header_font  = Font(name="Calibri", bold=True, size=12, color="FFFFFF")
    header_fill  = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    data_font    = Font(name="Calibri", size=11)
    data_align   = Alignment(vertical="top", wrap_text=True)

    question_font = Font(name="Calibri", bold=True, size=13, color="2F5496")
    answer_font   = Font(name="Calibri", size=11, italic=True)
    summary_font  = Font(name="Calibri", size=11, bold=True, color="2F5496")

    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin")
    )

    alt_fill = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")

    # ── Row 1: Question ──────────────────────────────────────
    ws.merge_cells("A1:G1")
    cell = ws["A1"]
    cell.value = f"Q: {question}"
    cell.font = question_font
    cell.alignment = Alignment(wrap_text=True)
    ws.row_dimensions[1].height = 30

    # ── Row 2: Answer ────────────────────────────────────────
    answer = response.get("answer", "")
    if answer:
        ws.merge_cells("A2:G2")
        cell = ws["A2"]
        cell.value = f"A: {answer}"
        cell.font = answer_font
        cell.alignment = Alignment(wrap_text=True)
        ws.row_dimensions[2].height = 40

    # ── Row 3: Summary (if present) ──────────────────────────
    summary = response.get("summary", "")
    start_row = 3
    if summary:
        ws.merge_cells("A3:G3")
        cell = ws["A3"]
        cell.value = f"Summary: {summary}"
        cell.font = summary_font
        cell.alignment = Alignment(wrap_text=True)
        ws.row_dimensions[3].height = 40
        start_row = 4

    # ── Row 4+: Empty row separator ──────────────────────────
    start_row += 1

    # ── Data Headers ─────────────────────────────────────────
    data = response.get("data", [])
    if not data:
        ws.merge_cells(f"A{start_row}:G{start_row}")
        ws[f"A{start_row}"].value = "No data records returned."
        ws[f"A{start_row}"].font = data_font
    else:
        # Determine columns from first data record
        # Use a consistent column order
        preferred_order = [
            "hotel_name", "agreement_type", "section", "key",
            "value", "page_no", "notes"
        ]

        # Collect all keys from all data records
        all_keys = set()
        for record in data:
            all_keys.update(record.keys())

        # Order: preferred first, then any extras
        columns = [k for k in preferred_order if k in all_keys]
        extras = sorted(all_keys - set(preferred_order))
        columns.extend(extras)

        # Pretty column names
        col_display = {
            "hotel_name":      "Hotel Name",
            "agreement_type":  "Agreement Type",
            "section":         "Section",
            "key":             "Key",
            "value":           "Value",
            "page_no":         "Page",
            "notes":           "Notes",
        }

        # Write headers
        header_row = start_row
        for col_idx, col_key in enumerate(columns, 1):
            cell = ws.cell(row=header_row, column=col_idx)
            cell.value = col_display.get(col_key, col_key.replace("_", " ").title())
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = thin_border

        # Write data rows
        for row_idx, record in enumerate(data, header_row + 1):
            for col_idx, col_key in enumerate(columns, 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                value = record.get(col_key, "")

                # Handle nested dicts/lists → convert to readable string
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2, ensure_ascii=False)

                cell.value = str(value) if value is not None else ""
                cell.font = data_font
                cell.alignment = data_align
                cell.border = thin_border

                # Alternate row coloring
                if row_idx % 2 == 0:
                    cell.fill = alt_fill

        # ── Auto-fit column widths ───────────────────────────
        for col_idx, col_key in enumerate(columns, 1):
            max_width = len(col_display.get(col_key, col_key)) + 2

            for row_idx in range(header_row, header_row + len(data) + 1):
                cell_value = str(ws.cell(row=row_idx, column=col_idx).value or "")
                # For multi-line values, use longest line
                lines = cell_value.split("\n")
                longest_line = max(len(line) for line in lines) if lines else 0
                max_width = max(max_width, min(longest_line + 2, 60))

            col_letter = openpyxl.utils.get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = max_width

    # ── Row heights for wrapped text ─────────────────────────
    for row in ws.iter_rows(min_row=start_row + 1, max_row=ws.max_row):
        for cell in row:
            if cell.value and len(str(cell.value)) > 60:
                ws.row_dimensions[cell.row].height = max(
                    ws.row_dimensions[cell.row].height or 15,
                    min(len(str(cell.value)) // 2, 200)
                )

    # ── Save ─────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Clean question for filename
    safe_question = re.sub(r'[^\w\s-]', '', question)[:50].strip()
    safe_question = re.sub(r'\s+', '_', safe_question)

    file_path = OUTPUT_DIR / f"{safe_question}_{timestamp}.xlsx"
    wb.save(str(file_path))
    return file_path


# ─────────────────────────────────────────────────────────────
# FUNCTION 5 — ASK (Orchestrator)
# ─────────────────────────────────────────────────────────────

def ask(question: str, export_excel: bool = True, verbose: bool = True):
    """
    Full RAG pipeline:
    1. Parse question (LLM)
    2. Retrieve chunks (Qdrant)
    3. Generate response (LLM + chunks)
    4. Export to Excel (optional)
    """
    if verbose:
        print(f"\n{'═' * 60}")
        print(f"  QUESTION: {question}")
        print(f"{'═' * 60}")

    # ── Step 1: Parse ────────────────────────────────────────
    if verbose:
        print(f"\n  Step 1: Parsing question...")
    parsed = parse_question(question)
    if verbose:
        print(f"  Parsed: {json.dumps(parsed, indent=2)}")

    # ── Step 2: Retrieve ─────────────────────────────────────
    if verbose:
        print(f"\n  Step 2: Retrieving chunks...")
    chunks = retrieve_chunks(parsed)
    if verbose:
        print(f"  Retrieved: {len(chunks)} chunks")
        for i, c in enumerate(chunks[:5], 1):
            hotel = c.get("hotel_name", "?")
            key = c.get("key_name", "?")
            val = c.get("value", "")[:50]
            score = c.get("_score", "")
            score_str = f" [{score}]" if score else ""
            print(f"    {i}. {hotel} → {key}: {val}...{score_str}")
        if len(chunks) > 5:
            print(f"    ... and {len(chunks) - 5} more")

    # ── Step 3: Generate (RAG) ───────────────────────────────
    if verbose:
        print(f"\n  Step 3: Generating response (RAG)...")
    response = generate_response(question, chunks)
    if verbose:
        print(f"  Answer: {response.get('answer', '')[:100]}...")
        print(f"  Data records: {len(response.get('data', []))}")
        if response.get("summary"):
            print(f"  Summary: {response['summary'][:100]}...")

    # ── Step 4: Export ───────────────────────────────────────
    if export_excel:
        if verbose:
            print(f"\n  Step 4: Exporting to Excel...")
        file_path = export_to_excel(response, question)
        if verbose:
            print(f"  📊 Saved: {file_path}")

    # ── Print full JSON response ─────────────────────────────
    if verbose:
        print(f"\n  {'─' * 50}")
        print(f"  Full JSON Response:")
        print(f"  {'─' * 50}")
        print(json.dumps(response, indent=2, ensure_ascii=False))

    return response


# ─────────────────────────────────────────────────────────────
# INTERACTIVE MODE
# ─────────────────────────────────────────────────────────────

def interactive():
    """
    Interactive query mode — ask questions in a loop.
    Type 'quit' or 'exit' to stop.
    """
    print("\n" + "═" * 60)
    print("  🏨 HOTEL CONTRACT RAG — Interactive Mode")
    print("  Type your question and press Enter.")
    print("  Type 'quit' or 'exit' to stop.")
    print("═" * 60)

    while True:
        print()
        question = input("  📝 Your question: ").strip()

        if not question:
            continue

        if question.lower() in ("quit", "exit", "q"):
            print("\n  👋 Goodbye!")
            break

        try:
            ask(question)
        except Exception as e:
            print(f"\n  ❌ Error: {e}")
            import traceback
            traceback.print_exc()


# ─────────────────────────────────────────────────────────────
# MAIN — TEST QUERIES
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        # ── Test with predefined queries ─────────────────────
        test_queries = [
            "Show me all management fees across all hotels",
            "Which hotel has the highest management fee?",
            "What are the termination clauses for Taj Exotica Dubai?",
            "Compare renewal terms across all hotels",
            "Find hotels where incentive fee mentions GOP above 50%",
        ]

        # Run just the first query as a test
        # Change index or uncomment loop to run more
        ask(test_queries[0])

        # ── Or run all test queries ──────────────────────────
        # for q in test_queries:
        #     ask(q)

        # ── Or start interactive mode ────────────────────────
        # interactive()

    finally:
        qdrant_client.close()