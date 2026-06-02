
# 🏨 IHCL Hotel Contract RAG Pipeline

This project is an automated pipeline to extract structured contractual data from IHCL (Indian Hotels Company Limited) hotel agreement PDFs.

# 📂 Project Structure

pdf_to_md/
├── pdf_to_md_with_delimiter_v2.py   # Step 1
├── embedding_pipeline.py            # Step 2
├── verify_pipeline.py               # Step 3
├── query_v2.py                      # Step 4
├── inspect_chunks.py                # Debug tool
├── CORE_KEYS_LIST.py                # Key definitions

---

# 🧩 Files and Usage

## pdf_to_md_with_delimiter_v2.py
Purpose: Converts PDF files into structured markdown with section and key delimiters.

Run:
python pdf_to_md_with_delimiter_v2.py

---

## embedding_pipeline.py
Purpose: Parses markdown, creates chunks, generates embeddings, and stores data in Qdrant.

Run:
python embedding_pipeline.py

---

## verify_pipeline.py
Purpose: Runs validation checks on stored vector data to ensure quality.

Run 
python verify_pipeline.py

---

## query_v2.py
Purpose: Extracts predefined attributes and exports them into structured Excel format.

Run:
python query_v2.py

---

## inspect_chunks.py
Purpose: Debug tool to inspect all chunks for a specific file stored in Qdrant.

Run (optional): for validation
python inspect_chunks.py

---

## CORE_KEYS_LIST.py
Purpose: Contains complete list of contract keys used for extraction and matching.

Run (optional):
python CORE_KEYS_LIST.py

---

# 🚀 Execution Order

```bash
# Full pipeline — run in order:
python pdf_to_md_with_delimiter_v2.py      # Step 1: PDF → Markdown
python embedding_pipeline.py         # Step 2: Markdown → Qdrant
python verify_pipeline.py            # Step 3: Quality checks
python query_v2.py                   # Step 4: Extract → Excel
```

---

# ⚠️ Notes

- Always re-run embedding pipeline after any parsing changes
- Qdrant DB is stored locally in ./qdrant_local



*Built for IHCL — Indian Hotels Company Limited (Tata Group)*
