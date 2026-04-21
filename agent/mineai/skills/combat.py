"""
skills/combat.py – engage hostile mobs and handle retreat.
"""

from __future__ import annotations
import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mineai.bot_client import BotClient

log = logging.getLogger("mineai.skills.combat")

HOSTILE_MOBS = {
    "zombie", "skeleton", "spider", "cave_spider", "creeper", "witch",
    "pillager", "vindicator", "phantom", "drowned", "husk", "stray",
    "blaze", "ghast", "magma_cube", "slime", "enderman",
}

RETREAT_HEALTH_THRESHOLD = 6


async def engage_nearest_hostile(
    client: "BotClient",
    state: dict[str, Any],
    retreat_health: int = RETREAT_HEALTH_THRESHOLD,
) -> bool:
    """
    Find the nearest hostile mob and attack it.
    Retreats if health drops below `retreat_health`.
    Returns True if combat was initiated.
    """
    health = state.get("health", 20)
    if health <= retreat_health:
        log.info("Health too low (%s) – retreating instead of fighting", health)
        await _retreat(client, state)
        return False

    entities = state.get("nearbyEntities", [])
    hostiles = [e for e in entities if e.get("name", "").lower() in HOSTILE_MOBS]
    if not hostiles:
        return False

    # Target the closest hostile
    pos = state.get("position", {})
    px, py, pz = pos.get("x", 0), pos.get("y", 0), pos.get("z", 0)
    hostiles.sort(key=lambda e: (
        (e["position"]["x"] - px) ** 2
        + (e["position"]["y"] - py) ** 2
        + (e["position"]["z"] - pz) ** 2
    ))
    target = hostiles[0]

    # Equip best sword / axe
    for weapon in ("netherite_sword", "diamond_sword", "iron_sword",
                   "stone_sword", "wooden_sword",
                   "netherite_axe", "diamond_axe", "iron_axe"):
        r = await client.send_action("equip", {"item_name": weapon})
        if r.get("success"):
            log.info("Equipped %s for combat", weapon)
            break

    log.info("Attacking %s (id=%s)", target["name"], target["id"])
    await client.send_action("attack", {"entity_id": target["id"]})
    return True


async def stop_combat(client: "BotClient") -> None:
    await client.send_action("stop_attack", {})
    await client.send_action("stop_moving", {})


async def _retreat(client: "BotClient", state: dict[str, Any]) -> None:
    """Run away from the nearest hostile mob."""
    pos = state.get("position", {})
    entities = state.get("nearbyEntities", [])
    hostiles = [e for e in entities if e.get("name", "").lower() in HOSTILE_MOBS]
    if not hostiles or not pos:
        return
    threat = hostiles[0]["position"]
    # Move in the opposite direction (approx)
    rx = pos["x"] + (pos["x"] - threat["x"]) * 2
    rz = pos["z"] + (pos["z"] - threat["z"]) * 2
    await client.send_action("stop_attack", {})
    await client.send_action("move_to", {"x": int(rx), "y": pos["y"], "z": int(rz), "range": 1})
    log.info("Retreating to (%d, %d, %d)", int(rx), pos["y"], int(rz))
