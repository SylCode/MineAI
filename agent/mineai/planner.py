"""
planner.py – Voyager-inspired ReAct loop with:
  1. Automatic curriculum   – LLM proposes the next task every N cycles
  2. Skill library          – ChromaDB-indexed, ever-growing reusable skills
  3. Critic / verification  – post-action LLM check with retry (up to max_retries)
  4. Skill generation       – LLM writes new Python skills when a goal fails repeatedly

Each turn:
  1. [Curriculum] every N cycles → push a new goal from the LLM
  2. [Retrieval]  fetch top-k relevant skills from the library
  3. [ReAct]      LLM produces THINK + ACTIONS (with skill context in prompt)
  4. [Execute]    run actions via BotClient
  5. [Critic]     verify success; retry up to max_retries on failure
  6. [Memory]     record turn; record achievement on success
  7. [Generate]   if goal failed skill_fail_threshold times, generate a new skill
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from mineai.llm.client   import LlamaClient
from mineai.llm.prompts  import (
    SYSTEM_PROMPT, CRITIC_PROMPT, build_state_summary,
)
from mineai.memory       import AgentMemory
from mineai.config       import Config
from mineai.curriculum   import CurriculumGenerator
from mineai.skills.skill_library   import SkillLibrary
from mineai.skills.skill_generator import SkillGenerator

if TYPE_CHECKING:
    from mineai.bot_client import BotClient

log = logging.getLogger("mineai.planner")

_ACTIONS_RE = re.compile(r"ACTIONS:\s*(\[.*?\])", re.DOTALL | re.IGNORECASE)
_THINK_RE   = re.compile(r"THINK:\s*(.+?)(?=ACTIONS:|$)", re.DOTALL | re.IGNORECASE)
_SUCCESS_RE = re.compile(r"SUCCESS:\s*(true|false)", re.IGNORECASE)
_HINT_RE    = re.compile(r"RETRY_HINT:\s*(.+)", re.IGNORECASE)


class ReactPlanner:
    def __init__(self, config: Config, memory: AgentMemory) -> None:
        self._cfg    = config
        self._memory = memory

        # Fast local LLM – used every think cycle for ReAct
        self._llm = LlamaClient(
            base_url = config.llm_base_url,
            model    = config.llm_model,
            timeout  = config.llm_timeout,
            api_key  = config.llm_api_key,
        )

        # Strong LLM – used for curriculum, critic, skill generation.
        # Falls back to the local LLM when STRONG_LLM_BASE_URL is not set.
        self._strong_llm = LlamaClient(
            base_url = config.strong_llm_effective_url,
            model    = config.strong_llm_effective_model,
            timeout  = config.strong_llm_timeout,
            api_key  = config.strong_llm_effective_key,
        )
        if config.strong_llm_base_url:
            log.info("Strong LLM: %s  model=%s", config.strong_llm_effective_url, config.strong_llm_effective_model)
        else:
            log.info("Strong LLM: using same local endpoint as ReAct LLM")

        # Voyager components
        self._skill_library = SkillLibrary(
            chroma_dir=config.skill_chroma_path,
        )
        self._skill_gen   = SkillGenerator(self._strong_llm, self._skill_library)
        self._curriculum  = CurriculumGenerator(self._strong_llm, self._memory)

        # Internal state
        self._chat_queue:    asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._thinking:      bool = False
        self._think_count:   int  = 0
        self._goal_fails:    int  = 0   # consecutive failures for current goal

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
        self._think_count += 1

        # ── 1. Curriculum ────────────────────────────────────────────────────
        if self._think_count % self._cfg.curriculum_interval == 0:
            new_task = await self._curriculum.propose_next_task(state)
            if new_task:
                self._memory.push_goal(new_task)
                self._goal_fails = 0

        goal = self._memory.current_goal
        log.info("[Think #%d] goal=%s", self._think_count, goal)

        # ── 2. Drain chat queue ──────────────────────────────────────────────
        pending_chats: list[dict] = []
        while not self._chat_queue.empty():
            pending_chats.append(self._chat_queue.get_nowait())

        # ── 3. Retrieve relevant skills ──────────────────────────────────────
        relevant_skills = self._skill_library.retrieve(goal, top_k=self._cfg.skill_top_k)
        if relevant_skills:
            log.debug("Retrieved %d skills: %s", len(relevant_skills),
                      [s["name"] for s in relevant_skills])

        # ── 4–5. ReAct + Critic loop ─────────────────────────────────────────
        messages   = self._build_messages(state, pending_chats, relevant_skills)
        think_text = ""
        actions:    list[dict] = []
        results:    list[str]  = []
        post_state  = state
        succeeded   = False

        for attempt in range(self._cfg.max_retries + 1):
            # LLM call
            try:
                reply = await self._llm.chat(
                    messages    = messages,
                    max_tokens  = self._cfg.max_tokens,
                    temperature = self._cfg.temperature,
                    stop        = ["THINK:", "\n\n\n"],
                )
            except RuntimeError as exc:
                log.error("LLM call failed: %s", exc)
                break

            think_text, actions = self._parse_reply(reply)
            if think_text:
                log.info("[Reason] %s", think_text.strip())

            # Execute actions
            results = []
            for action in actions:
                action_name = action.get("action", "")
                params      = action.get("params", {})
                log.info("[Act] %s  %s", action_name, params)
                result = await client.send_action(action_name, params)
                ok  = result.get("success", False)
                err = result.get("error", "")
                results.append(f"{action_name}: {'OK' if ok else 'FAIL – ' + err}")
                if not ok:
                    log.warning("[Act] %s failed: %s", action_name, err)

            # Fetch updated game state for the critic
            state_result = await client.send_action("get_state", {})
            post_state   = state_result.get("data") or state

            # No actions taken → skip critic
            if not actions:
                succeeded = True
                break

            # ── Critic ───────────────────────────────────────────────────────
            succeeded, hint = await self._critic_check(state, post_state, actions, goal)

            if succeeded:
                log.info("[Critic] ✓ Goal progressed")
                break

            if attempt < self._cfg.max_retries:
                log.info("[Critic] ✗ Retry %d/%d – %s", attempt + 1, self._cfg.max_retries, hint)
                # Feed critic feedback back into the conversation
                messages.append({"role": "assistant", "content": reply})
                messages.append({
                    "role":    "user",
                    "content": (
                        f"That didn't work. Critic feedback: {hint}\n"
                        f"Updated state:\n{build_state_summary(post_state)}\n"
                        "Try a different approach."
                    ),
                })
                state = post_state   # use updated state for next attempt

        # ── 6. Memory ────────────────────────────────────────────────────────
        self._memory.add_turn(
            observation    = build_state_summary(state),
            actions        = actions,
            result_summary = "; ".join(results) if results else "no actions",
        )

        if succeeded:
            self._goal_fails = 0
            self._maybe_record_achievement(goal, post_state)
        else:
            self._goal_fails += 1

        # ── 7. Skill generation when goal fails repeatedly ───────────────────
        if self._goal_fails >= self._cfg.skill_fail_threshold:
            log.info("[SkillGen] Goal failed %d times – asking LLM to write a skill",
                     self._goal_fails)
            examples = self._skill_library.retrieve(goal, top_k=2)
            await self._skill_gen.generate_and_save(goal, post_state, examples)
            self._goal_fails = 0   # reset regardless of generation success

        # Heuristic survival goal switching
        self._maybe_update_goal(think_text, post_state)

    # ── Critic ────────────────────────────────────────────────────────────────

    async def _critic_check(
        self,
        pre:     dict[str, Any],
        post:    dict[str, Any],
        actions: list[dict],
        goal:    str,
    ) -> tuple[bool, str]:
        """
        Ask the LLM whether the actions made progress toward the goal.
        Returns (success: bool, retry_hint: str).
        """
        messages = [
            {"role": "system", "content": CRITIC_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Goal: {goal}\n"
                    f"Actions taken: {json.dumps(actions)}\n"
                    f"Before:\n{build_state_summary(pre)}\n"
                    f"After:\n{build_state_summary(post)}"
                ),
            },
        ]
        try:
            reply = await self._strong_llm.chat(messages, max_tokens=150, temperature=0.1)
        except RuntimeError as exc:
            log.warning("Critic LLM call failed: %s – assuming success", exc)
            return True, "none"

        m_success = _SUCCESS_RE.search(reply)
        m_hint    = _HINT_RE.search(reply)

        success = m_success.group(1).lower() == "true" if m_success else True
        hint    = m_hint.group(1).strip() if m_hint else "Try a different approach."
        return success, hint

    # ── Achievement recording ─────────────────────────────────────────────────

    def _maybe_record_achievement(self, goal: str, state: dict[str, Any]) -> None:
        achievements: list[str] = self._memory.recall("achievements", [])
        if goal not in achievements:
            achievements.append(goal)
            self._memory.remember("achievements", achievements)
            log.info("[Achievement] %s", goal)

    # ── Prompt construction ───────────────────────────────────────────────────

    def _build_messages(
        self,
        state:            dict[str, Any],
        chats:            list[dict],
        retrieved_skills: list[dict] | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Long-term facts
        facts = self._memory.all_facts()
        if facts:
            # Exclude bookkeeping keys; show last 20
            display = {k: v for k, v in facts.items() if k != "achievements"}
            if display:
                facts_text = "\n".join(f"- {k}: {v}" for k, v in list(display.items())[-20:])
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
                + (
                    "## Goal stack\n"
                    + "\n".join(f"  {i}. {g}" for i, g in enumerate(goals))
                    if len(goals) > 1 else ""
                )
            ),
        })

        # Retrieved skill library snippets
        if retrieved_skills:
            skill_text = "\n\n".join(
                f"### Skill: {s['name']}\n# {s['description']}\n{s['code']}"
                for s in retrieved_skills
            )
            messages.append({
                "role":    "system",
                "content": (
                    "## Relevant skills from your library (call via execute_skill or adapt inline)\n"
                    + skill_text
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
            messages.append({"role": "assistant", "content": "Understood."})

        # Pending player chat
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
        think:   str        = ""
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
                log.warning("Could not parse ACTIONS JSON: %s", exc)

        return think, actions

    # ── Heuristic survival goal switching ────────────────────────────────────

    def _maybe_update_goal(self, think: str, state: dict[str, Any]) -> None:
        health = state.get("health", 20)
        food   = state.get("food",   20)

        if health < 5:
            self._memory.replace_goal("Recover health immediately – find shelter or food.")
        elif food < 6:
            self._memory.replace_goal("Find food – I am starving.")
        elif health < 10:
            if "danger" not in self._memory.current_goal:
                self._memory.push_goal("Escape danger and heal up.")

