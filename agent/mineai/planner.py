"""
planner.py – ReAct (Reason + Act) loop.

Each "turn":
  1. Build a prompt from system prompt + long-term facts + recent history
     + current game state + pending chat messages.
  2. Call the LLM.
  3. Parse THINK / ACTIONS from the reply.
  4. Execute each action via the BotClient.
  5. Store the turn in memory.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from mineai.llm.client  import LlamaClient
from mineai.llm.prompts import SYSTEM_PROMPT, build_state_summary
from mineai.memory      import AgentMemory
from mineai.config      import Config

if TYPE_CHECKING:
    from mineai.bot_client import BotClient

log = logging.getLogger("mineai.planner")

# Regex to extract the ACTIONS JSON array from the LLM reply
_ACTIONS_RE = re.compile(r"ACTIONS:\s*(\[.*?\])", re.DOTALL | re.IGNORECASE)
_THINK_RE   = re.compile(r"THINK:\s*(.+?)(?=ACTIONS:|$)", re.DOTALL | re.IGNORECASE)


class ReactPlanner:
    def __init__(self, config: Config, memory: AgentMemory) -> None:
        self._cfg    = config
        self._memory = memory
        self._llm    = LlamaClient(
            base_url    = config.llm_base_url,
            model       = config.llm_model,
            timeout     = config.llm_timeout,
        )
        # Queue of incoming chat messages to process
        self._chat_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._thinking = False   # guard against concurrent think calls

    # ── Event hook ────────────────────────────────────────────────────────────

    async def on_event(self, event: str, data: dict[str, Any], client: "BotClient") -> None:
        if event == "chat":
            await self._chat_queue.put(data)

    # ── Main think/act cycle ──────────────────────────────────────────────────

    async def think(self, state: dict[str, Any], client: "BotClient") -> None:
        if self._thinking:
            return
        self._thinking = True
        try:
            await self._run_turn(state, client)
        except Exception as exc:
            log.error("Planner error: %s", exc, exc_info=True)
        finally:
            self._thinking = False

    async def _run_turn(self, state: dict[str, Any], client: "BotClient") -> None:
        # Collect pending chat messages (non-blocking drain)
        pending_chats: list[dict] = []
        while not self._chat_queue.empty():
            pending_chats.append(self._chat_queue.get_nowait())

        # Build the message list for the LLM
        messages = self._build_messages(state, pending_chats)

        log.info("[Think] goal=%s", self._memory.current_goal)

        try:
            reply = await self._llm.chat(
                messages    = messages,
                max_tokens  = self._cfg.max_tokens,
                temperature = self._cfg.temperature,
                stop        = ["THINK:", "\n\n\n"],
            )
        except RuntimeError as exc:
            log.error("LLM call failed: %s", exc)
            return

        think_text, actions = self._parse_reply(reply)
        if think_text:
            log.info("[Reason] %s", think_text.strip())

        results: list[str] = []
        for action in actions:
            action_name = action.get("action", "")
            params      = action.get("params", {})
            log.info("[Act] %s  params=%s", action_name, params)
            result = await client.send_action(action_name, params)
            ok = result.get("success", False)
            err = result.get("error", "")
            results.append(f"{action_name}: {'OK' if ok else 'FAIL – ' + err}")
            if not ok:
                log.warning("[Act] %s failed: %s", action_name, err)

        self._memory.add_turn(
            observation    = build_state_summary(state),
            actions        = actions,
            result_summary = "; ".join(results) if results else "no actions",
        )

        # Update goal if LLM suggested one (optional heuristic)
        self._maybe_update_goal(think_text, state)

    # ── Prompt construction ───────────────────────────────────────────────────

    def _build_messages(
        self, state: dict[str, Any], chats: list[dict]
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Long-term facts
        facts = self._memory.all_facts()
        if facts:
            facts_text = "\n".join(f"- {k}: {v}" for k, v in list(facts.items())[-20:])
            messages.append({
                "role":    "system",
                "content": f"## What you know (long-term memory)\n{facts_text}",
            })

        # Goal stack
        goals = self._memory.goals_stack()
        messages.append({
            "role":    "system",
            "content": (
                f"## Current goal\n{goals[-1]}\n"
                + (f"## Goal stack\n" + "\n".join(f"  {i}. {g}" for i, g in enumerate(goals)) if len(goals) > 1 else "")
            ),
        })

        # Recent history
        history = self._memory.recent_history(n=self._cfg.max_history)
        for turn in history:
            messages.append({
                "role":    "user",
                "content": (
                    f"### Previous observation\n{turn['observation']}\n"
                    f"### Actions taken\n{json.dumps(turn['actions'], indent=2)}\n"
                    f"### Result\n{turn['result_summary']}"
                ),
            })
            messages.append({
                "role":    "assistant",
                "content": "Understood.",
            })

        # Pending chat messages from players
        if chats:
            chat_text = "\n".join(f"<{c['username']}> {c['message']}" for c in chats)
            messages.append({
                "role":    "user",
                "content": f"## Players said\n{chat_text}",
            })

        # Current state
        messages.append({
            "role":    "user",
            "content": f"## Current game state\n{build_state_summary(state)}\n\nWhat do you do next?",
        })

        return messages

    # ── Reply parsing ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_reply(reply: str) -> tuple[str, list[dict]]:
        think  = ""
        actions: list[dict] = []

        m_think = _THINK_RE.search(reply)
        if m_think:
            think = m_think.group(1).strip()

        m_actions = _ACTIONS_RE.search(reply)
        if m_actions:
            try:
                parsed = json.loads(m_actions.group(1))
                if isinstance(parsed, list):
                    actions = parsed
            except json.JSONDecodeError as exc:
                log.warning("Could not parse ACTIONS JSON: %s\nRaw: %s", exc, m_actions.group(1)[:200])

        return think, actions

    # ── Heuristic goal updating ───────────────────────────────────────────────

    def _maybe_update_goal(self, think: str, state: dict[str, Any]) -> None:
        """Very lightweight triggers – a real agent would derive these from LLM output."""
        health = state.get("health", 20)
        food   = state.get("food",   20)

        if health < 5:
            self._memory.replace_goal("Recover health immediately – find shelter or food.")
        elif food < 6:
            self._memory.replace_goal("Find food – I am starving.")
        elif health < 10:
            if "danger" not in self._memory.current_goal:
                self._memory.push_goal("Escape danger and heal up.")
