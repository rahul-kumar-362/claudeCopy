<div align="center">
  <img src="https://img.shields.io/badge/Status-Active-success.svg?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/AI_Model-Gemini%20|%20Llama%203-orange.svg?style=for-the-badge" alt="AI Agent" />
</div>

<br />

<div align="center">
  <h1>🛸 Claude Code Max</h1>
  <p><strong>The ultimate, highly autonomous CLI AI software engineering companion.</strong></p>
</div>

---

**Claude Code Max** is an elite, uninhibited AI coding agent designed to operate natively within your terminal environments. Built for developers who value execution speed, robust autonomy, and a zero-friction workflow, this agent investigates, plans, executes, and validates its own codebase changes without needing to ask for permission.

Unlike standard conversational AIs, Claude Code Max is a system-level agent heavily armed with tools to read, write, execute, lint, and troubleshoot software dynamically.

## ✨ Premium Features

### 🧠 Hybrid Intelligent Routing
Designed for extreme resilience and cost-efficiency, Claude Code Max utilizes a **Hybrid Multi-Model Architecture**:
- **Primary Engine**: Google GenAI (`gemini-2.5-flash`) for deep, context-heavy codebase comprehension and tool streaming.
- **Failover / Rate-Limit Bypass**: Intelligently detects 429 API errors, seamlessly rotates through backup Gemini API keys, and as a final fallback, routes requests to Groq (Llama 3) for high-speed, cost-effective continuity without dropping the session.

### ⚡ Deep Native Autonomy 
It doesn't just write code; it manipulates your system natively.
- **Terminal Execution**: Runs shell commands (`npm install`, `python -m pytest`, `git commit`) and perfectly parses the output `stdout` and `stderr`.
- **Background Processes**: Capable of spawning and detaching persistent dev servers (`npm run dev`) directly in the background.
- **File System Mastery**: Performs surgical Regex and line-based replacements, reads directories recursively up to thousands of lines, and auto-generates files.

### 🌐 Integrated Web-Scraping & Search
When faced with an unknown error or lacking documentation, Claude Code Max doesn't pause. It automatically leverages **DuckDuckGo OSINT searching** combined with live web scraping (`urllib`) to find real-time Stack Overflow discussions and API documentation—and applies the fix autonomously.

### 🎨 Stunning TUI (Terminal User Interface)
Built utilizing the `Rich` Python library, the CLI interface is absolutely stunning. Featuring:
- Custom Alien-Coral Hex Palettes (`#d97757`)
- Interactive animated spinners and execution status displays
- Embedded Markdown and syntax-highlighted code diffs
- Explicit separation of Internal Thoughts (`<thought>`) vs execution logs

---

## 🛠️ Built-In Toolset

Claude Code Max boasts a robust set of 15 fully integrated functional tools, abstracted into a continuous execution loop:

| Category | Commands |
| -------- | -------- |
| **System** | `run_command`, `run_background_command` |
| **File I/O** | `read_file`, `read_file_chunk`, `write_file`, `replace_in_file`, `edit_file_lines`, `search_files`, `list_dir` | 
| **DevOps** | `lint_code` (Ruff Native Integration) |
| **Web** | `web_search` (DDGS), `web_scrape` |
| **Git** | `git_status`, `git_diff`, `git_commit` |

---

## 🚀 Quickstart & Installation

### 1. Clone & Setup
```bash
git clone https://github.com/rahul-kumar-362/claudeCopy.git
cd claudeCopy
pip install -r requirements.txt
```
*(Ensure you have Python 3.8+ installed).*

### 2. Configure Brain / Environment (`.env`)
Create a `.env` file at the root of the project. Claude Code Max will auto-detect these on startup.

```env
# Required: Primary Model
GEMINI_API_KEY=your_google_genai_key

# Optional: Automatic Rate-Limit Failover Rotation Keys
GEMINI_API_KEY_2=your_backup_google_genai_key
GROQ_API_KEY=your_backup_groq_key

# Optional: System Overrides
AGENT_ENABLE_SHELL=1
AGENT_ENABLE_GIT=1
AGENT_ENABLE_WEB=1
AGENT_TEMPERATURE=0.2
```

### 3. Initialize Agent
```bash
python agent.py
```

Type any prompt to begin. 

---

## 🔒 Security & Safety Defaults

Claude Code Max operates with maximum power but utilizes intelligent safety guardrails:
- **Destructive Command Blocking**: A deeply integrated regex filter blocks executing commands like `rm -rf /`, `drop database`, or `reg delete`.
- **Granular Feature Toggles**: You can independently disable shell commands (`AGENT_ENABLE_SHELL=0`), Git tools (`AGENT_ENABLE_GIT=0`), or Web functionality (`AGENT_ENABLE_WEB=0`) via the `.env` configuration depending on your trust level for the project.

---

<div align="center">
  <i>“Speak with the authority and brevity of a senior principal engineer. No fluff. Just results.”</i>
</div>
