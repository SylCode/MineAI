"""
skills/farming.py – plant and harvest basic crops.

Assumes a flat 3×3 or larger farm plot already exists.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mineai.bot_client import BotClient

log = logging.getLogger("mineai.skills.farming")

CROPS: dict[str, dict] = {
    "wheat":    {"seed": "wheat_seeds",   "block": "wheat",    "max_age": 7},
    "carrot":   {"seed": "carrot",        "block": "carrots",  "max_age": 7},
    "potato":   {"seed": "potato",        "block": "potatoes", "max_age": 7},
    "beetroot": {"seed": "beetroot_seeds","block": "beetroots","max_age": 3},
}


async def harvest_crops(
    client: "BotClient",
    state: dict[str, Any],
) -> int:
    """
    Harvest any fully grown crop blocks visible in the current state.
    Returns number of harvest actions attempted.
    """
    interesting = state.get("interestingBlocks", [])
    targets = [
        b for b in interesting
        if any(info["block"] in b["name"] for info in CROPS.values())
    ]
    count = 0
    for block in targets:
        bp = block["position"]
        # Navigate next to the crop
        await client.send_action("move_to", {"x": bp["x"], "y": bp["y"], "z": bp["z"], "range": 2})
        # Mine (break) the crop to harvest
        r = await client.send_action("mine_block", bp)
        if r.get("success"):
            log.info("Harvested %s at %s", block["name"], bp)
            count += 1
    return count


async def plant_seeds(
    client: "BotClient",
    state: dict[str, Any],
    crop: str = "wheat",
) -> int:
    """
    Equip seeds and plant them on farmland blocks nearby.
    Returns number of blocks planted.
    """
    info = CROPS.get(crop)
    if not info:
        log.warning("Unknown crop: %s", crop)
        return 0

    seed_name = info["seed"]
    inv = {i["name"]: i["count"] for i in state.get("inventory", [])}
    if seed_name not in inv or inv[seed_name] == 0:
        log.info("No %s in inventory", seed_name)
        return 0

    await client.send_action("equip", {"item_name": seed_name})

    # Find farmland blocks nearby
    farmland = [
        b for b in state.get("interestingBlocks", [])
        if "farmland" in b["name"]
    ]
    planted = 0
    for block in farmland[:16]:
        bp = block["position"]
        await client.send_action("move_to", {"x": bp["x"], "y": bp["y"], "z": bp["z"], "range": 2})
        # Place seed on top of farmland block
        r = await client.send_action("place_block", {
            "x": bp["x"], "y": bp["y"], "z": bp["z"],
            "face_x": 0, "face_y": 1, "face_z": 0,
        })
        if r.get("success"):
            planted += 1
    return planted
