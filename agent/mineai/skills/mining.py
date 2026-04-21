"""
skills/mining.py – strip-mine a vein or collect a specific ore type.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mineai.bot_client import BotClient

log = logging.getLogger("mineai.skills.mining")

ORE_NAMES = [
    "coal_ore", "deepslate_coal_ore",
    "iron_ore", "deepslate_iron_ore",
    "gold_ore", "deepslate_gold_ore",
    "diamond_ore", "deepslate_diamond_ore",
    "emerald_ore", "deepslate_emerald_ore",
    "lapis_ore", "deepslate_lapis_ore",
    "redstone_ore", "deepslate_redstone_ore",
    "copper_ore", "deepslate_copper_ore",
    "nether_quartz_ore", "nether_gold_ore",
    "ancient_debris",
]


async def collect_ore(
    client: "BotClient",
    ore_name: str,
    count: int = 8,
    max_distance: int = 32,
) -> bool:
    """Equip best pickaxe then collect nearby ore."""
    # Equip pickaxe
    for pick in ("netherite_pickaxe", "diamond_pickaxe", "iron_pickaxe",
                 "stone_pickaxe", "wooden_pickaxe"):
        r = await client.send_action("equip", {"item_name": pick})
        if r.get("success"):
            log.info("Equipped %s", pick)
            break

    result = await client.send_action("collect_block", {
        "block_name":   ore_name,
        "count":        count,
        "max_distance": max_distance,
    })
    return result.get("success", False)


async def collect_nearest_ore(
    client: "BotClient",
    state: dict[str, Any],
    preferred_tier: str = "iron",
) -> bool:
    """Mine the nearest ore of at least the preferred tier."""
    tier_order = ["diamond", "emerald", "gold", "iron", "lapis", "redstone",
                  "copper", "coal", "quartz"]
    start = max(0, tier_order.index(preferred_tier) if preferred_tier in tier_order else 0)

    for tier in tier_order[start:]:
        for ore in [o for o in ORE_NAMES if tier in o]:
            r = await collect_ore(client, ore, count=4)
            if r:
                return True
    return False
