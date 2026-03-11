# 👽 Claude Code Max

**Claude Code Max** is an elite, highly autonomous AI software engineer that runs directly in your terminal. 

Built with an unapologetic focus on execution speed, fault tolerance, and developer autonomy, it functions as a legendary 10x CLI companion that investigates, plans, executes, and validates its own codebase changes without needing to ask for permission.

## ✨ Features

- **Hybrid Model Routing**: Defaults to the powerful `gemini-2.5-flash` model via Google GenAI SDK. If API rate limits are hit, it intelligently falls back to Groq (Llama 3) for high-speed, cost-effective continuity.
- **Deep System Autonomy**: Investigates code using local file tools, searches the web for documentation or stackoverflow answers, and directly executes bash commands (with safety guards).
- **Advanced Context Management**: Manages session state natively via `.claude_session.json` and chunk-reads large files to preserve token windows.
- **Beautiful Terminal TUI**: Built with `Rich`, featuring an alien-coral premium UI, animated spinners, diff-syntax highlighting, and detailed task logs.

## 🚀 Quickstart

1. Clone the repository:
```bash
git clone https://github.com/rahul-kumar-362/claudeCopy.git
cd claudeCopy
```

2. Install the necessary dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your API Keys in a `.env` file:
```env
GEMINI_API_KEY=your_google_genai_key
GEMINI_API_KEY_2=your_backup_google_genai_key
GROQ_API_KEY=your_backup_groq_key
```
*(Claude Code Max natively rotates through available Gemini keys if rate-limited!)*

4. Launch the Agent:
```bash
python agent.py
```

## 🛠️ Built-in Toolset
- `run_command` / `run_background_command`
- `read_file` / `read_file_chunk`
- `write_file` / `replace_in_file` / `edit_file_lines`
- `lint_code`
- `list_dir` / `search_files`
- `web_search` / `web_scrape`
- Full `git` suite (`git_status`, `git_diff`, `git_commit`)

---

*“Speak with the authority and brevity of a senior principal engineer. No fluff. Just results.”*
