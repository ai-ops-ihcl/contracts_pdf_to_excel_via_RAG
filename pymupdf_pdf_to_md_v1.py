import time
import pymupdf4llm
from pathlib import Path

INPUT_DIR  = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\demo_217")
OUTPUT_DIR = Path(r"C:\Users\bipin_kes\OneDrive\Desktop\pdf_to_md\demo_markdowns")
OUTPUT_DIR.mkdir(exist_ok=True)

def convert_all():
    pdfs = list(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in ./pdfs folder.")
        return

    print(f"Found {len(pdfs)} PDFs. Starting conversion...\n")

    success, failed = [], []
    start = time.time()

    for pdf_path in pdfs:
        out_path = OUTPUT_DIR / pdf_path.with_suffix(".md").name

        if out_path.exists():
            print(f"⏭  Skipping (already done): {pdf_path.name}")
            continue

        try:
            md_text = pymupdf4llm.to_markdown(str(pdf_path))
            out_path.write_text(md_text, encoding="utf-8")
            print(f"✅ {pdf_path.name}")
            success.append(pdf_path.name)
        except Exception as e:
            print(f"❌ {pdf_path.name} → {e}")
            failed.append((pdf_path.name, str(e)))

    elapsed = time.time() - start
    print(f"\n{'─'*50}")
    print(f"Done in {elapsed:.1f}s  |  ✅ {len(success)}  ❌ {len(failed)}")

    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")

if __name__ == "__main__":
    convert_all()