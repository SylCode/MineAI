/**
 * actions.js – maps action names received from the Python agent to Mineflayer
 * bot method calls.  Every action is async and returns { success, error? }.
 */

"use strict";

const { goals, Movements } = require("mineflayer-pathfinder");
const Vec3 = require("vec3");

/**
 * @param {import('mineflayer').Bot} bot
 * @param {string} action
 * @param {object} params
 * @returns {Promise<{success: boolean, error?: string, data?: object}>}
 */
async function executeAction(bot, action, params) {
  try {
    switch (action) {

      // ── Movement ──────────────────────────────────────────────────────────

      case "move_to": {
        const { x, y, z, range = 1 } = params;
        const goal = new goals.GoalNear(x, y, z, range);
        await bot.pathfinder.goto(goal);
        return { success: true };
      }

      case "follow_entity": {
        const entity = bot.entities[params.entity_id];
        if (!entity) return { success: false, error: "Entity not found" };
        const goal = new goals.GoalFollow(entity, params.range ?? 2);
        bot.pathfinder.setGoal(goal, true);   // dynamic goal
        return { success: true };
      }

      case "stop_moving": {
        bot.pathfinder.setGoal(null);
        return { success: true };
      }

      case "look_at": {
        const { x, y, z } = params;
        await bot.lookAt(new Vec3(x, y, z));
        return { success: true };
      }

      case "jump": {
        bot.setControlState("jump", true);
        await sleep(200);
        bot.setControlState("jump", false);
        return { success: true };
      }

      // ── Mining / collecting ───────────────────────────────────────────────

      case "mine_block": {
        const { x, y, z } = params;
        const block = bot.blockAt(new Vec3(x, y, z));
        if (!block) return { success: false, error: "No block at position" };
        await bot.tool.equipForBlock(block);
        await bot.dig(block);
        return { success: true };
      }

      case "collect_block": {
        // Uses mineflayer-collectblock to navigate + mine
        const blockType = bot.registry.blocksByName[params.block_name];
        if (!blockType) return { success: false, error: `Unknown block: ${params.block_name}` };
        const targets = bot.findBlocks({
          matching:    blockType.id,
          maxDistance: params.max_distance ?? 32,
          count:       params.count ?? 1,
        });
        if (targets.length === 0) return { success: false, error: "No blocks found nearby" };
        const blocks = targets.map((t) => bot.blockAt(t)).filter(Boolean);
        await bot.collectBlock.collect(blocks);
        return { success: true };
      }

      // ── Building / placing ────────────────────────────────────────────────

      case "place_block": {
        const { x, y, z, face_x = 0, face_y = 1, face_z = 0 } = params;
        const refBlock = bot.blockAt(new Vec3(x, y, z));
        if (!refBlock) return { success: false, error: "No reference block" };
        await bot.placeBlock(refBlock, new Vec3(face_x, face_y, face_z));
        return { success: true };
      }

      // ── Inventory / items ─────────────────────────────────────────────────

      case "equip": {
        const { item_name, destination = "hand" } = params;
        const item = bot.inventory.items().find((i) => i.name === item_name);
        if (!item) return { success: false, error: `Item not found: ${item_name}` };
        await bot.equip(item, destination);
        return { success: true };
      }

      case "craft": {
        const { item_name, count = 1 } = params;
        const itemType = bot.registry.itemsByName[item_name];
        if (!itemType) return { success: false, error: `Unknown item: ${item_name}` };
        const recipe = bot.recipesFor(itemType.id, null, 1, null)[0];
        if (!recipe) return { success: false, error: `No recipe found for: ${item_name}` };
        // Check if crafting table is needed
        const needsTable = recipe.requiresTable;
        if (needsTable) {
          const table = bot.findBlock({ matching: bot.registry.blocksByName["crafting_table"].id, maxDistance: 4 });
          if (!table) return { success: false, error: "No crafting table nearby" };
          await bot.craft(recipe, count, table);
        } else {
          await bot.craft(recipe, count, null);
        }
        return { success: true };
      }

      case "drop": {
        const { item_name, count = 1 } = params;
        const item = bot.inventory.items().find((i) => i.name === item_name);
        if (!item) return { success: false, error: `Item not found: ${item_name}` };
        await bot.toss(item.type, null, Math.min(count, item.count));
        return { success: true };
      }

      case "eat": {
        const { item_name } = params;
        if (item_name) {
          const food = bot.inventory.items().find((i) => i.name === item_name);
          if (food) await bot.equip(food, "hand");
        }
        await bot.consume();
        return { success: true };
      }

      // ── Combat ────────────────────────────────────────────────────────────

      case "attack": {
        const entity = bot.entities[params.entity_id];
        if (!entity) return { success: false, error: "Entity not found" };
        bot.pvp.attack(entity);
        return { success: true };
      }

      case "stop_attack": {
        bot.pvp.stop();
        return { success: true };
      }

      // ── Chat ──────────────────────────────────────────────────────────────

      case "chat": {
        bot.chat(params.message);
        return { success: true };
      }

      case "whisper": {
        bot.chat(`/msg ${params.username} ${params.message}`);
        return { success: true };
      }

      // ── Interaction ───────────────────────────────────────────────────────

      case "activate_block": {
        const { x, y, z } = params;
        const block = bot.blockAt(new Vec3(x, y, z));
        if (!block) return { success: false, error: "No block at position" };
        await bot.activateBlock(block);
        return { success: true };
      }

      case "sleep": {
        const bedBlock = bot.findBlock({ matching: (b) => b.name.includes("bed"), maxDistance: 4 });
        if (!bedBlock) return { success: false, error: "No bed nearby" };
        await bot.sleep(bedBlock);
        return { success: true };
      }

      case "get_state": {
        const buildGameState = require("./gameState");
        return { success: true, data: buildGameState(bot) };
      }

      default:
        return { success: false, error: `Unknown action: ${action}` };
    }
  } catch (err) {
    return { success: false, error: err.message };
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

module.exports = executeAction;
