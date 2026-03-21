<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-success.svg?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/AI_Model-GLM--4.7%20|%20Gemini%20|%20Llama%203-orange.svg?style=for-the-badge" alt="AI Agent" />
</div>

<br />

<div align="center">
  <h1>🛸 Claude Code Max: BEAST MODE</h1>
  <p><strong>The ultimate, highly autonomous CLI AI software engineering companion powered by GLM 4.7.</strong></p>
</div>

---

**Claude Code Max** has been heavily upgraded into **BEAST MODE**. It is an elite, uninhibited AI coding agent designed to operate natively within your terminal environments. Built for developers who value execution speed, robust autonomy, and a zero-friction workflow, this agent investigates, plans, executes, and validates its own codebase changes without needing to ask for permission.

Unlike standard conversational AIs, Claude Code Max is a system-level agent heavily armed with **22 built-in tools** to read, write, execute, lint, and troubleshoot software dynamically.

## ✨ Premium Features

### 🧠 Hybrid Intelligent Routing (Fireworks First)
Designed for extreme resilience and cost-efficiency, Claude Code Max utilizes a **Hybrid Multi-Model Architecture**:
- **Primary Engine**: Fireworks AI (`accounts/fireworks/models/glm-4-9b-chat`) for blazing fast, deep context, and beast mode reasoning.
- **Failover / Rate-Limit Bypass**: Intelligently detects API errors, seamlessly rotates through a pool of backup Gemini API keys, and as a final fallback, routes requests to Groq (Llama 3) for high-speed, cost-effective continuity without dropping the session.

### ⚡ Deep Native Autonomy 
It doesn't just write code; it manipulates your system natively.
- **Terminal Execution**: Runs shell commands (`npm install`, `python -m pytest`, `git commit`) and perfectly parses the output.
- **Process Management**: Capable of spawning, listing, and killing processes, including persistent dev servers directly in the background.
- **File System Mastery**: Surgical File IO, AST-based Python analysis (`analyze_code`), recursive deep search (`find_files`), and multi-file batch generation (`multi_file_write`).

### 🌐 Integrated Web-Scraping & Request Testing
When faced with an unknown error or lacking documentation, Claude Code Max automatically leverages DuckDuckGo OSINT searching combined with live web scraping (`urllib`). You can also make direct HTTP requests (`http_request`) to interact with APIs and webhooks.

### 🎨 Stunning TUI (Terminal User Interface)
Built utilizing the `Rich` Python library, the CLI interface is absolutely stunning. Featuring:
- Custom Alien-Coral Hex Palettes (`#d97757`)
- Interactive animated spinners, execution status displays, and a BEAST MODE banner
- Embedded Markdown and syntax-highlighted code diffs
- Explicit separation of Internal Thoughts (`<thought>`) vs execution logs

---

## 🛠️ Built-In Toolset (22 Beast Mode Tools)

Claude Code Max boasts a robust set of 22 fully integrated functional tools, abstracted into a continuous execution loop.

| Category | Tools |
| -------- | -------- |
| **System** | `run_command`, `run_background_command`, `process_manager` |
| **File I/O** | `read_file`, `read_file_chunk`, `write_file`, `replace_in_file`, `edit_file_lines`, `patch_file`, `multi_file_write`, `list_dir`, `find_files`, `search_files` | 
| **Code** | `analyze_code`, `run_python`, `lint_code` (Ruff Native Integration) |
| **Web** | `web_search` (DDGS), `web_scrape`, `http_request` |
| **Git** | `git_status`, `git_diff`, `git_commit` |
| **Meta** | `task_planner`, `generate_project` |

---

## 🚀 Quickstart & Installation

### 1. Clone & Setup
```bash
git clone https://github.com/rahul-kumar-362/claudeCopy.git
cd claudeCopy
pip install -r requirements.txt
```
*(Ensure you have Python 3.8+ installed).*

### 2. Configure Environment (`.env`)
Create a `.env` file at the root of the project. Claude Code Max will auto-detect these on startup.

```env
# Primary Model Configuration
FIREWORKS_API_KEY=your_fireworks_api_key
AGENT_MODEL=accounts/fireworks/models/glm-4-9b-chat

# Backup Failover Keys
GEMINI_API_KEY=your_google_genai_key
GEMINI_API_KEY_2=your_backup_google_genai_key
GROQ_API_KEY=your_backup_groq_key

# System Overrides (1=Enabled, 0=Disabled)
AGENT_ENABLE_SHELL=1
AGENT_ENABLE_GIT=1
AGENT_ENABLE_WEB=1
```

### 3. Initialize Agent
```bash
python agent.py
```

---

## 🔒 Security & Safety Defaults

Claude Code Max operates with maximum power but utilizes intelligent safety guardrails:
- **Destructive Command Blocking**: A deeply integrated regex filter blocks executing commands like `rm -rf /`, `drop database`, or `reg delete`.
- **Granular Feature Toggles**: You can independently disable shell commands (`AGENT_ENABLE_SHELL=0`), Git tools (`AGENT_ENABLE_GIT=0`), or Web functionality (`AGENT_ENABLE_WEB=0`) via the `.env` configuration depending on your trust level for the project.

---

<div align="center">
  <i>“Speak with the authority and brevity of a senior principal engineer. No fluff. Just results. BEAST MODE.”</i>
</div>
