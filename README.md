# MineAI

An autonomous AI player for Minecraft Fabric 1.21, inspired by [Voyager](https://arxiv.org/abs/2305.16291).  
Uses a **local LLM** (llama.cpp) for fast real-time decisions and optionally **GPT-4.1** (GitHub Models / OpenAI) for higher-quality curriculum, critic, and skill generation.

```
 ┌──────────────────────┐        WebSocket          ┌────────────────────────────┐
 │  Minecraft Server    │◄──── Mineflayer bot ──────►│  Python AI Agent           │
 │  (Fabric 1.21)       │      (Node.js)             │  ReAct + Voyager loop      │
 └──────────────────────┘                            └──────────┬─────────────────┘
                                                                │
                                              ┌─────────────────┴──────────────────┐
                                              │                                    │
                                  ┌───────────▼───────────┐          ┌────────────▼────────────┐
                                  │  Local LLM (ReAct)    │          │  Strong LLM (optional)  │
                                  │  llama.cpp / any gguf │          │  GPT-4.1 via GitHub     │
                                  │  every ~3 s           │          │  Models or OpenAI API   │
                                  └───────────────────────┘          └─────────────────────────┘
```

## Features

| Capability | Implementation |
|---|---|
| Chat with players | LLM reads chat events, replies naturally |
| Autonomous navigation | `mineflayer-pathfinder` A* |
| Resource gathering | `mineflayer-collectblock` |
| Combat + retreat | `mineflayer-pvp` + health-based flee logic |
| Farming | Harvest & plant crops via dedicated skill |
| Building | `place_block` chains guided by LLM or skill |
| Auto-eat | `mineflayer-auto-eat` (no LLM needed) |
| **Automatic curriculum** | LLM proposes the next Minecraft milestone every N cycles |
| **Skill library** | ChromaDB-indexed, ever-growing store of reusable Python skills |
| **Skill generation** | LLM writes new `async def run()` skills when a goal fails repeatedly |
| **Critic / retry loop** | Post-action LLM verification with up to N retries per turn |
| Long-term goals | Persistent goal stack saved to `data/memory.json` |
| Long-term memory | Key-value facts + achievement log saved to disk |

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
git clone https://github.com/SylCode/MineAI
cd MineAI
cp .env.example .env
# edit .env – see Configuration Reference below
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

### 3 – (Optional) Enable GPT-4.1 for smart calls

Get a free [GitHub PAT](https://github.com/settings/tokens) with the `models:read` scope, then in `.env`:

```
STRONG_LLM_BASE_URL=https://models.inference.ai.azure.com
STRONG_LLM_MODEL=gpt-4.1
STRONG_LLM_API_KEY=github_pat_...
```

If `STRONG_LLM_BASE_URL` is left empty, the local model handles everything.

### 4 – Start the bot layer

```bash
cd bot
npm install
node index.js
```

### 5 – Start the Python agent

```bash
cd agent
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python main.py
```

> **Note:** On first run, ChromaDB downloads a small (~80 MB) ONNX embedding model for semantic skill retrieval. This is a one-time download.

---

## Project Layout

```
MineAI/
├── bot/                          Node.js Mineflayer layer
│   ├── index.js                  Bot entry point + WebSocket server
│   └── lib/
│       ├── actions.js            Action dispatcher (30+ actions)
│       └── gameState.js          Game-state snapshot builder
│
├── agent/                        Python AI agent
│   ├── main.py                   Entry point
│   └── mineai/
│       ├── config.py             Config from environment variables
│       ├── bot_client.py         WebSocket client + event routing
│       ├── planner.py            Voyager-inspired ReAct loop
│       ├── memory.py             Short-term history + long-term facts
│       ├── curriculum.py         Automatic task proposal (LLM)
│       └── llm/
│           ├── client.py         OpenAI-compatible async client (local + cloud)
│           └── prompts.py        System, critic, curriculum, skill-gen prompts
│       └── skills/
│           ├── skill_library.py  ChromaDB-backed skill store + retrieval
│           ├── skill_generator.py  LLM writes new Python skill functions
│           ├── wood_gathering.py
│           ├── mining.py
│           ├── farming.py
│           ├── combat.py
│           ├── building.py
│           └── generated/        Runtime output of skill generator
│
├── data/                         Created automatically at runtime
│   ├── memory.json               Persistent facts, goals, achievements
│   └── skill_chroma/             ChromaDB skill embeddings
│
└── .env.example                  Configuration template
```

---

## How It Works

Each think cycle (every `THINK_INTERVAL` seconds):

1. **Curriculum** *(every N cycles, strong LLM)* – proposes the next concrete Minecraft milestone based on inventory, health, and achievements. Pushed onto the goal stack.
2. **Skill retrieval** – ChromaDB finds the top-k most relevant stored skills for the current goal and injects them into the prompt context.
3. **Reason** *(local LLM)* – builds a prompt from system instructions, long-term memory, goal stack, retrieved skills, recent history, and current game state. LLM outputs `THINK:` + `ACTIONS:` JSON.
4. **Act** – sends each action to the Mineflayer bot via WebSocket.
5. **Critic** *(strong LLM)* – compares before/after game state against the goal. If the goal wasn't progressed, provides a retry hint and loops back to step 3 (up to `MAX_RETRIES` times).
6. **Remember** – stores the turn in short-term history. Records a completed achievement on success.
7. **Skill generation** *(strong LLM, on repeated failure)* – if the same goal fails `SKILL_FAIL_THRESHOLD` times, the LLM writes a new `async def run(client, state)` Python skill, validates it with `ast.parse`, saves it to `skills/generated/`, and registers it in ChromaDB.

---

## Configuration Reference

### Minecraft bot

| Variable | Default | Description |
|---|---|---|
| `HOST` | `localhost` | Minecraft server host |
| `PORT` | `25565` | Minecraft server port |
| `USERNAME` | `MineAI` | Bot username |
| `AUTH` | `offline` | `offline` or `microsoft` |
| `WS_PORT` | `3001` | WebSocket port for bot↔agent communication |

### Local LLM (ReAct loop)

| Variable | Default | Description |
|---|---|---|
| `LLM_HOST` | `localhost` | llama.cpp host |
| `LLM_PORT` | `8080` | llama.cpp port |
| `LLM_MODEL` | `local-model` | Model name (shown in logs) |
| `LLM_TIMEOUT` | `60` | Request timeout in seconds |
| `LLM_API_KEY` | *(empty)* | API key – leave blank for llama.cpp |

### Strong LLM (curriculum / critic / skill generation)

| Variable | Default | Description |
|---|---|---|
| `STRONG_LLM_BASE_URL` | *(empty)* | Leave empty to reuse the local LLM |
| `STRONG_LLM_MODEL` | `gpt-4.1` | Model name |
| `STRONG_LLM_API_KEY` | *(empty)* | GitHub PAT or OpenAI key |
| `STRONG_LLM_TIMEOUT` | `120` | Request timeout in seconds |

### Generation

| Variable | Default | Description |
|---|---|---|
| `MAX_TOKENS` | `512` | Max tokens per ReAct reply |
| `TEMPERATURE` | `0.3` | Sampling temperature |

### Agent behaviour

| Variable | Default | Description |
|---|---|---|
| `THINK_INTERVAL` | `3.0` | Seconds between think cycles |
| `MAX_HISTORY` | `8` | Past turns to include in prompt |
| `MAX_RETRIES` | `2` | Critic retry attempts per turn |
| `CURRICULUM_INTERVAL` | `10` | Run curriculum every N cycles |
| `SKILL_TOP_K` | `3` | Skills retrieved per turn |
| `SKILL_FAIL_THRESHOLD` | `3` | Failures before skill generation triggers |
| `MEMORY_PATH` | `data/memory.json` | Persistent memory file |
| `SKILL_CHROMA_PATH` | `data/skill_chroma` | ChromaDB directory |

---

## Extending the Agent

### Adding a new primitive action
1. Add the handler in `bot/lib/actions.js` inside the `switch` block.
2. Document it in `SYSTEM_PROMPT` in `agent/mineai/llm/prompts.py` and in `SKILL_GENERATION_PROMPT`.

### Adding a hardcoded skill
Create a file in `agent/mineai/skills/` with `async def run(client, state) -> bool`. The skill generator uses the same contract for generated skills.

### Switching to a different cloud LLM
Set `STRONG_LLM_BASE_URL` and `STRONG_LLM_API_KEY` to any OpenAI-compatible endpoint (e.g. Anthropic via proxy, Mistral API, Azure OpenAI).

---

## Licence

MIT


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
