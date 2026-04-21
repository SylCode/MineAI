"""
MineAI Agent – entry point.

Connects to the Mineflayer bot via WebSocket and runs a continuous
ReAct (Reason + Act) loop powered by a local llama.cpp server.
"""

import asyncio
import logging
import signal

from rich.logging import RichHandler

from mineai.bot_client import BotClient
from mineai.planner import ReactPlanner
from mineai.memory import AgentMemory
from mineai.config import load_config

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
log = logging.getLogger("mineai")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    cfg = load_config()

    memory  = AgentMemory(save_path=cfg.memory_path)
    planner = ReactPlanner(config=cfg, memory=memory)
    client  = BotClient(
        uri=f"ws://{cfg.bot_host}:{cfg.bot_ws_port}",
        planner=planner,
    )

    loop = asyncio.get_running_loop()

    def _shutdown(*_):
        log.info("Shutting down MineAI agent…")
        loop.create_task(client.close())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    log.info("Connecting to bot at %s:%s…", cfg.bot_host, cfg.bot_ws_port)
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
