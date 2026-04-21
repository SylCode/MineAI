# MineAI

An autonomous AI player for Minecraft Fabric 1.21, powered by a **local LLM** (llama.cpp).

```
 ┌──────────────────────┐        WebSocket          ┌───────────────────────┐
 │  Minecraft Server    │◄──── Mineflayer bot ──────►│  Python AI Agent      │
 │  (Fabric 1.21)       │      (Node.js)             │  ReAct loop + LLM     │
 └──────────────────────┘                            └──────────┬────────────┘
                                                                │  HTTP /v1/chat/completions
                                                     ┌──────────▼────────────┐
                                                     │  llama.cpp server     │
                                                     │  (local, any .gguf)   │
                                                     └───────────────────────┘
```

## Features

| Capability | Implementation |
|---|---|
| Chat with players | LLM reads chat events, replies via `chat` action |
| Autonomous navigation | `mineflayer-pathfinder` A* |
| Resource gathering | `mineflayer-collectblock` |
| Combat | `mineflayer-pvp` |
| Farming | LLM plans crop cycles; bot plants/harvests |
| Building | `place_block` actions guided by LLM |
| Auto-eat | `mineflayer-auto-eat` (no LLM needed) |
| Long-term goals | Persistent goal stack in `data/memory.json` |
| Long-term memory | Key-value facts saved to disk |

---

## Requirements

| Component | Minimum version |
|---|---|
| Node.js | 18 |
| Python | 3.11 |
| llama.cpp | any recent build with `--jinja` flag |
| Minecraft | Fabric 1.21 server (online or offline mode) |

---

## Quick Start

### 1 – Clone and configure

```bash
git clone https://github.com/you/MineAI
cd MineAI
cp .env.example .env
# edit .env: set HOST, PORT, USERNAME, LLM_PORT, etc.
```

### 2 – Start the llama.cpp server

```bash
./llama-server \
  --model models/your-model.gguf \
  --port 8080 \
  --ctx-size 4096 \
  --jinja            # enables OpenAI-compatible /v1/chat/completions
```

Recommended models (4–8 GB VRAM / RAM):
- **Mistral 7B Instruct** (fast, good instruction following)
- **Llama 3.2 8B Instruct** (strong reasoning)
- **Qwen 2.5 7B Instruct** (excellent JSON output)

### 3 – Install and start the bot layer

```bash
cd bot
npm install
cp ../.env.example .env   # or symlink
node index.js
```

The bot will connect to the Minecraft server and wait for the Python agent on
`ws://localhost:3001`.

### 4 – Install and start the Python agent

```bash
cd agent
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cp ../.env.example .env
python main.py
```

---

## Project Layout

```
MineAI/
├── bot/                   Node.js Mineflayer layer
│   ├── index.js           Bot entry point + WebSocket server
│   └── lib/
│       ├── actions.js     Action dispatcher
│       └── gameState.js   Game-state snapshot builder
│
├── agent/                 Python AI agent
│   ├── main.py            Entry point
│   └── mineai/
│       ├── config.py      Config from environment variables
│       ├── bot_client.py  WebSocket client + event routing
│       ├── planner.py     ReAct think/act loop
│       ├── memory.py      Short-term + long-term memory
│       └── llm/
│           ├── client.py  llama.cpp HTTP client (async)
│           └── prompts.py System prompt + state formatter
│
├── data/                  Runtime data (created automatically)
│   └── memory.json        Persistent agent memory
│
└── .env.example           Configuration template
```

---

## How It Works

The agent runs a **ReAct loop** every few seconds (configurable via `THINK_INTERVAL`):

1. **Observe** – collect current game state (position, health, food, inventory, nearby
   entities and blocks) from the bot.
2. **Reason** – build a prompt containing the system prompt, long-term facts, goal
   stack, recent history, and current state, then call the local LLM.
3. **Act** – parse `THINK:` (reasoning) and `ACTIONS:` (JSON array) from the reply,
   send each action to the Mineflayer bot via WebSocket.
4. **Remember** – store the observation/action/result in short-term history and
   optionally update long-term facts or goals.

In parallel, incoming chat messages are queued and injected into the next prompt so
the bot responds naturally to players.

---

## Configuration Reference

Key variables in `.env`:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `localhost` | Minecraft server host |
| `PORT` | `25565` | Minecraft server port |
| `USERNAME` | `MineAI` | Bot username |
| `AUTH` | `offline` | `offline` or `microsoft` |
| `LLM_PORT` | `8080` | llama.cpp server port |
| `TEMPERATURE` | `0.3` | LLM sampling temperature (lower = more deterministic) |
| `THINK_INTERVAL` | `3.0` | Seconds between autonomous think cycles |
| `MAX_HISTORY` | `8` | Recent turns to include in prompt |
| `MEMORY_PATH` | `data/memory.json` | Persistent memory file |

---

## Extending the Agent

### Adding a new action
1. Add the handler in `bot/lib/actions.js` inside the `switch` block.
2. Document it in the `SYSTEM_PROMPT` in `agent/mineai/llm/prompts.py`.

### Adding skills / macros
Create a helper in `agent/mineai/skills/` that chains multiple actions (e.g.
`skills/wood_gathering.py` that locates a tree, navigates, fells it, and collects
all logs).  Call the skill from the planner based on the current goal.

### Using a different LLM backend
Replace `LlamaClient` in `agent/mineai/llm/client.py` with any client that exposes
an `async chat(messages) → str` interface.  The planner is backend-agnostic.

---

## Licence

MIT
