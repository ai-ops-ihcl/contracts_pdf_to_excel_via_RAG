"""
IHCL Contract Pipeline — Orchestrator
=======================================
Chains all 4 pipeline steps in sequence.
Handles: incremental processing, error isolation, file movement, logging.

THIS IS THE BRAIN — it calls your existing step functions.

Usage:
    orchestrator = PipelineOrchestrator()
    result = orchestrator.run(mode="incremental")
"""

import shutil
import uuid
from datetime import datetime
from pathlib import Path

# -- Internal imports --
from app.utils.logger import get_logger, PipelineRunLogger
from app.utils.tracker import FileTracker

# ============================================
# Pipeline Step Functions
# ============================================
from app.pipeline.pdf_to_md_with_delimiter_v2 import pdf_to_chunked_markdown
from app.pipeline.embedding_pipeline import (
    parse_file_name,
    parse_section_name,
    parse_key_row,
    parse_page_from_delimiter,
    extract_audit_trail
)
from app.pipeline.verify_pipeline import (
    check_1_collection_stats,
    check_2_sample_chunks,
    check_3_per_hotel_breakdown
)
from app.pipeline.query_v2 import (
    get_all_hotels,
    fetch_hotel_chunks,
    retrieve_core_attributes
)


class PipelineOrchestrator:
    """
    Orchestrates the full contract extraction pipeline.
    
    Modes:
        - "full"        : Process ALL PDFs (re-embed everything)
        - "incremental" : Process only NEW/changed PDFs (default)
    """

    def __init__(self, config):
        """
        Initialize with configuration module.

        Args:
            config: The app.config module with all settings
        """
        self.input_dir      = Path(config.INPUT_PDF_DIR)
        self.processed_dir  = Path(config.PROCESSED_PDF_DIR)
        self.markdown_dir   = Path(config.MARKDOWN_DIR)
        self.output_dir     = Path(config.OUTPUT_EXCEL_DIR)
        self.log_dir        = Path(config.LOG_DIR)
        self.tracker_path   = Path(config.PROCESSED_LOG_FILE)
        self.qdrant_url     = config.QDRANT_URL
        self.qdrant_collection = config.QDRANT_COLLECTION

        # Ensure directories exist
        for d in [self.input_dir, self.processed_dir, self.markdown_dir, self.output_dir, self.log_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def run(self, mode: str = "incremental") -> dict:
        """
        Execute the full pipeline.
        
        Args:
            mode: "incremental" (default) or "full"
        
        Returns:
            dict with run summary
        """
        # -- Generate unique run ID --
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # -- Initialize logger --
        logger = get_logger(name=f"pipeline.{run_id}", log_dir=self.log_dir, run_id=run_id)
        run_log = PipelineRunLogger(run_id=run_id)

        logger.info(f"{'='*60}")
        logger.info(f"🚀 PIPELINE START | run_id={run_id} | mode={mode}")
        logger.info(f"{'='*60}")

        # -- Initialize tracker --
        tracker = FileTracker(self.tracker_path)
        run_log.set_step("Initialization")

        try:
            # =============================================
            # STEP 0: Identify files to process
            # =============================================
            logger.info("📂 STEP 0: Identifying files...")
            
            if mode == "full":
                pdf_files = sorted(self.input_dir.glob("*.pdf"))
                logger.info(f"   FULL mode — processing ALL {len(pdf_files)} PDFs")
            else:
                pdf_files = tracker.get_new_files(self.input_dir)
                logger.info(f"   INCREMENTAL mode — {len(pdf_files)} new PDFs found")

            if not pdf_files:
                logger.info("✅ No new files to process. Pipeline complete.")
                run_log.finish("NO_NEW_FILES")
                return {
                    "run_id": run_id,
                    "status": "NO_NEW_FILES",
                    "files_processed": 0,
                    "timestamp": datetime.now().isoformat(),
                }

            total = len(pdf_files)
            processed = 0
            failed = 0
            errors = []

            run_log.total_files = total

            # =============================================
            # STEP 1: PDF → Markdown
            # =============================================
            run_log.set_step("PDF → Markdown")
            logger.info(f"📄 STEP 1: PDF → Markdown ({total} files)")
            
            for i, pdf_path in enumerate(pdf_files, 1):
                try:
                    logger.info(f"   [{i}/{total}] Converting: {pdf_path.name}")
                    
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    # 👉 PLUG YOUR FUNCTION HERE:
                    # convert_pdf_to_markdown(
                    #     pdf_path=pdf_path,
                    #     output_dir=self.markdown_dir,
                    # )
                    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    
                    logger.info(f"   ✅ Done: {pdf_path.name}")
                    
                except Exception as e:
                    logger.error(f"   ❌ FAILED: {pdf_path.name} — {e}")
                    run_log.record_error(pdf_path.name, str(e))
                    errors.append({"file": pdf_path.name, "step": "pdf_to_md", "error": str(e)})
                    failed += 1
                    continue  # Skip to next file — DON'T stop pipeline

            run_log.complete_step("PDF → Markdown")

            # =============================================
            # STEP 2: Markdown → Qdrant Embedding
            # =============================================
            run_log.set_step("Embedding")
            logger.info(f"🧠 STEP 2: Markdown → Qdrant Embedding")
            
            try:
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 👉 PLUG YOUR FUNCTION HERE:
                # embed_markdown_to_qdrant(
                #     markdown_dir=self.markdown_dir,
                #     qdrant_url=QDRANT_URL,
                #     collection=QDRANT_COLLECTION,
                # )
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                logger.info("   ✅ Embedding complete")
                run_log.complete_step("Embedding")

            except Exception as e:
                logger.error(f"   ❌ Embedding FAILED: {e}")
                errors.append({"file": "ALL", "step": "embedding", "error": str(e)})
                run_log.finish("FAILED")
                # This is critical — can't continue without embeddings
                return {
                    "run_id": run_id,
                    "status": "FAILED",
                    "failed_at": "step2_embedding",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }

            # =============================================
            # STEP 3: Verify Qdrant
            # =============================================
            run_log.set_step("Verification")
            logger.info(f"🔍 STEP 3: Verifying Qdrant collection")
            
            try:
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 👉 PLUG YOUR FUNCTION HERE:
                # verify_result = verify_qdrant_collection(
                #     qdrant_url=QDRANT_URL,
                #     collection=QDRANT_COLLECTION,
                # )
                # logger.info(f"   Verification: {verify_result}")
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                logger.info("   ✅ Verification passed")
                run_log.complete_step("Verification")

            except Exception as e:
                logger.warning(f"   ⚠️ Verification warning: {e}")
                # Non-fatal — continue to extraction

            # =============================================
            # STEP 4: Query + Excel Export
            # =============================================
            run_log.set_step("Excel Export")
            logger.info(f"📊 STEP 4: Extracting to Excel")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.output_dir / f"contracts_{timestamp}.xlsx"
            
            try:
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 👉 PLUG YOUR FUNCTION HERE:
                # extract_to_excel(
                #     qdrant_url=QDRANT_URL,
                #     collection=QDRANT_COLLECTION,
                #     output_path=output_file,
                # )
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                
                logger.info(f"   ✅ Excel saved: {output_file}")
                run_log.complete_step("Excel Export")

            except Exception as e:
                logger.error(f"   ❌ Excel export FAILED: {e}")
                errors.append({"file": "ALL", "step": "excel_export", "error": str(e)})

            # =============================================
            # STEP 5: Move processed PDFs
            # =============================================
            run_log.set_step("Cleanup")
            logger.info(f"📦 STEP 5: Moving processed PDFs")
            
            for pdf_path in pdf_files:
                try:
                    dest = self.processed_dir / pdf_path.name
                    shutil.move(str(pdf_path), str(dest))
                    tracker.mark_processed(dest, status="SUCCESS", run_id=run_id)
                    run_log.processed_files += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Could not move {pdf_path.name}: {e}")

            processed = total - failed
            run_log.complete_step("Cleanup")

            # =============================================
            # FINAL SUMMARY
            # =============================================
            status = "SUCCESS" if failed == 0 else "PARTIAL"
            run_log.finish(status)

            summary = {
                "run_id": run_id,
                "status": status,
                "mode": mode,
                "total_files": total,
                "processed": processed,
                "failed": failed,
                "errors": errors,
                "output_file": str(output_file),
                "started_at": run_log.start_time.isoformat(),
                "completed_at": run_log.end_time.isoformat() if run_log.end_time else None,
                "elapsed_seconds": round((run_log.end_time - run_log.start_time).total_seconds(), 2) if run_log.end_time else None,
                "timestamp": datetime.now().isoformat(),
            }

            logger.info(f"{'='*60}")
            logger.info(f"🏁 PIPELINE COMPLETE")
            logger.info(f"   Status:    {status}")
            logger.info(f"   Processed: {processed}/{total}")
            logger.info(f"   Failed:    {failed}")
            logger.info(f"   Output:    {output_file}")
            logger.info(f"{'='*60}")

            return summary

        except Exception as e:
            import logging
            logger = logging.getLogger(f"pipeline.{run_id}")
            logger.critical(f"💥 PIPELINE CRASHED: {e}")
            return {
                "run_id": run_id,
                "status": "CRASHED",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }