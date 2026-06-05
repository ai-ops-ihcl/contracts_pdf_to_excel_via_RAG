import os
from pathlib import Path
from dotenv import load_dotenv
from openai import AzureOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

load_dotenv()

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

AZURE_API_KEY      = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_ENDPOINT     = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_VERSION  = os.getenv("AZURE_OPENAI_API_VERSION")
EMBEDDING_MODEL    = "text-embedding-3-large"
VECTOR_DIM         = 3072
COLLECTION_NAME    = "hotel_contracts"
QDRANT_PATH        = "./qdrant_local"

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
# HELPER — Get embedding
# ─────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list:
    """Get embedding vector for a text string."""
    response = openai_client.embeddings.create(
        input=[text],
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding

# ─────────────────────────────────────────────────────────────
# HELPER — Scroll all points
# ─────────────────────────────────────────────────────────────

def scroll_all(limit: int = 1000) -> list:
    """Scroll all points from the collection."""
    results = qdrant_client.scroll(
        collection_name=COLLECTION_NAME,
        limit=limit,
        with_payload=True,
        with_vectors=False
    )[0]
    return results

# ─────────────────────────────────────────────────────────────
# CHECK 1 — Collection Stats
# ─────────────────────────────────────────────────────────────

def check_1_collection_stats() -> bool:
    """Verify collection exists, has points, and correct vector dimension."""
    print("\n" + "─" * 60)
    print("  CHECK 1 — Collection Stats")
    print("─" * 60)

    try:
        info = qdrant_client.get_collection(COLLECTION_NAME)
        total_points = info.points_count
        vectors_config = info.config.params.vectors

        # Get vector size — handle both named and unnamed vector configs
        if hasattr(vectors_config, "size"):
            vec_dim = vectors_config.size
        elif isinstance(vectors_config, dict):
            first_key = list(vectors_config.keys())[0]
            vec_dim = vectors_config[first_key].size
        else:
            vec_dim = "Unknown"

        status = info.status

        print(f"  Collection:      {COLLECTION_NAME}")
        print(f"  Total points:    {total_points}")
        print(f"  Vector dimension: {vec_dim}")
        print(f"  Status:          {status}")

        passed = total_points > 0 and vec_dim == VECTOR_DIM
        print(f"\n  Result: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

# ─────────────────────────────────────────────────────────────
# CHECK 2 — Sample Chunks
# ─────────────────────────────────────────────────────────────

def check_2_sample_chunks() -> bool:
    """Pull 3 sample chunks and inspect their structure."""
    print("\n" + "─" * 60)
    print("  CHECK 2 — Sample Chunks")
    print("─" * 60)

    try:
        results = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            limit=3,
            with_payload=True,
            with_vectors=False
        )[0]

        if not results:
            print("  ERROR: No points found")
            return False

        for i, point in enumerate(results, 1):
            p = point.payload
            value = str(p.get("value", ""))
            value_display = value[:100] + "..." if len(value) > 100 else value

            print(f"\n  --- Sample {i} (ID: {point.id}) ---")
            print(f"  Hotel:          {p.get('hotel_name', 'N/A')}")
            print(f"  Agreement Type: {p.get('agreement_type', 'N/A')}")
            print(f"  File Name:      {p.get('file_name', 'N/A')}")
            print(f"  Section:        {p.get('section', 'N/A')}")
            print(f"  Key Name:       {p.get('key_name', 'N/A')}")
            print(f"  Page No:        {p.get('page_no', 'N/A')}")
            print(f"  Value:          {value_display}")

        # Check that required fields exist
        required_fields = ["hotel_name", "key_name", "section", "value", "page_no"]
        sample_payload = results[0].payload
        missing = [f for f in required_fields if f not in sample_payload]

        if missing:
            print(f"\n  WARNING: Missing fields in payload: {missing}")

        passed = len(results) > 0 and len(missing) == 0
        print(f"\n  Result: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

# ─────────────────────────────────────────────────────────────
# CHECK 3 — Per-Hotel Breakdown
# ─────────────────────────────────────────────────────────────

def check_3_per_hotel_breakdown() -> bool:
    """Group all chunks by hotel and show breakdown."""
    print("\n" + "─" * 60)
    print("  CHECK 3 — Per-Hotel Breakdown")
    print("─" * 60)

    try:
        all_points = scroll_all()

        if not all_points:
            print("  ERROR: No points found")
            return False

        # Group by hotel
        hotels = {}
        for point in all_points:
            hotel = point.payload.get("hotel_name", "Unknown")
            section = point.payload.get("section", "")

            if hotel not in hotels:
                hotels[hotel] = {"chunks": 0, "sections": set()}
            hotels[hotel]["chunks"] += 1
            if section:
                hotels[hotel]["sections"].add(section)

        print(f"\n  {'Hotel':<50} {'Chunks':>8} {'Sections':>10}")
        print(f"  {'─' * 50} {'─' * 8} {'─' * 10}")

        for hotel in sorted(hotels.keys()):
            data = hotels[hotel]
            print(f"  {hotel:<50} {data['chunks']:>8} {len(data['sections']):>10}")

        print(f"\n  Total: {len(all_points)} points across {len(hotels)} hotel(s)")

        # Show sections for each hotel
        print(f"\n  Section Details:")
        for hotel in sorted(hotels.keys()):
            sections = sorted(hotels[hotel]["sections"])
            print(f"    {hotel}:")
            for s in sections:
                print(f"      - {s}")

        passed = len(hotels) > 0
        print(f"\n  Result: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

# ─────────────────────────────────────────────────────────────
# CHECK 4 — Keyword Filter Test
# ─────────────────────────────────────────────────────────────

def check_4_keyword_filter() -> bool:
    """Test keyword filtering on known key names."""
    print("\n" + "─" * 60)
    print("  CHECK 4 — Keyword Filter Test")
    print("─" * 60)

    test_keys = ["Management Fee", "Name of Hotel", "Renewal Term", "Arbitration"]
    all_found = True

    for key_name in test_keys:
        results = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(must=[
                FieldCondition(key="key_name", match=MatchValue(value=key_name))
            ]),
            limit=100,
            with_payload=True,
            with_vectors=False
        )[0]

        hotels = set(p.payload.get("hotel_name", "Unknown") for p in results)
        count = len(results)
        status = "OK" if count > 0 else "MISS"

        if count == 0:
            all_found = False

        print(f"\n  '{key_name}': {count} chunk(s) across {len(hotels)} hotel(s) [{status}]")
        for h in sorted(hotels):
            print(f"    - {h}")

    print(f"\n  Result: {'PASS' if all_found else 'PARTIAL — some keys not found'}")
    return all_found

# ─────────────────────────────────────────────────────────────
# CHECK 5 — Semantic Search Test
# ─────────────────────────────────────────────────────────────

def check_5_semantic_search() -> bool:
    """Test semantic search with natural language queries."""
    print("\n" + "─" * 60)
    print("  CHECK 5 — Semantic Search Test")
    print("─" * 60)

    test_queries = [
        "management fee percentage",
        "hotel termination clause",
        "contract renewal period",
    ]

    all_good = True

    for query in test_queries:
        print(f"\n  Query: \"{query}\"")

        try:
            query_vector = get_embedding(query)

            results = qdrant_client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=3,
                with_payload=True
            )

            if not results.points:
                print("    No results found")
                all_good = False
                continue

            for rank, point in enumerate(results.points, 1):
                p = point.payload
                print(
                    f"    #{rank}  score={point.score:.4f}  "
                    f"hotel={p.get('hotel_name', 'N/A'):<40}  "
                    f"key={p.get('key_name', 'N/A'):<25}  "
                    f"section={p.get('section', 'N/A')}"
                )

            # Check score range
            top_score = results.points[0].score
            if top_score < 0.30:
                print(f"    WARNING: Top score {top_score:.4f} is very low")
                all_good = False

        except Exception as e:
            print(f"    ERROR: {e}")
            all_good = False

    print(f"\n  Result: {'PASS' if all_good else 'PARTIAL — check scores'}")
    return all_good

# ─────────────────────────────────────────────────────────────
# CHECK 6 — Chunk Format Verification
# ─────────────────────────────────────────────────────────────

def check_6_chunk_format() -> bool:
    """Verify chunk data quality: no empty fields, no noise, no leaks."""
    print("\n" + "─" * 60)
    print("  CHECK 6 — Chunk Format Verification")
    print("─" * 60)

    try:
        all_points = scroll_all()

        if not all_points:
            print("  ERROR: No points found")
            return False

        total = len(all_points)
        empty_key_names = 0
        empty_sections = 0
        empty_values = 0
        audit_leaks = 0
        leftover_noise = 0

        for point in all_points:
            p = point.payload
            key_name = p.get("key_name", "").strip()
            section = p.get("section", "").strip()
            value = str(p.get("value", "")).strip()

            # Empty field checks
            if not key_name:
                empty_key_names += 1
            if not section:
                empty_sections += 1
            if not value:
                empty_values += 1

            # Audit trail leak check
            # (audit trail chunks should be separated — if they show up
            #  in the main collection with section containing "AUDIT", flag it)
            if "AUDIT" in section.upper() and "TRAIL" in section.upper():
                audit_leaks += 1

            # Leftover noise check
            if "---" in value or "|||" in value:
                leftover_noise += 1

        # Print results
        checks = {
            "Empty key_names":    (empty_key_names, empty_key_names == 0),
            "Empty sections":     (empty_sections, empty_sections <= 2),  # Allow minor tolerance
            "Empty values":       (empty_values, empty_values == 0),
            "Audit trail leaks":  (audit_leaks, audit_leaks == 0),
            "Leftover noise":     (leftover_noise, leftover_noise == 0),
        }

        all_pass = True
        for check_name, (count, passed) in checks.items():
            status = "PASS" if passed else "WARN"
            if not passed:
                all_pass = False
            print(f"  {status:<6} {check_name}: {count} / {total}")

        print(f"\n  Result: {'PASS' if all_pass else 'PARTIAL — see warnings above'}")
        return all_pass

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

# ─────────────────────────────────────────────────────────────
# MAIN — Run All Checks
# ─────────────────────────────────────────────────────────────

def run_all_checks():
    """Run all 6 verification checks and print summary."""
    print()
    print("=" * 60)
    print("  IHCL Hotel Contracts — Pipeline Verification")
    print("=" * 60)

    checks = [
        ("Collection Stats",          check_1_collection_stats),
        ("Sample Chunks",             check_2_sample_chunks),
        ("Per-Hotel Breakdown",       check_3_per_hotel_breakdown),
        ("Keyword Filter Test",       check_4_keyword_filter),
        ("Semantic Search Test",      check_5_semantic_search),
        ("Chunk Format Verification", check_6_chunk_format),
    ]

    results = []
    for name, func in checks:
        try:
            passed = func()
        except Exception as e:
            print(f"  UNEXPECTED ERROR in {name}: {e}")
            passed = False
        results.append((name, passed))

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)

    passed_count = 0
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        icon = "[OK]" if passed else "[!!]"
        print(f"  {icon} Check: {name} — {status}")
        if passed:
            passed_count += 1

    print(f"\n  Result: {passed_count} / {len(checks)} checks passed")
    print("=" * 60)

    return passed_count == len(checks)

def diagnose_empty_fields():
    """Find which chunks have empty sections or empty values."""
    print("\n" + "=" * 60)
    print("  DIAGNOSTIC — Empty Sections & Values")
    print("=" * 60)

    all_points = scroll_all()

    print("\n  ── Chunks with EMPTY SECTION ──")
    for point in all_points:
        p = point.payload
        if not p.get("section", "").strip():
            print(
                f"    Hotel: {p.get('hotel_name', 'N/A'):<45} "
                f"Key: {p.get('key_name', 'N/A'):<30} "
                f"Page: {p.get('page_no', 'N/A')}"
            )

    print("\n  ── Chunks with EMPTY VALUE ──")
    for point in all_points:
        p = point.payload
        if not str(p.get("value", "")).strip():
            print(
                f"    Hotel: {p.get('hotel_name', 'N/A'):<45} "
                f"Key: {p.get('key_name', 'N/A'):<30} "
                f"Section: {p.get('section', 'N/A')}"
            )


if __name__ == "__main__":
    try:
        run_all_checks()
        diagnose_empty_fields()    # ← add this line
    finally:
        qdrant_client.close()