"""
curriculum.py – automatic curriculum generator (Voyager-inspired).

Every N think cycles, proposes the next concrete short-term task based on:
  - Current inventory and game state
  - Completed achievements stored in long-term memory
  - Loose Minecraft tech-tree heuristics baked into the prompt

The curriculum does NOT replace the goal stack – it pushes a new goal
that the planner will pursue until completed or superseded.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mineai.llm.client import LlamaClient
    from mineai.memory     import AgentMemory

from mineai.llm.prompts import CURRICULUM_PROMPT

log = logging.getLogger("mineai.curriculum")

_TASK_RE   = re.compile(r"TASK:\s*(.+)",   re.IGNORECASE)
_REASON_RE = re.compile(r"REASON:\s*(.+)", re.IGNORECASE)


class CurriculumGenerator:
    """Proposes the next achievable milestone by querying the LLM."""

    def __init__(self, llm: "LlamaClient", memory: "AgentMemory") -> None:
        self._llm    = llm
        self._memory = memory

    async def propose_next_task(self, state: dict[str, Any]) -> str | None:
        """
        Returns a concrete task string such as
        "Craft a stone pickaxe using 3 cobblestone and 2 sticks"
        or None if no change is warranted.
        """
        inv          = {i["name"]: i["count"] for i in state.get("inventory", [])}
        health       = state.get("health", 20)
        food         = state.get("food",   20)
        time_of_day  = state.get("time",   0)
        achievements = self._memory.recall("achievements", [])
        current_goal = self._memory.current_goal

        messages = [
            {"role": "system", "content": CURRICULUM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Current goal: {current_goal}\n"
                    f"Health: {health}/20  Food: {food}/20  Time: {time_of_day}\n"
                    f"Inventory: {_fmt_inv(inv)}\n"
                    f"Completed achievements: "
                    + (", ".join(achievements) if achievements else "none")
                    + "\n\nWhat should I do next?"
                ),
            },
        ]

        try:
            reply = await self._llm.chat(messages, max_tokens=200, temperature=0.2)
        except RuntimeError as exc:
            log.error("Curriculum LLM call failed: %s", exc)
            return None

        task_m   = _TASK_RE.search(reply)
        reason_m = _REASON_RE.search(reply)

        if not task_m:
            log.debug("Curriculum gave no parseable task:\n%s", reply[:200])
            return None

        task   = task_m.group(1).strip()
        reason = reason_m.group(1).strip() if reason_m else ""

        if reason:
            log.info("[Curriculum] %s  (reason: %s)", task, reason)
        else:
            log.info("[Curriculum] %s", task)

        return task


def _fmt_inv(inv: dict[str, int]) -> str:
    return ", ".join(f"{k}×{v}" for k, v in inv.items()) or "empty"
