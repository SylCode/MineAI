"""
memory.py – simple persistent agent memory.

Short-term:  last N (state, action, result) tuples kept in RAM.
Long-term:   named facts written to a JSON file and loaded on startup.
Goals:       the current goal stack (top = active goal).
"""

from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

log = logging.getLogger("mineai.memory")

MAX_SHORT_TERM = 20


class AgentMemory:
    def __init__(self, save_path: Path | str = "data/memory.json") -> None:
        self._path: Path = Path(save_path)

        # Short-term: ring buffer of recent turns
        self._history: deque[dict[str, Any]] = deque(maxlen=MAX_SHORT_TERM)

        # Long-term: persistent key→value facts
        self._facts: dict[str, Any] = {}

        # Goal stack (list, last element = current active goal)
        self._goals: list[str] = ["Survive and explore the world."]

        self._load()

    # ── History ───────────────────────────────────────────────────────────────

    def add_turn(self, observation: str, actions: list[dict], result_summary: str) -> None:
        self._history.append({
            "observation":    observation,
            "actions":        actions,
            "result_summary": result_summary,
        })

    def recent_history(self, n: int = 6) -> list[dict[str, Any]]:
        return list(self._history)[-n:]

    # ── Long-term facts ───────────────────────────────────────────────────────

    def remember(self, key: str, value: Any) -> None:
        self._facts[key] = value
        self._save()
        log.debug("Remembered: %s = %s", key, value)

    def recall(self, key: str, default: Any = None) -> Any:
        return self._facts.get(key, default)

    def all_facts(self) -> dict[str, Any]:
        return dict(self._facts)

    # ── Goals ─────────────────────────────────────────────────────────────────

    @property
    def current_goal(self) -> str:
        return self._goals[-1] if self._goals else "Idle."

    def push_goal(self, goal: str) -> None:
        self._goals.append(goal)
        self._save()
        log.info("New goal: %s", goal)

    def pop_goal(self) -> str | None:
        if len(self._goals) > 1:          # keep at least the root goal
            goal = self._goals.pop()
            self._save()
            log.info("Completed goal: %s  →  now: %s", goal, self.current_goal)
            return goal
        return None

    def replace_goal(self, goal: str) -> None:
        if self._goals:
            self._goals[-1] = goal
        else:
            self._goals.append(goal)
        self._save()

    def goals_stack(self) -> list[str]:
        return list(self._goals)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump({"facts": self._facts, "goals": self._goals}, f, indent=2)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._facts = data.get("facts", {})
            goals = data.get("goals", [])
            if goals:
                self._goals = goals
            log.info("Loaded memory from %s  (%d facts, %d goals)",
                     self._path, len(self._facts), len(self._goals))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not load memory file: %s", exc)
