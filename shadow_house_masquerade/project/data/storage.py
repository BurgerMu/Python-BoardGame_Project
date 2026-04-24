"""
data/storage.py
----------------
JSON-file-based persistence layer.

Three things are persisted to disk, each in its own file under a data
directory (by default ``~/.shadow_house_masquerade``):

    * stats.json    — aggregated player statistics across all games
    * history.json  — rolling log of the last 50 completed games
    * save.json     — single slot for a suspended game

Deliberately simple: no database, no ORM — just the standard-library
``json`` module. Every read is defensive (returns a sensible default on
corruption) so the GUI never crashes over a malformed file.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Default data directory
# ---------------------------------------------------------------------------
DEFAULT_DATA_DIR = os.path.join(
    os.path.expanduser("~"), ".shadow_house_masquerade"
)
STATS_FILE = "stats.json"
HISTORY_FILE = "history.json"
SAVE_FILE = "save.json"
HISTORY_MAX = 50


class Storage:
    """Facade over JSON file reads/writes for the whole app."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        try:
            os.makedirs(self.data_dir, exist_ok=True)
        except OSError as exc:  # pragma: no cover - would mean an unwritable home
            raise RuntimeError(
                f"Unable to create data directory {self.data_dir!r}: {exc}"
            )

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------
    def _path(self, filename: str) -> str:
        return os.path.join(self.data_dir, filename)

    def _read_json(self, filename: str, default: Any) -> Any:
        path = self._path(filename)
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # File exists but is unreadable; keep the game playable.
            return default

    def _write_json(self, filename: str, data: Any) -> bool:
        path = self._path(filename)
        try:
            # Write-then-rename makes concurrent reads safe-ish.
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Player statistics
    # ------------------------------------------------------------------
    def load_stats(self) -> Dict[str, Dict[str, Any]]:
        """Return {player_name: {"games": int, "wins": int, "total_points": int}}."""
        data = self._read_json(STATS_FILE, {})
        return data if isinstance(data, dict) else {}

    def update_player_stats(
        self, name: str, won_game: bool, round_points: int
    ) -> None:
        """Record one game-end for a single player."""
        stats = self.load_stats()
        entry = stats.setdefault(
            name, {"games": 0, "wins": 0, "total_points": 0}
        )
        entry["games"] = int(entry.get("games", 0)) + 1
        if won_game:
            entry["wins"] = int(entry.get("wins", 0)) + 1
        entry["total_points"] = int(entry.get("total_points", 0)) + int(round_points)
        self._write_json(STATS_FILE, stats)

    def clear_stats(self) -> bool:
        return self._write_json(STATS_FILE, {})

    # ------------------------------------------------------------------
    # Game history
    # ------------------------------------------------------------------
    def load_history(self) -> List[Dict[str, Any]]:
        data = self._read_json(HISTORY_FILE, [])
        return data if isinstance(data, list) else []

    def append_history(self, record: Dict[str, Any]) -> None:
        history = self.load_history()
        record = dict(record)  # shallow copy — don't mutate caller's dict
        record["timestamp"] = datetime.now().isoformat(timespec="seconds")
        history.append(record)
        history = history[-HISTORY_MAX:]
        self._write_json(HISTORY_FILE, history)

    # ------------------------------------------------------------------
    # Save / resume  (single slot)
    # ------------------------------------------------------------------
    def save_game(self, state: Dict[str, Any]) -> bool:
        return self._write_json(SAVE_FILE, state)

    def load_save(self) -> Optional[Dict[str, Any]]:
        return self._read_json(SAVE_FILE, None)

    def has_save(self) -> bool:
        return os.path.exists(self._path(SAVE_FILE))

    def delete_save(self) -> None:
        path = self._path(SAVE_FILE)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
