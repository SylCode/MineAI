"""
skills/building.py – simple prefab structure helpers.

Provides a `build_shelter` skill that places a minimal 5×3×5 dirt/cobblestone
box around the bot's current position – useful for surviving the first night.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mineai.bot_client import BotClient

log = logging.getLogger("mineai.skills.building")


async def place_block_safe(
    client: "BotClient",
    x: int, y: int, z: int,
) -> bool:
    r = await client.send_action("place_block", {
        "x": x, "y": y, "z": z,
        "face_x": 0, "face_y": 1, "face_z": 0,
    })
    return r.get("success", False)


async def build_shelter(
    client: "BotClient",
    state: dict[str, Any],
    material: str = "cobblestone",
) -> bool:
    """
    Build a minimal 5×4×5 closed shelter centred on the bot's position.
    The bot must have enough `material` blocks in inventory.

    Returns True if at least partially successful.
    """
    pos = state.get("position")
    if not pos:
        return False

    cx, cy, cz = pos["x"], pos["y"], pos["z"]
    placed = 0

    # Equip material
    await client.send_action("equip", {"item_name": material})

    # Floor + walls (skip air / interior volume)
    for dy in range(0, 4):         # 4 blocks tall
        for dx in range(-2, 3):    # 5 wide
            for dz in range(-2, 3):
                is_wall = (abs(dx) == 2 or abs(dz) == 2 or dy == 0 or dy == 3)
                if not is_wall:
                    continue      # skip interior
                bx, by, bz = cx + dx, cy + dy, cz + dz
                r = await place_block_safe(client, int(bx), int(by), int(bz))
                if r:
                    placed += 1

    log.info("Shelter built: %d blocks placed", placed)
    return placed > 0
