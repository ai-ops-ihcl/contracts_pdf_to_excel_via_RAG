import re
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime
from pathlib import Path
from openai import AzureOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from dotenv import load_dotenv
import os
# Load environment variables from .env file
load_dotenv()

# ── Config ────────────────────────────────────────────────────
AZURE_API_KEY     = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT    = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
EMBEDDING_MODEL   = "text-embedding-3-large"  # TODO: Replace with your Azure deployment name
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
# STEP 1 — PARSE QUESTION
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a hotel contract query parser.

Given a natural language question, return ONLY a JSON object.

Known contract keys (use exact spelling):
- Name of Hotel, Owner Details and Address, Operator details and Address
- Region, No. of Rooms, Hotel Opening Date, Nature of Right of Owner
- Original Execution Date, Original Term, Valid from, Valid up to, Lock-in Period
- Renewal Term, Renewal Notice Period, Conditions of Renewal
- Management Fee, Incentive Fee, Fee Threshold, Sales & Marketing Fee
- Central Group Services Fee, Loyalty Program Fee, Reimbursables
- Key Personnel, Termination at Will, Termination by Owner, Termination by Operator
- Consequences of Termination, Liquidated Damages
- Non-compete Clause, Sale Transfer Clause, Area of Protection
- Governing Law and Jurisdiction, Arbitration

Return one of these formats:

FORMAT 1 — Structured query (field with condition):
{"type": "structured", "key": "exact key", "operator": "gt|lt|eq|contains|after|before", "value": "comparison value"}

FORMAT 2 — Fetch all values for a key:
{"type": "fetch_all", "key": "exact key"}

FORMAT 3 — Semantic query (no specific field):
{"type": "semantic", "query": "rephrased search query"}

Examples:
Q: "Find hotels where management fee is above 2%"
A: {"type": "structured", "key": "Management Fee", "operator": "gt", "value": "2"}

Q: "Show me all hotel opening dates"
A: {"type": "fetch_all", "key": "Hotel Opening Date"}

Q: "Find contracts with strict termination clauses"
A: {"type": "semantic", "query": "strict termination conditions"}

Return ONLY valid JSON. No explanation.
"""


def parse_question(question: str) -> dict:
    response = openai_client.chat.completions.create(
        model       = CHAT_MODEL,
        messages    = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": question}
        ],
        temperature = 0,
        max_tokens  = 200
    )
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r'```json|```', '', raw).strip()
    return json.loads(raw)


# ─────────────────────────────────────────────────────────────
# STEP 2 — RETRIEVE FROM QDRANT
# ─────────────────────────────────────────────────────────────

def get_all_by_key(key_name: str) -> list[dict]:
    """Fetch all contracts matching a key."""
    results = qdrant_client.scroll(
        collection_name = COLLECTION_NAME,
        scroll_filter   = Filter(
            must=[FieldCondition(
                key   = "key",
                match = MatchValue(value=key_name)
            )]
        ),
        limit        = 500,
        with_payload = True,
        with_vectors = False
    )
    return [p.payload for p in results[0]]


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """Embed query and search Qdrant by similarity."""
    response = openai_client.embeddings.create(
        input = [query],
        model = EMBEDDING_MODEL
    )
    query_vector = response.data[0].embedding

    results = qdrant_client.query_points(
        collection_name = COLLECTION_NAME,
        query           = query_vector,
        limit           = top_k,
        with_payload    = True
    ).points

    return [{**r.payload, "score": round(r.score, 4)} for r in results]


# ─────────────────────────────────────────────────────────────
# STEP 3 — APPLY CONDITIONS (for structured queries)
# ─────────────────────────────────────────────────────────────

def extract_number(value: str):
    match = re.search(r'\d+\.?\d*', value.replace(',', ''))
    return float(match.group()) if match else None


def extract_year(value: str):
    match = re.search(r'\b(19|20)\d{2}\b', value)
    return int(match.group()) if match else None


def apply_condition(value: str, operator: str, threshold: str) -> bool:
    if operator in ("gt", "lt", "eq"):
        num_val = extract_number(value)
        num_thr = extract_number(threshold)
        if num_val is None or num_thr is None:
            return False
        if operator == "gt":  return num_val > num_thr
        if operator == "lt":  return num_val < num_thr
        if operator == "eq":  return num_val == num_thr

    elif operator in ("after", "before"):
        year_val = extract_year(value)
        year_thr = extract_year(threshold)
        if year_val is None or year_thr is None:
            return False
        if operator == "after":  return year_val > year_thr
        if operator == "before": return year_val < year_thr

    elif operator == "contains":
        return threshold.lower() in value.lower()

    return False


def execute_query(parsed: dict) -> list[dict]:
    """Run the parsed query against Qdrant."""
    qtype = parsed.get("type")

    if qtype == "fetch_all":
        return get_all_by_key(parsed["key"])

    elif qtype == "structured":
        all_results = get_all_by_key(parsed["key"])
        return [
            r for r in all_results
            if apply_condition(r.get("value", ""), parsed["operator"], parsed["value"])
        ]

    elif qtype == "semantic":
        return semantic_search(parsed["query"])

    return []


# ─────────────────────────────────────────────────────────────
# STEP 4 — EXPORT TO EXCEL
# ─────────────────────────────────────────────────────────────

def export_to_excel(results: list[dict], question: str) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"

    header_font  = Font(bold=True, color="FFFFFF")
    header_fill  = PatternFill("solid", fgColor="1F4E79")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # ── question row ──────────────────────────────────────────
    ws.merge_cells("A1:F1")
    ws["A1"]            = f"Query: {question}"
    ws["A1"].font       = Font(bold=True, italic=True, size=12)
    ws["A1"].fill       = PatternFill("solid", fgColor="D6E4F0")
    ws["A1"].alignment  = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 25

    # ── column headers ────────────────────────────────────────
    headers = ["#", "Hotel Name", "Contract ID", "Section", "Key", "Value"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=header)
        cell.font      = header_font
        cell.fill      = header_fill
        cell.alignment = header_align
    ws.row_dimensions[2].height = 20

    # ── data rows ─────────────────────────────────────────────
    alt_fill = PatternFill("solid", fgColor="EBF3FB")
    for i, result in enumerate(results, 1):
        row  = i + 2
        fill = alt_fill if i % 2 == 0 else None
        data = [
            i,
            result.get("hotel_name", ""),
            result.get("contract_id", ""),
            result.get("section", ""),
            result.get("key", ""),
            result.get("value", "")
        ]
        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if fill:
                cell.fill = fill

    # ── column widths ─────────────────────────────────────────
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 35
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 25
    ws.column_dimensions["F"].width = 60

    # ── save ──────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath  = OUTPUT_DIR / f"query_result_{timestamp}.xlsx"
    wb.save(filepath)
    return filepath


# ─────────────────────────────────────────────────────────────
# MAIN — ASK QUESTION
# ─────────────────────────────────────────────────────────────

def ask(question: str):
    print(f"\n{'─'*60}")
    print(f"Question : {question}")
    print(f"{'─'*60}")

    print("Parsing...")
    parsed = parse_question(question)
    print(f"Parsed   : {json.dumps(parsed)}")

    print("Retrieving...")
    results = execute_query(parsed)
    print(f"Results  : {len(results)} found")

    if not results:
        print("No results found.")
        return

    # preview top 5
    print(f"\n{'─'*60}")
    print("PREVIEW (first 5):")
    print(f"{'─'*60}")
    for r in results[:5]:
        print(f"  Hotel : {r.get('hotel_name')}")
        print(f"  Key   : {r.get('key')}")
        print(f"  Value : {str(r.get('value'))[:100]}")
        print()

    filepath = export_to_excel(results, question)
    print(f"✅ Excel saved: {filepath}")


# ─────────────────────────────────────────────────────────────
# TEST QUERIES
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ask("Find all hotels where management fee is above 2%")
    ask("Show me all hotel opening dates")
    ask("Which contracts are valid up to  before 2030?")
    ask("Find hotels with area of protection clauses")

    qdrant_client.close()