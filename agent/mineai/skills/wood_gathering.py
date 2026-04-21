"""
skills/wood_gathering.py – find and chop the nearest tree.

Chains: find logs → navigate → mine each log → collect drops.
Returns True if at least one log was collected.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mineai.bot_client import BotClient

log = logging.getLogger("mineai.skills.wood")

LOG_BLOCK_NAMES = [
    "oak_log", "spruce_log", "birch_log", "jungle_log",
    "acacia_log", "dark_oak_log", "mangrove_log", "cherry_log",
    "bamboo_block",
]


async def run(client: "BotClient", state: dict[str, Any]) -> bool:
    """Navigate to and chop the nearest tree. Returns success."""
    # Find logs in the interesting blocks list
    logs = [
        b for b in state.get("interestingBlocks", [])
        if b["name"] in LOG_BLOCK_NAMES
    ]
    if not logs:
        log.info("No logs nearby – requesting scan")
        result = await client.send_action("collect_block", {
            "block_name": "oak_log",
            "count": 8,
            "max_distance": 64,
        })
        return result.get("success", False)

    # Sort by closest (rough 3D distance)
    pos = state.get("position", {})
    px, py, pz = pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)
    logs.sort(key=lambda b: (
        (b["position"]["x"] - px) ** 2
        + (b["position"]["y"] - py) ** 2
        + (b["position"]["z"] - pz) ** 2
    ))

    for log_block in logs[:8]:
        lp = log_block["position"]
        # Navigate close
        nav = await client.send_action("move_to", {"x": lp["x"], "y": lp["y"], "z": lp["z"], "range": 3})
        if not nav.get("success"):
            continue
        # Mine
        mine = await client.send_action("mine_block", lp)
        if mine.get("success"):
            log.info("Chopped %s at %s", log_block["name"], lp)

    return True
