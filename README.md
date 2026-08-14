# 🧠 Liebchen — Your Local AI Learning Companion

> A fully autonomous, local educational and productivity AI agent powered by Ollama + LangGraph + SQLite.

## Quick Start

### Prerequisites

1. **Python 3.10+** installed
2. **Ollama** installed and running:
   ```bash
   # Install: https://ollama.com/download
   ollama serve
   ollama pull llama3:8b
   ```

### Installation

```bash
# Clone and enter the project
cd Liebchen

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install the package in editable mode
pip install -e .
```

### Run the Agent

```bash
# Interactive mode
python cli.py

# First-time setup
python cli.py --setup

# Startup greeting mode (for system boot)
python cli.py --startup
```

### Run Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Project Structure

```
Liebchen/
├── liebchen/              # Core package
│   ├── config.py          # Settings & constants
│   ├── database/          # SQLite schema + CRUD
│   ├── llm/               # Ollama client + prompts
│   ├── agent/             # LangGraph state, tools, graph
│   ├── api/               # REST API (Phase 3)
│   └── startup/           # System boot integration
├── cli.py                 # CLI entry point
├── data/                  # SQLite databases (auto-created)
└── tests/                 # Test suite
```

## Core Features

- **Skill Analysis** — Analyze your skills vs. goals, identify gaps
- **Dynamic Timetable** — Auto-generated study schedules with adjustment
- **Educational Tutor** — Clear explanations of complex topics
- **Startup Greeting** — Morning briefing with today's tasks
- **Persistent Memory** — Remembers your context across sessions

## Configuration

Copy `.env.example` to `.env` and customize:

```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3:8b
OLLAMA_TEMPERATURE=0.7
LIEBCHEN_DB_PATH=data/liebchen.db
```

## License

MIT
