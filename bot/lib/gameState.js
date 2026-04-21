/**
 * gameState.js – snapshot the current bot state into a plain JSON object
 * to send to the Python agent.
 */

"use strict";

/**
 * @param {import('mineflayer').Bot} bot
 * @returns {object}
 */
function buildGameState(bot) {
  const pos = bot.entity?.position;

  // Nearby entities (within 32 blocks)
  const nearbyEntities = Object.values(bot.entities)
    .filter((e) => e !== bot.entity && e.position?.distanceTo(bot.entity.position) < 32)
    .map((e) => ({
      id:       e.id,
      type:     e.type,
      name:     e.name || e.username || e.displayName || e.type,
      position: { x: Math.round(e.position.x), y: Math.round(e.position.y), z: Math.round(e.position.z) },
      health:   e.metadata?.[9] ?? null,
    }))
    .slice(0, 20);

  // Inventory (non-empty slots only)
  const inventory = bot.inventory.items().map((item) => ({
    name:  item.name,
    count: item.count,
    slot:  item.slot,
  }));

  // Nearby blocks of interest within 8 blocks
  const interestingBlocks = [];
  if (pos) {
    const radius = 8;
    for (let dx = -radius; dx <= radius; dx++) {
      for (let dy = -radius; dy <= radius; dy++) {
        for (let dz = -radius; dz <= radius; dz++) {
          const block = bot.blockAt(pos.offset(dx, dy, dz));
          if (block && block.name !== "air" && block.name !== "cave_air" && isInteresting(block.name)) {
            interestingBlocks.push({
              name:     block.name,
              position: { x: Math.round(pos.x + dx), y: Math.round(pos.y + dy), z: Math.round(pos.z + dz) },
            });
          }
        }
      }
    }
  }

  return {
    position:        pos ? { x: Math.round(pos.x), y: Math.round(pos.y), z: Math.round(pos.z) } : null,
    health:          bot.health,
    food:            bot.food,
    saturation:      bot.foodSaturation,
    time:            bot.time?.timeOfDay ?? null,
    weather:         bot.isRaining ? "rain" : "clear",
    biome:           pos ? bot.blockAt(pos)?.biome?.name ?? null : null,
    gameMode:        bot.game?.gameMode ?? null,
    inventory,
    nearbyEntities,
    interestingBlocks: interestingBlocks.slice(0, 30),
  };
}

const INTERESTING_KEYWORDS = [
  "ore", "log", "wood", "chest", "furnace", "crafting", "diamond", "gold",
  "iron", "coal", "emerald", "lapis", "redstone", "netherite", "wheat",
  "carrot", "potato", "beetroot", "melon", "pumpkin", "sugar_cane",
  "flower", "mushroom", "sand", "gravel", "clay", "water", "lava",
  "mob_spawner", "portal", "anvil", "enchanting", "bed", "door", "gate",
];

function isInteresting(name) {
  return INTERESTING_KEYWORDS.some((k) => name.includes(k));
}

module.exports = buildGameState;
