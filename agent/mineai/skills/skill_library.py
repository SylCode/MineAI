"""
skills/skill_library.py – ChromaDB-backed, ever-growing skill library.

Skills are Python async functions with signature:
    async def run(client: BotClient, state: dict) -> bool

They are stored with a natural-language description used for embedding-based
retrieval.  Generated skill source files live in agent/mineai/skills/generated/.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("mineai.skills.library")

_DEFAULT_GENERATED_DIR = Path(__file__).parent / "generated"
_DEFAULT_CHROMA_DIR    = Path("data/skill_chroma")


class SkillLibrary:
    """Persistent, embedding-indexed store of reusable Minecraft skills."""

    def __init__(
        self,
        generated_dir: Path | str = _DEFAULT_GENERATED_DIR,
        chroma_dir:    Path | str = _DEFAULT_CHROMA_DIR,
    ) -> None:
        self._generated_dir = Path(generated_dir)
        self._generated_dir.mkdir(parents=True, exist_ok=True)
        _ensure_init(self._generated_dir)

        chroma_dir = Path(chroma_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)

        try:
            import chromadb
            self._chroma = chromadb.PersistentClient(path=str(chroma_dir))
            self._collection = self._chroma.get_or_create_collection("skills")
            self._available = True
            log.info("Skill library loaded: %d skills", self._collection.count())
        except ImportError:
            log.warning("chromadb not installed – skill library will run in-memory only")
            self._available  = False
            self._mem_store: list[dict[str, str]] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def add_skill(self, name: str, description: str, code: str) -> bool:
        """Validate, save to disk, and register a new skill. Returns True on success."""
        if not _validate_skill_code(name, code):
            return False

        skill_file = self._generated_dir / f"{name}.py"
        skill_file.write_text(code, encoding="utf-8")

        if self._available:
            self._collection.upsert(
                ids=[name],
                documents=[description],
                metadatas=[{"name": name, "code": code}],
            )
        else:
            # In-memory fallback
            self._mem_store = [s for s in self._mem_store if s["name"] != name]
            self._mem_store.append({"name": name, "description": description, "code": code})

        log.info("Skill '%s' added to library", name)
        return True

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Return the top_k most semantically relevant skills for the query."""
        if self._available:
            count = self._collection.count()
            if count == 0:
                return []
            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, count),
            )
            return [
                {
                    "name":        results["metadatas"][0][i]["name"],
                    "description": doc,
                    "code":        results["metadatas"][0][i]["code"],
                }
                for i, doc in enumerate(results["documents"][0])
            ]
        else:
            # Fallback: return first top_k (no semantic ranking)
            return self._mem_store[:top_k]

    async def execute(self, name: str, client: Any, state: dict[str, Any]) -> bool:
        """Dynamically load and run a generated skill by name."""
        skill_file = self._generated_dir / f"{name}.py"
        if not skill_file.exists():
            log.warning("Skill file not found: %s", skill_file)
            return False

        spec   = importlib.util.spec_from_file_location(
            f"mineai.skills.generated.{name}", skill_file
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "run"):
            log.warning("Skill %s has no `run` function", name)
            return False

        return await module.run(client, state)

    def list_all(self) -> list[dict[str, str]]:
        """Return name + description of every stored skill."""
        if self._available:
            if self._collection.count() == 0:
                return []
            data = self._collection.get()
            return [
                {"name": m["name"], "description": doc}
                for m, doc in zip(data["metadatas"], data["documents"])
            ]
        return [{"name": s["name"], "description": s["description"]} for s in self._mem_store]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_skill_code(name: str, code: str) -> bool:
    """Check that code is valid Python and contains `async def run`."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        log.warning("Skill '%s' rejected – syntax error: %s", name, exc)
        return False

    has_run = any(
        isinstance(node, ast.AsyncFunctionDef) and node.name == "run"
        for node in ast.walk(tree)
    )
    if not has_run:
        log.warning("Skill '%s' rejected – missing `async def run(client, state)`", name)
        return False

    return True


def _ensure_init(directory: Path) -> None:
    init = directory / "__init__.py"
    if not init.exists():
        init.write_text("")
