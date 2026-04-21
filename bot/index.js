/**
 * MineAI Bot – Minecraft protocol layer
 *
 * Connects to the Minecraft server as a player using Mineflayer and exposes
 * a WebSocket server on WS_PORT so the Python agent can send action commands
 * and receive game-state events.
 *
 * WebSocket message format:
 *   - Bot → Agent:  { type: "event", event: "<name>", data: { … } }
 *   - Agent → Bot:  { type: "action", action: "<name>", params: { … }, id: "<uuid>" }
 *   - Bot → Agent:  { type: "action_result", id: "<uuid>", success: bool, error?: string }
 */

"use strict";

require("dotenv").config();

const mineflayer          = require("mineflayer");
const { pathfinder, Movements, goals } = require("mineflayer-pathfinder");
const pvp                 = require("mineflayer-pvp").plugin;
const autoEat             = require("mineflayer-auto-eat").plugin;
const collectBlock        = require("mineflayer-collectblock").plugin;
const toolPlugin          = require("mineflayer-tool").plugin;
const { WebSocketServer } = require("ws");

const buildGameState  = require("./lib/gameState");
const executeAction   = require("./lib/actions");

// ─── Config ────────────────────────────────────────────────────────────────

const MC_HOST  = process.env.HOST     || "localhost";
const MC_PORT  = parseInt(process.env.PORT || "25565", 10);
const USERNAME = process.env.USERNAME  || "MineAI";
const AUTH     = process.env.AUTH      || "offline";
const WS_PORT  = parseInt(process.env.WS_PORT || "3001", 10);

// ─── WebSocket server ───────────────────────────────────────────────────────

const wss = new WebSocketServer({ port: WS_PORT });
let agentSocket = null;   // single agent connection

wss.on("listening", () => {
  console.log(`[WS] Agent WebSocket server listening on ws://localhost:${WS_PORT}`);
});

wss.on("connection", (ws) => {
  console.log("[WS] Python agent connected");
  agentSocket = ws;
  // Send current game state immediately so the agent can bootstrap
  sendEvent("connected", { username: bot.username });

  ws.on("message", async (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      console.warn("[WS] Received non-JSON message – ignored");
      return;
    }
    if (msg.type === "action") {
      const result = await executeAction(bot, msg.action, msg.params || {});
      ws.send(JSON.stringify({
        type: "action_result",
        id: msg.id || null,
        ...result,
      }));
    }
  });

  ws.on("close", () => {
    console.log("[WS] Python agent disconnected");
    agentSocket = null;
  });
});

/** Broadcast a game event to the connected agent (if any). */
function sendEvent(event, data = {}) {
  if (!agentSocket || agentSocket.readyState !== agentSocket.OPEN) return;
  agentSocket.send(JSON.stringify({ type: "event", event, data }));
}

// ─── Minecraft bot ──────────────────────────────────────────────────────────

const bot = mineflayer.createBot({
  host:     MC_HOST,
  port:     MC_PORT,
  username: USERNAME,
  auth:     AUTH,
  version:  "1.21",
});

// Load plugins
bot.loadPlugin(pathfinder);
bot.loadPlugin(pvp);
bot.loadPlugin(autoEat);
bot.loadPlugin(collectBlock);
bot.loadPlugin(toolPlugin);

// ─── Bot events ─────────────────────────────────────────────────────────────

bot.once("spawn", () => {
  console.log(`[Bot] Spawned as ${bot.username}`);
  // Configure pathfinder default movements
  const defaultMovements = new Movements(bot);
  bot.pathfinder.setMovements(defaultMovements);
  // Enable auto-eat
  bot.autoEat.options.priority  = "foodPoints";
  bot.autoEat.options.startAt   = 14;
  sendEvent("spawned", buildGameState(bot));
});

bot.on("chat", (username, message) => {
  if (username === bot.username) return;
  sendEvent("chat", { username, message });
});

bot.on("health", () => {
  sendEvent("health", { health: bot.health, food: bot.food, saturation: bot.foodSaturation });
});

bot.on("death", () => {
  sendEvent("death", { position: bot.entity?.position });
});

bot.on("entityHurt", (entity) => {
  if (entity === bot.entity) {
    sendEvent("hurt", { health: bot.health, attacker: null });
  }
});

bot.on("playerJoined", (player) => {
  sendEvent("player_joined", { username: player.username });
});

bot.on("playerLeft", (player) => {
  sendEvent("player_left", { username: player.username });
});

// Periodic state broadcast (every 2 seconds)
setInterval(() => {
  if (!bot.entity) return;
  sendEvent("state", buildGameState(bot));
}, 2000);

bot.on("error", (err)  => console.error("[Bot] Error:", err.message));
bot.on("end",   (reason) => {
  console.warn("[Bot] Disconnected:", reason);
  sendEvent("disconnected", { reason });
});

bot.on("kicked", (reason) => {
  console.warn("[Bot] Kicked:", reason);
  sendEvent("kicked", { reason });
});

// ─── Graceful shutdown ──────────────────────────────────────────────────────

process.on("SIGINT", () => {
  console.log("\n[Bot] Shutting down…");
  bot.quit();
  wss.close();
  process.exit(0);
});
