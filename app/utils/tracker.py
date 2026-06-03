"""
IHCL Contract Pipeline — File Tracker
=======================================
Tracks which PDFs have already been processed.
Enables incremental runs — only new files get processed.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional


class FileTracker:
    """
    Maintains a JSON log of processed files.
    Uses file hash (MD5) + filename to detect duplicates.
    """

    def __init__(self, tracker_path: Path):
        self.tracker_path = Path(tracker_path)
        self._data: dict = self._load()

    def _load(self) -> dict:
        """Load existing tracker or create empty one."""
        if self.tracker_path.exists():
            with open(self.tracker_path, "r") as f:
                return json.load(f)
        return {"processed_files": {}, "last_updated": None}

    def _save(self):
        """Persist tracker to disk."""
        self._data["last_updated"] = datetime.now().isoformat()
        with open(self.tracker_path, "w") as f:
            json.dump(self._data, f, indent=2)

    @staticmethod
    def _file_hash(file_path: Path) -> str:
        """Compute MD5 hash of a file for dedup."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def is_processed(self, file_path: Path) -> bool:
        """Check if file has already been processed."""
        file_key = file_path.name
        if file_key not in self._data["processed_files"]:
            return False
        # Also verify hash matches (same name, different content = reprocess)
        stored_hash = self._data["processed_files"][file_key].get("hash")
        current_hash = self._file_hash(file_path)
        return stored_hash == current_hash

    def mark_processed(
        self,
        file_path: Path,
        status: str = "SUCCESS",
        run_id: str = None,
        error: Optional[str] = None,
    ):
        """Record a file as processed."""
        self._data["processed_files"][file_path.name] = {
            "hash": self._file_hash(file_path),
            "status": status,
            "run_id": run_id,
            "processed_at": datetime.now().isoformat(),
            "error": error,
        }
        self._save()

    def get_new_files(self, input_dir: Path) -> list[Path]:
        """Return list of PDF files not yet processed."""
        all_pdfs = sorted(input_dir.glob("*.pdf"))
        return [f for f in all_pdfs if not self.is_processed(f)]

    def get_stats(self) -> dict:
        """Return summary statistics."""
        files = self._data["processed_files"]
        return {
            "total_tracked": len(files),
            "success": sum(1 for f in files.values() if f["status"] == "SUCCESS"),
            "failed": sum(1 for f in files.values() if f["status"] == "FAILED"),
            "last_updated": self._data.get("last_updated"),
        }

    def reset(self):
        """Clear all tracking data (use with caution)."""
        self._data = {"processed_files": {}, "last_updated": None}
        self._save()
