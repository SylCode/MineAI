"""
skills/skill_generator.py – asks the LLM to write a new Python skill function.

Triggered by the planner when a goal fails repeatedly (threshold set in config).
The LLM produces a complete `async def run(client, state)` function which is
validated, saved, and registered in the SkillLibrary.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mineai.llm.client        import LlamaClient
    from mineai.skills.skill_library import SkillLibrary

from mineai.llm.prompts import SKILL_GENERATION_PROMPT

log = logging.getLogger("mineai.skills.generator")

_CODE_RE  = re.compile(r"```python\s*(.*?)```", re.DOTALL)
_NAME_RE  = re.compile(r"SKILL_NAME:\s*(\w+)")
_DESC_RE  = re.compile(r"SKILL_DESC:\s*(.+)")

_SKILL_HEADER = """\
from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from mineai.bot_client import BotClient
log = logging.getLogger("mineai.skills.generated")

"""


class SkillGenerator:
    """Generates and registers new skills via the LLM."""

    def __init__(self, llm: "LlamaClient", library: "SkillLibrary") -> None:
        self._llm     = llm
        self._library = library

    async def generate_and_save(
        self,
        goal: str,
        state: dict[str, Any],
        examples: list[dict] | None = None,
    ) -> dict[str, str] | None:
        """
        Ask the LLM to write a skill that accomplishes `goal`.
        Returns {name, description, code} if saved successfully, else None.
        """
        example_block = ""
        if examples:
            example_block = "Example existing skills for reference:\n" + "\n---\n".join(
                f"# {s['name']}: {s['description']}\n{s['code']}" for s in examples
            ) + "\n\n"

        messages = [
            {"role": "system", "content": SKILL_GENERATION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Goal to accomplish: {goal}\n\n"
                    + example_block
                    + f"Current state: {_fmt_state(state)}"
                ),
            },
        ]

        try:
            reply = await self._llm.chat(messages, max_tokens=900, temperature=0.2)
        except RuntimeError as exc:
            log.error("Skill generation LLM call failed: %s", exc)
            return None

        name_m = _NAME_RE.search(reply)
        desc_m = _DESC_RE.search(reply)
        code_m = _CODE_RE.search(reply)

        if not (name_m and desc_m and code_m):
            log.warning("Could not parse skill output:\n%s", reply[:400])
            return None

        name = name_m.group(1).strip()
        desc = desc_m.group(1).strip()
        code = code_m.group(1).strip()

        # Inject standard imports if the LLM omitted them
        if "from __future__" not in code:
            code = _SKILL_HEADER + code

        if not self._library.add_skill(name, desc, code):
            return None

        log.info("Generated and saved new skill: '%s'", name)
        return {"name": name, "description": desc, "code": code}


def _fmt_state(state: dict[str, Any]) -> str:
    pos     = state.get("position") or {}
    inv     = state.get("inventory") or []
    inv_str = ", ".join(f"{i['name']}×{i['count']}" for i in inv) or "empty"
    return (
        f"pos=({pos.get('x','?')},{pos.get('y','?')},{pos.get('z','?')}) "
        f"health={state.get('health','?')} food={state.get('food','?')} "
        f"inv=[{inv_str}]"
    )
