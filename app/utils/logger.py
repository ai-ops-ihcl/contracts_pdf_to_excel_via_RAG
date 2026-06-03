"""
IHCL Contract Pipeline — Structured Logger
============================================
- Console + File output
- JSON-structured for production parsing
- Per-run log files with timestamps
"""

import logging
import sys
from datetime import datetime
from pathlib import Path


def get_logger(
    name: str = "ihcl_pipeline",
    log_dir: Path = None,
    run_id: str = None,
) -> logging.Logger:
    """
    Create a structured logger with both console and file handlers.
    
    Args:
        name: Logger name
        log_dir: Directory to store log files
        run_id: Unique run identifier for this pipeline execution
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # ---- Formatter ----
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # ---- Console Handler ----
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)
    
    # ---- File Handler (if log_dir provided) ----
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_tag = f"_{run_id}" if run_id else ""
        log_file = log_dir / f"pipeline{run_tag}_{timestamp}.log"
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        
        logger.info(f"Log file: {log_file}")
    
    return logger


class PipelineRunLogger:
    """
    Tracks per-run statistics for the pipeline.
    Useful for the /status endpoint and run history.
    """
    
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.start_time = datetime.now()
        self.end_time = None
        self.status = "RUNNING"  # RUNNING | SUCCESS | FAILED | PARTIAL
        self.current_step = ""
        self.total_files = 0
        self.processed_files = 0
        self.failed_files = 0
        self.skipped_files = 0
        self.errors: list[dict] = []
        self.steps_completed: list[str] = []
    
    def set_step(self, step_name: str):
        self.current_step = step_name
    
    def complete_step(self, step_name: str):
        self.steps_completed.append(step_name)
    
    def record_error(self, file_name: str, error: str):
        self.errors.append({
            "file": file_name,
            "error": str(error),
            "timestamp": datetime.now().isoformat(),
        })
        self.failed_files += 1
    
    def finish(self, status: str = "SUCCESS"):
        self.end_time = datetime.now()
        self.status = status
    
    def to_dict(self) -> dict:
        elapsed = (self.end_time or datetime.now()) - self.start_time
        return {
            "run_id": self.run_id,
            "status": self.status,
            "current_step": self.current_step,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "elapsed_seconds": round(elapsed.total_seconds(), 2),
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "skipped_files": self.skipped_files,
            "steps_completed": self.steps_completed,
            "errors": self.errors[-10:],  # Last 10 errors
        }