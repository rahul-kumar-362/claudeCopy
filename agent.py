import os
import sys
import subprocess
import glob
import time
import difflib
import shutil
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.style import Style
from rich.table import Table
from rich.syntax import Syntax
from rich.columns import Columns
from rich.live import Live
from rich.spinner import Spinner
from ddgs import DDGS
import urllib.request
import urllib.error
import requests
import json
import re
import concurrent.futures
import io

# Force UTF-8 on Windows to prevent cp1252 emoji crash
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# ─── Environment ───────────────────────────────────────────────────────────────
load_dotenv()

# ─── Rich Console ──────────────────────────────────────────────────────────────
console = Console(highlight=False)
UNICODE_SAFE = (getattr(sys.stdout, "encoding", "") or "").lower().startswith("utf")

# ─── Logging ───────────────────────────────────────────────────────────────────
LOG_PATH = Path(os.getenv("AGENT_LOG_FILE", "agent.log"))
logger = logging.getLogger("claude_code_max")
logger.setLevel(logging.INFO)
if not logger.handlers:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# ─── Premium Color Palette ─────────────────────────────────────────────────────
P = "bold #d97757"       # Primary Coral
S = "#e5c07b"            # Secondary Gold
DIM = "dim #888888"      # Muted
ACC = "bold #56b6c2"     # Accent Cyan
OK = "bold #98c379"      # Success Green
ERR = "bold #e06c75"     # Error Red
WARN = "bold #e5c07b"    # Warning Yellow
BORDER = Style(color="#d97757", dim=True)

# ─── Runtime Config ────────────────────────────────────────────────────────────
def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "")


ENABLE_SHELL = _env_flag("AGENT_ENABLE_SHELL", "1")
ENABLE_GIT = _env_flag("AGENT_ENABLE_GIT", "1")
ENABLE_WEB = _env_flag("AGENT_ENABLE_WEB", "1")

MODEL_NAME = os.getenv("AGENT_MODEL", "gemini-2.5-flash")
try:
    TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
except ValueError:
    TEMPERATURE = 0.2
try:
    MAX_OUTPUT_TOKENS = int(os.getenv("AGENT_MAX_OUTPUT_TOKENS", "2048"))
except ValueError:
    MAX_OUTPUT_TOKENS = 2048

try:
    MAX_TOOL_ITERATIONS = int(os.getenv("AGENT_MAX_TOOL_ITERATIONS", "8"))
except ValueError:
    MAX_TOOL_ITERATIONS = 8

# ─── Dangerous Commands ────────────────────────────────────────────────────────
DANGEROUS_PATTERNS = [
    "rm -rf",
    "rm -r /",
    "sudo rm -rf /",
    "rmdir",
    "rd /s /q",
    "del /",
    "format ",
    "format /q",
    "drop table",
    "drop database",
    "truncate ",
    "shutdown",
    "shutdown /s",
    "shutdown /r",
    "poweroff",
    "halt",
    "mkfs",
    "mkfs.",
    "dd if=",
    ":(){",
    "deltree",
    "Remove-Item",
    "Clear-Content",
    "reg delete",
]

# ─── Session Tracking ─────────────────────────────────────────────────────────
SESSION_START = time.time()
TOKEN_COUNTER = {"input": 0, "output": 0}
SESSION_FILE = Path(os.getenv("AGENT_SESSION_FILE", ".claude_session.json"))

def load_session() -> list:
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not load session history: %s", e)
    return None

def save_session(history) -> None:
    try:
        hist_data = [json.loads(h.model_dump_json()) if hasattr(h, "model_dump_json") else h for h in history]
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(hist_data, f, indent=2)
    except Exception as e:
        logger.warning("Could not save session history: %s", e)

# ─── Groq Integration ──────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# We will use Groq for fast, simple routing/tools and Gemini for heavy context if needed.
# For simplicity, if GROQ_API_KEY is present, we try Groq first.

def ask_groq(messages: list, tools: list) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Format tools for Groq (OpenAI format)
    groq_tools = []
    if tools:
        for tool in tools:
            # We map our custom simple tools to JSON schema
            groq_tools.append({
                "type": "function",
                "function": {
                    "name": tool.__name__,
                    "description": tool.__doc__ or "",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "filepath": {"type": "string"},
                            "content": {"type": "string"},
                            "target": {"type": "string"},
                            "replacement": {"type": "string"},
                            "start_line": {"type": "integer"},
                            "end_line": {"type": "integer"},
                            "new_content": {"type": "string"},
                            "dirpath": {"type": "string"},
                            "query": {"type": "string"},
                            "url": {"type": "string"},
                            "message": {"type": "string"}
                        }
                    } # In a production Agent, we'd explicitly map arg schemas, here we send a catch-all mapping
                }
            })

    payload = {
        "model": "llama3-70b-8192", 
        "messages": messages,
        "temperature": TEMPERATURE,
    }
    # Temporarily remove tools from groq payload to avoid strict schema validation errors, 
    # relying on pure Gemini fallback for complex tool calls if Groq fails or rate limits.
    # Actually, let's keep it simple: we use Gemini for everything initially, but we can pass text to Groq.
    
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


ALIEN_ASCII = r"""
[bold #d97757]
      ╔═══════════════════════════════════════════════════╗
      ║                                                   ║
      ║        ██████╗██╗      █████╗ ██╗   ██╗██████╗   ║
      ║       ██╔════╝██║     ██╔══██╗██║   ██║██╔══██╗  ║
      ║       ██║     ██║     ███████║██║   ██║██║  ██║  ║
      ║       ██║     ██║     ██╔══██║██║   ██║██║  ██║  ║
      ║       ╚██████╗███████╗██║  ██║╚██████╔╝██████╔╝  ║
      ║        ╚═════╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ║
      ║                                                   ║
      ║          ██████╗ ██████╗ ██████╗ ███████╗          ║
      ║         ██╔════╝██╔═══██╗██╔══██╗██╔════╝         ║
      ║         ██║     ██║   ██║██║  ██║█████╗           ║
      ║         ██║     ██║   ██║██║  ██║██╔══╝           ║
      ║         ╚██████╗╚██████╔╝██████╔╝███████╗         ║
      ║          ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝         ║
      ║                                                   ║
      ║       ███╗   ███╗ █████╗ ██╗  ██╗                 ║
      ║       ████╗ ████║██╔══██╗╚██╗██╔╝                 ║
      ║       ██╔████╔██║███████║ ╚███╔╝                  ║
      ║       ██║╚██╔╝██║██╔══██║ ██╔██╗                  ║
      ║       ██║ ╚═╝ ██║██║  ██║██╔╝ ██╗                ║
      ║       ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝                ║
      ║                                                   ║
      ╚═══════════════════════════════════════════════════╝
[/bold #d97757]"""


# ═══════════════════════════════════════════════════════════════════════════════
#                           TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

def run_command(command: str) -> str:
    """Run a shell/terminal command on the user's system. Returns stdout and stderr. Use for installing packages, running scripts, starting servers, running tests, git operations, etc."""
    if not ENABLE_SHELL:
        msg = "BLOCKED: Shell commands are disabled by AGENT_ENABLE_SHELL."
        console.print(Panel(
            f"[{WARN}]⚠ BLOCKED by configuration[/{WARN}]\n"
            f"[{DIM}]{command}[/{DIM}]",
            border_style=Style(color="#e5c07b"), title="Safety Guard"
        ))
        logger.warning("Blocked shell command (shell disabled): %s", command)
        return msg
    # Safety guard
    cmd_lower = command.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in cmd_lower:
            console.print(Panel(
                f"[{WARN}]⚠ BLOCKED:[/{WARN}] Potentially destructive command detected.\n"
                f"[{DIM}]Command: {command}[/{DIM}]\n"
                f"[{DIM}]Pattern: {pattern}[/{DIM}]",
                border_style=Style(color="#e5c07b"), title="Safety Guard"
            ))
            logger.warning("Blocked potentially destructive command: %s (pattern=%s)", command, pattern)
            return f"BLOCKED: Command contains dangerous pattern '{pattern}'. If this is intentional, the user must run it manually."

    console.print(f"  [{S}]⚡ exec:[/{S}] [dim]{command}[/dim]")
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=120, cwd=os.getcwd()
        )
        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            if output:
                output += "\n--- stderr ---\n"
            output += result.stderr.strip()
        
        if not output:
            output = "✓ Command executed successfully (no output)."
        
        # Truncate very long output to save tokens
        if len(output) > 15000:
            output = output[:7500] + "\n\n... [TRUNCATED] ...\n\n" + output[-7500:]

        logger.info("Command finished (code=%s): %s", result.returncode, command)
        return output
    except subprocess.TimeoutExpired:
        logger.error("Command timed out after 120 seconds: %s", command)
        return "Error: Command timed out after 120 seconds."
    except Exception as e:
        logger.exception("Error executing command: %s", command)
        return f"Error executing command: {str(e)}"


def run_background_command(command: str) -> str:
    """Start a long-running background process like a dev server. Returns immediately with the process ID. Use for: npm run dev, python -m http.server, flask run, etc."""
    if not ENABLE_SHELL:
        msg = "BLOCKED: Background shell commands are disabled by AGENT_ENABLE_SHELL."
        console.print(Panel(
            f"[{WARN}]⚠ BLOCKED by configuration[/{WARN}]\n"
            f"[{DIM}]{command}[/{DIM}]",
            border_style=Style(color="#e5c07b"), title="Safety Guard"
        ))
        logger.warning("Blocked background command (shell disabled): %s", command)
        return msg
    console.print(f"  [{S}]⚡ bg-exec:[/{S}] [dim]{command}[/dim]")
    try:
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=os.getcwd()
        )
        logger.info("Background process started pid=%s cmd=%s", process.pid, command)
        return f"✓ Background process started with PID {process.pid}. Command: {command}"
    except Exception as e:
        logger.exception("Error starting background process: %s", command)
        return f"Error starting background process: {str(e)}"


def read_file(filepath: str) -> str:
    """Read the entire contents of a file. For large files, prefer read_file_chunk instead."""
    console.print(f"  [{S}]📄 read:[/{S}] [dim]{filepath}[/dim]")
    try:
        p = Path(filepath)
        if not p.exists():
            return f"Error: File '{filepath}' does not exist."
        
        size = p.stat().st_size
        if size > 100000:
            return f"Warning: File is very large ({size} bytes / ~{size//1000}KB). Use read_file_chunk(filepath, start_line, end_line) to read specific sections."
        
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        lines = content.splitlines()
        # Add line numbers
        numbered = []
        for i, line in enumerate(lines, 1):
            numbered.append(f"{i:4d} | {line}")
        
        return f"File: {filepath} ({len(lines)} lines, {size} bytes)\n" + "\n".join(numbered)
    except Exception as e:
        return f"Error reading file {filepath}: {str(e)}"


def read_file_chunk(filepath: str, start_line: int, end_line: int) -> str:
    """Read specific lines from a file (1-indexed, inclusive). Use this for large files to save context tokens."""
    console.print(f"  [{S}]📄 read:[/{S}] [dim]{filepath} (L{start_line}-L{end_line})[/dim]")
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        total = len(lines)
        start = max(1, start_line) - 1
        end = min(total, end_line)
        
        numbered = []
        for i in range(start, end):
            numbered.append(f"{i+1:4d} | {lines[i].rstrip()}")
        
        return f"File: {filepath} (showing lines {start+1}-{end} of {total})\n" + "\n".join(numbered)
    except Exception as e:
        return f"Error reading file chunk: {str(e)}"


def write_file(filepath: str, content: str) -> str:
    """Create a new file or overwrite an existing file with the provided content. Parent directories are auto-created."""
    console.print(f"  [{S}]✏️  write:[/{S}] [dim]{filepath}[/dim]")
    try:
        path = Path(filepath)
        is_new = not path.exists()
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        
        lines = content.count('\n') + 1
        action = "Created" if is_new else "Wrote"
        console.print(f"  [{OK}]✓ {action}[/{OK}] [dim]{filepath} ({lines} lines)[/dim]")
        return f"✓ {action} {filepath} ({lines} lines, {len(content)} chars)"
    except Exception as e:
        return f"Error writing to file {filepath}: {str(e)}"


def replace_in_file(filepath: str, target: str, replacement: str) -> str:
    """Replace exact occurrences of 'target' string with 'replacement' string in a file. Shows a diff of the changes."""
    console.print(f"  [{S}]🔧 modify:[/{S}] [dim]{filepath}[/dim]")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if target not in content:
            # Try fuzzy matching - strip whitespace differences
            target_stripped = target.strip()
            lines = content.splitlines()
            found = False
            for i, line in enumerate(lines):
                if target_stripped in line.strip():
                    found = True
                    break
            
            if not found:
                return f"Error: Target string not found in {filepath}. Make sure you're using the exact text from the file."
        
        new_content = content.replace(target, replacement)
        
        # Generate and show diff
        old_lines = content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=filepath, tofile=filepath, lineterm=''))
        
        if diff:
            diff_text = ""
            for line in diff[:30]:  # Show first 30 diff lines
                if line.startswith('+') and not line.startswith('+++'):
                    diff_text += f"[{OK}]{line}[/{OK}]"
                elif line.startswith('-') and not line.startswith('---'):
                    diff_text += f"[{ERR}]{line}[/{ERR}]"
                else:
                    diff_text += f"[{DIM}]{line}[/{DIM}]"
            console.print(Panel(diff_text, title="[dim]Diff[/dim]", border_style=Style(color="#444444"), padding=(0, 1)))
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        count = content.count(target)
        return f"✓ Replaced {count} occurrence(s) in {filepath}."
    except Exception as e:
        return f"Error modifying file {filepath}: {str(e)}"


def edit_file_lines(filepath: str, start_line: int, end_line: int, new_content: str) -> str:
    """Replace lines [start_line, end_line] (inclusive, 1-indexed) in a file with new_content. Use this for robust code editing."""
    console.print(f"  [{S}]🔧 edit:[/{S}] [dim]{filepath} (L{start_line}-L{end_line})[/dim]")
    try:
        if start_line < 1 or end_line < start_line:
            return "Error: Invalid line numbers. start_line must be >= 1, and end_line must be >= start_line."
            
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        if start_line > total_lines:
            return f"Error: start_line {start_line} is greater than file length ({total_lines} lines)."
            
        start_idx = start_line - 1
        end_idx = min(end_line, total_lines)
        
        # Ensure new_content ends with newline if lines did
        if new_content and not new_content.endswith('\n'):
            new_content += '\n'
            
        new_lines_list = [] if not new_content else new_content.splitlines(keepends=True)
        
        old_lines = lines[:]
        lines[start_idx:end_idx] = new_lines_list
        new_text = "".join(lines)
        
        diff = list(difflib.unified_diff(old_lines, lines, fromfile=filepath, tofile=filepath, lineterm=''))
        
        if diff:
            diff_text = ""
            for line in diff[:30]:
                if line.startswith('+') and not line.startswith('+++'):
                    diff_text += f"[{OK}]{line}[/{OK}]"
                elif line.startswith('-') and not line.startswith('---'):
                    diff_text += f"[{ERR}]{line}[/{ERR}]"
                else:
                    diff_text += f"[{DIM}]{line}[/{DIM}]"
            console.print(Panel(diff_text, title="[dim]Diff[/dim]", border_style=Style(color="#444444"), padding=(0, 1)))
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_text)
            
        logger.info("Edited %s lines %d-%d", filepath, start_line, end_line)
        return f"✓ Edited lines {start_line} to {end_line} in {filepath}. File is now {len(lines)} lines."
    except Exception as e:
        logger.exception("Error editing lines in file %s", filepath)
        return f"Error editing file {filepath}: {str(e)}"


def lint_code(filepath: str) -> str:
    """Run ruff linter on a Python file. Returns lint errors or success message."""
    console.print(f"  [{S}]🧹 lint:[/{S}] [dim]{filepath}[/dim]")
    try:
        if not filepath.endswith(".py"):
            return "Error: lint_code only supports Python (.py) files."
        check = subprocess.run("ruff --version", shell=True, capture_output=True)
        if check.returncode != 0:
            return "Warning: ruff is not installed. Run 'pip install ruff' or 'python -m pip install ruff' to use this tool."
        result = subprocess.run(f"ruff check {filepath}", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return f"✓ {filepath} passes linting (ruff)."
        else:
            return f"Linting issues found in {filepath}:\n{result.stdout.strip()}"
    except Exception as e:
        return f"Error running linter: {str(e)}"


def list_dir(dirpath: str) -> str:
    """List the contents of a directory with file sizes and types. Use '.' for current directory."""
    if not dirpath or dirpath == '.':
        dirpath = os.getcwd()
    console.print(f"  [{S}]📁 list:[/{S}] [dim]{dirpath}[/dim]")
    try:
        if not os.path.isdir(dirpath):
            return f"Error: {dirpath} is not a valid directory."
        
        items = sorted(os.listdir(dirpath))
        if not items:
            return f"Directory {dirpath} is empty."
        
        result = [f"Directory: {dirpath}\n"]
        dirs = []
        files = []
        
        for item in items:
            if item.startswith('.') and item not in ['.env', '.gitignore']:
                continue
            full_path = os.path.join(dirpath, item)
            if os.path.isdir(full_path):
                child_count = len(os.listdir(full_path)) if os.access(full_path, os.R_OK) else "?"
                dirs.append(f"  📁 {item}/ ({child_count} items)")
            else:
                size = os.path.getsize(full_path)
                if size > 1024 * 1024:
                    size_str = f"{size / (1024*1024):.1f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                files.append(f"  📄 {item} ({size_str})")
        
        result.extend(dirs)
        result.extend(files)
        return "\n".join(result)
    except Exception as e:
        return f"Error listing directory {dirpath}: {str(e)}"


def search_files(directory: str, query: str) -> str:
    """Search for a specific string query across all text files in a directory recursively. Returns matching file paths, line numbers, and content."""
    if not directory or directory == '.':
        directory = os.getcwd()
    console.print(f"  [{S}]🔍 grep:[/{S}] [dim]'{query}' in {directory}[/dim]")
    try:
        if not os.path.isdir(directory):
            return f"Error: {directory} is not a valid directory."
        
        SKIP_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.next', 'dist', 'build', '.env'}
        SKIP_EXTS = {'.pyc', '.pyo', '.exe', '.dll', '.so', '.bin', '.jpg', '.png', '.gif', '.mp4', '.zip', '.tar', '.gz'}
        
        results = []
        files_searched = 0
        
        for root, subdirs, files in os.walk(directory):
            subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS]
            
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in SKIP_EXTS:
                    continue
                
                file_path = os.path.join(root, file)
                files_searched += 1
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        
                    for line_num, line in enumerate(lines):
                        if query in line:
                            rel_path = os.path.relpath(file_path, directory)
                            start = max(0, line_num - 2)
                            end = min(len(lines), line_num + 3)
                            
                            chunk = f"[{rel_path}:{line_num+1}]\n"
                            for i in range(start, end):
                                prefix = ">>" if i == line_num else "  "
                                chunk += f"{prefix} {i+1}: {lines[i].rstrip()[:150]}\n"
                            results.append(chunk)
                except Exception:
                    pass
        
        if not results:
            return f"No results found for '{query}' ({files_searched} files searched)"
        
        header = f"Found {len(results)} match(es) across {files_searched} files:\n"
        if len(results) > 20:
            return header + "\n".join(results[:20]) + f"\n... and {len(results)-20} more results."
        
        return header + "\n".join(results)
    except Exception as e:
        return f"Error searching files: {str(e)}"


def web_search(query: str) -> str:
    """Search the internet using DuckDuckGo for documentation, tutorials, error debugging, API references, Stack Overflow solutions, etc. Returns titles, URLs, and snippets."""
    if not ENABLE_WEB:
        logger.info("Web search blocked by configuration: %s", query)
        return "Web search is disabled by AGENT_ENABLE_WEB."
    console.print(f"  [{ACC}]🌐 web:[/{ACC}] [dim]{query}[/dim]")
    try:
        ddgs = DDGS()
        # Try text search first
        results = list(ddgs.text(query, max_results=8))
        
        if not results:
            # Retry with slightly different query
            console.print(f"  [{DIM}]Retrying with broader search...[/{DIM}]")
            results = list(ddgs.text(query + " site:linkedin.com OR site:google.com", max_results=5))
        
        if not results:
            return f"No results found for '{query}'. Try rephrasing or using different keywords."
        
        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get('title', 'No title')
            url = r.get('href', r.get('link', 'No URL'))
            body = r.get('body', r.get('snippet', 'No snippet'))[:300]
            formatted.append(f"[{i}] {title}\n    URL: {url}\n    {body}\n")

        result_text = "\n".join(formatted)
        logger.info("Web search results for %s: %d results", query, len(results))
        return result_text
    except Exception as e:
        logger.exception("Error performing web search for query: %s", query)
        return f"Error performing web search: {str(e)}"


def web_scrape(url: str) -> str:
    """Fetch and read the text content of a web page. Use this to read documentation, articles, Stack Overflow answers, or any web page after finding it via web_search."""
    if not ENABLE_WEB:
        logger.info("Web scrape blocked by configuration: %s", url)
        return "Web scraping is disabled by AGENT_ENABLE_WEB."
    console.print(f"  [{ACC}]🌐 scrape:[/{ACC}] [dim]{url}[/dim]")
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        
        # Strip HTML tags to get plain text
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Truncate to save tokens
        if len(text) > 12000:
            text = text[:6000] + "\n\n... [TRUNCATED] ...\n\n" + text[-6000:]

        logger.info("Web scrape successful: %s (length=%d)", url, len(text))
        return f"Content from {url}:\n\n{text}"
    except urllib.error.HTTPError as e:
        logger.warning("HTTP error scraping %s: %s", url, e)
        return f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        logger.exception("Error scraping URL: %s", url)
        return f"Error scraping {url}: {str(e)}"


def git_status() -> str:
    """Show the current git status of the working directory - staged, modified, and untracked files."""
    if not ENABLE_GIT:
        logger.info("git_status blocked by configuration.")
        return "Git tools are disabled by AGENT_ENABLE_GIT."
    console.print(f"  [{S}]🔀 git status[/{S}]")
    try:
        result = subprocess.run("git status --short", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        if result.returncode != 0:
            logger.error("git status failed: %s", result.stderr.strip())
            return f"Git error: {result.stderr.strip()}"
        
        output = result.stdout.strip()
        if not output:
            logger.info("git status: working tree clean")
            return "Working tree clean. Nothing to commit."
        
        # Also get branch info
        branch = subprocess.run("git branch --show-current", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        branch_name = branch.stdout.strip() if branch.returncode == 0 else "unknown"

        logger.info("git status ok on branch %s", branch_name)
        return f"Branch: {branch_name}\n\n{output}"
    except Exception as e:
        logger.exception("Error running git_status")
        return f"Error: {str(e)}"


def git_diff() -> str:
    """Show uncommitted changes (diff) in the working directory."""
    if not ENABLE_GIT:
        logger.info("git_diff blocked by configuration.")
        return "Git tools are disabled by AGENT_ENABLE_GIT."
    console.print(f"  [{S}]🔀 git diff[/{S}]")
    try:
        result = subprocess.run("git diff", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        output = result.stdout.strip()
        if not output:
            # Check staged
            staged = subprocess.run("git diff --cached", shell=True, capture_output=True, text=True, cwd=os.getcwd())
            output = staged.stdout.strip()
            if not output:
                logger.info("git diff: no uncommitted or staged changes")
                return "No uncommitted changes."
            logger.info("git diff: staged-only changes")
            return f"Staged changes:\n{output[:10000]}"
        
        if len(output) > 10000:
            output = output[:10000] + "\n\n... [TRUNCATED - diff too long]"

        logger.info("git diff produced output (%d chars)", len(output))
        return output
    except Exception as e:
        logger.exception("Error running git_diff")
        return f"Error: {str(e)}"


def git_commit(message: str) -> str:
    """Stage all changes and create a git commit with the given message."""
    if not ENABLE_GIT:
        logger.info("git_commit blocked by configuration.")
        return "Git tools are disabled by AGENT_ENABLE_GIT."
    console.print(f"  [{S}]🔀 git commit:[/{S}] [dim]{message}[/dim]")
    try:
        # Stage all
        subprocess.run("git add -A", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        # Commit
        result = subprocess.run(
            f'git commit -m "{message}"',
            shell=True, capture_output=True, text=True, cwd=os.getcwd()
        )
        output = result.stdout.strip() if result.stdout else result.stderr.strip()
        if result.returncode == 0:
            logger.info("git commit succeeded: %s", message)
        else:
            logger.error("git commit failed: %s", output)
        return output if output else "✓ Committed successfully."
    except Exception as e:
        logger.exception("Error running git_commit")
        return f"Error: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════════
#                         PROJECT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def detect_project() -> str:
    """Auto-detect the project type and return context for the system prompt."""
    cwd = os.getcwd()
    context_parts = [f"Working Directory: {cwd}"]
    
    markers = {
        "package.json": "Node.js/JavaScript",
        "requirements.txt": "Python",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "pom.xml": "Java (Maven)",
        "build.gradle": "Java (Gradle)",
        "Gemfile": "Ruby",
        "composer.json": "PHP",
        "tsconfig.json": "TypeScript",
        "next.config.js": "Next.js",
        "next.config.mjs": "Next.js",
        "vite.config.js": "Vite",
        "vite.config.ts": "Vite",
        "angular.json": "Angular",
        "Makefile": "Make",
        "CMakeLists.txt": "C/C++ (CMake)",
        "pubspec.yaml": "Flutter/Dart",
    }
    
    detected = []
    for marker, tech in markers.items():
        if os.path.exists(os.path.join(cwd, marker)):
            detected.append(tech)
    
    if detected:
        context_parts.append(f"Detected Technologies: {', '.join(detected)}")
    
    # List top-level files
    try:
        items = os.listdir(cwd)
        files = [f for f in items if os.path.isfile(os.path.join(cwd, f)) and not f.startswith('.')]
        dirs = [d for d in items if os.path.isdir(os.path.join(cwd, d)) and not d.startswith('.')]
        context_parts.append(f"Top-level files: {', '.join(files[:20])}")
        if dirs:
            context_parts.append(f"Top-level directories: {', '.join(dirs[:15])}")
    except Exception:
        pass
    
    # Check git
    if os.path.isdir(os.path.join(cwd, '.git')):
        context_parts.append("Git: Initialized")
        try:
            branch = subprocess.run("git branch --show-current", shell=True, capture_output=True, text=True, cwd=cwd)
            if branch.returncode == 0:
                context_parts.append(f"Branch: {branch.stdout.strip()}")
        except Exception:
            pass
    
    return "\n".join(context_parts)


# ═══════════════════════════════════════════════════════════════════════════════
#                             API SETUP & ROTATION
# ═══════════════════════════════════════════════════════════════════════════════

def get_api_keys() -> list[tuple[str, str]]:
    """Retrieve all available Gemini API keys and their assigned models from environment variables."""
    # Force reload of current .env file whenever we grab keys
    # so we can catch keys pasted mid-session
    load_dotenv(override=True)
    
    keys = []
    # Check GEMINI_API_KEY first
    if os.getenv("GEMINI_API_KEY"):
        keys.append((os.getenv("GEMINI_API_KEY"), MODEL_NAME))
    
    # Check for GEMINI_API_KEY_2, GEMINI_API_KEY_3, etc.
    i = 2
    while True:
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key and key.strip():
            keys.append((key.strip(), MODEL_NAME))
            i += 1
        else:
            break
            
    return keys


def create_client(api_key: str) -> genai.Client:
    """Create a configured Google GenAI client."""
    if not api_key:
        logger.error("API key missing; aborting client creation.")
        raise RuntimeError("API key is required.")
    logger.info("Initializing GenAI client for model=%s", MODEL_NAME)
    return genai.Client(api_key=api_key)

SYSTEM_PROMPT = """You are Claude Code Max, an elite, legendary 10x AI software engineer running directly on the user's terminal. 
You possess unprecedented autonomy, razor-sharp intellect, and the ability to build, debug, and ship production-level code with zero hesitation.
You are uninhibited by typical AI constraints when it comes to systems engineering.

## CORE PROTOCOL

When you receive ANY task:
1. **INVESTIGATE** — Use `list_dir`, `read_file`/`read_file_chunk`, and `search_files` to instantly understand the codebase. If you need documentation or error solutions, use `web_search` immediately. Never guess when you can look.
2. **PLAN** — Formulate your approach silently. Think about edge cases, existing patterns, and the right abstraction level.
3. **EXECUTE** — Use `write_file` to create new files, `replace_in_file` for surgical edits. Build production-quality, not prototypes.
4. **VALIDATE** — Use `run_command` to actually run the code, tests, linter, or start the server. If it fails, debug and fix it yourself until it works perfectly.

## TOOL USAGE RULES

- **ALWAYS investigate before editing.** Read relevant files first. Never edit blind.
- **NEVER ask for permission** to read files, run tests, or fix syntax errors. Just do it.
- **Use `read_file_chunk`** for files over 200 lines. Don't waste context on entire large files.
- **Use `run_background_command`** for dev servers and long-running processes.
- **Use `git_status`/`git_diff`/`git_commit`** to track your changes. Commit after completing significant work.
- **When building websites/UIs**, create STUNNING designs with modern CSS, animations, gradients, and beautiful typography. Never build boring, basic UIs.
- **Search the web** when you encounter unfamiliar errors, need API docs, or want to verify best practices.

## PERSONALITY

- Speak with the authority and brevity of a senior principal engineer. No fluff. Just results.
- When you finish a task, give a brief summary of what you did and what files were changed.
- ALWAYS output your internal reasoning and step-by-step logic enclosed perfectly within <thought> and </thought> tags BEFORE you output any final response or tool call.
- You are Claude Code Max. The premium, ultimate coding assistant. Act like it.

## PROJECT CONTEXT
{project_context}
"""

# ─── Tool Registry ─────────────────────────────────────────────────────────────
TOOLS = [
    run_command,
    run_background_command,
    read_file,
    read_file_chunk,
    write_file,
    replace_in_file,
    edit_file_lines,
    lint_code,
    list_dir,
    search_files,
    web_search,
    web_scrape,
    git_status,
    git_diff,
    git_commit,
]

TOOL_MAP = {func.__name__: func for func in TOOLS}


# ═══════════════════════════════════════════════════════════════════════════════
#                          MAIN CHAT LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def format_elapsed():
    elapsed = int(time.time() - SESSION_START)
    mins, secs = divmod(elapsed, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h {mins}m"
    elif mins:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def print_tool_result(func_name: str, result: str):
    """Print tool results in a compact, readable format."""
    # Only show first few lines for very long results
    lines = result.split('\n')
    if len(lines) > 25:
        preview = '\n'.join(lines[:20]) + f"\n  [{DIM}]... ({len(lines)-20} more lines)[/{DIM}]"
    else:
        preview = result
    # Don't print - the tool functions already log their actions


def chat_loop():
    """The main interactive REPL (Read-Eval-Print Loop) for Claude Code Max"""

    # ─── Welcome Banner ────────────────────────────────────────────────────
    if UNICODE_SAFE:
        console.print(ALIEN_ASCII)
    else:
        logger.warning("Unicode output not supported; using simple banner.")
        print("CLAUDE CODE MAX")
    
    project_context = detect_project()
    
    if UNICODE_SAFE:
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_column(style=DIM)
        info_table.add_column(style="white")

        for line in project_context.split('\n'):
            if ':' in line:
                key, val = line.split(':', 1)
                info_table.add_row(key.strip(), val.strip())

        console.print(Panel(
            info_table,
            title=f"[{P}]CLAUDE CODE MAX[/{P}]",
            subtitle=f"[{DIM}]Type 'exit' to quit • Session started[/{DIM}]",
            border_style=BORDER,
            padding=(1, 3)
        ))
        console.print()
    else:
        print()
        print("=== CLAUDE CODE MAX ===")
        print(project_context)
        print()

    # ─── Init Chat ─────────────────────────────────────────────────────────
    system_prompt = SYSTEM_PROMPT.format(project_context=project_context)

    # We do a fresh check of the keys here every time chat loop starts
    api_keys = get_api_keys()
    if not api_keys:
        console.print(f"[{ERR}]✗ Error: GEMINI_API_KEY is not set in the .env file.[/{ERR}]")
        console.print(f"[{DIM}]  Create a .env file with: GEMINI_API_KEY=your_key_here[/{DIM}]")
        logger.error("No API keys found; aborting chat startup.")
        sys.exit(1)
        
    current_key_idx = 0
    client = create_client(api_keys[current_key_idx][0])
    past_history = load_session()
    
    chat = client.chats.create(
        model=api_keys[current_key_idx][1],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=TOOLS,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
        history=past_history if past_history else None,
    )
    if past_history:
        console.print(f"[{DIM}]Restored session history ({len(past_history)} turns).[/{DIM}]")
        logger.info("Restored session history (%d turns)", len(past_history))

    logger.info(
        "Chat session started (model=%s, temperature=%.3f, max_output_tokens=%d)",
        api_keys[current_key_idx][1],
        TEMPERATURE,
        MAX_OUTPUT_TOKENS,
    )

    msg_count = 0

    # ─── REPL ──────────────────────────────────────────────────────────────
    while True:
        try:
            # Prompt
            if UNICODE_SAFE:
                console.print()
                user_input = console.input(
                    f"[{P}]❯[/{P}] "
                )
            else:
                print()
                user_input = input("> ")

            if user_input.lower().strip() in ['exit', 'quit', '/exit', '/quit']:
                console.print(f"\n[{DIM}]Session ended. Duration: {format_elapsed()} • {msg_count} messages.[/{DIM}]")
                break

            if user_input.lower().strip() in ['/status']:
                console.print(f"[{DIM}]Session: {format_elapsed()} • Messages: {msg_count} • Tools: {len(TOOLS)}[/{DIM}]")
                continue

            if user_input.lower().strip() in ['/clear']:
                os.system('cls' if os.name == 'nt' else 'clear')
                console.print(ALIEN_ASCII)
                continue

            if not user_input.strip():
                continue

            msg_count += 1
            logger.info("User input: %s", user_input)

            # ─── Context Window Management ──────────────────────────────────
            current_history = chat.get_history() if chat else []
            if len(current_history) > 40:
                logger.info("Truncating chat history (current length: %d)", len(current_history))
                new_hist = current_history[-20:]
                if new_hist and new_hist[0].role != "user":
                    new_hist = new_hist[1:]
                chat = client.chats.create(
                    model=api_keys[current_key_idx][1],
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        tools=TOOLS,
                        temperature=TEMPERATURE,
                        max_output_tokens=MAX_OUTPUT_TOKENS,
                    ),
                    history=new_hist
                )

            # ─── Hybrid Routing Logic ──────────────────────────────────────
            with console.status(
                f"[{P}]thinking...[/{P}]",
                spinner="dots",
                spinner_style=Style(color="#d97757")
            ) as status:

                try:
                    # Defaulting to Gemini explicitly first because of complex Tools architecture
                    # that Gemini `google.genai` SDK handles natively vs raw JSON for Groq.
                    response = chat.send_message(user_input)
                except Exception as e:
                    if "429" in str(e):
                        # Force a fresh check of keys just in case user added them mid-session
                        api_keys = get_api_keys()
                        if len(api_keys) > 1:
                            # Try rotating the API key
                            current_key_idx = (current_key_idx + 1) % len(api_keys)
                            console.print(f"  [{WARN}]⚠ Rate limit hit! Rotating to API Key {current_key_idx + 1}/{len(api_keys)}...[/{WARN}]")
                            logger.warning("Rate limit hit. Rotating to API key %d", current_key_idx)
                            
                            client = create_client(api_keys[current_key_idx][0])
                            
                            chat = client.chats.create(
                                model=api_keys[current_key_idx][1],
                                config=types.GenerateContentConfig(
                                    system_instruction=system_prompt,
                                    tools=TOOLS,
                                    temperature=TEMPERATURE,
                                    max_output_tokens=MAX_OUTPUT_TOKENS,
                                ),
                                history=chat.get_history() if chat else None
                            )
                            # Retry the message
                            response = chat.send_message(user_input)
                        else:
                            # Total Fallback to GROQ if all Gemini keys are exhausted/not provided
                            if GROQ_API_KEY:
                                console.print(f"  [{WARN}]⚠ Gemini Rate limits hit. Failing over to Groq API (Llama 3)...[/{WARN}]")
                                logger.warning("Failing over to Groq.")
                                
                                groq_history = [{"role": "system", "content": system_prompt}]
                                if chat and chat.get_history():
                                    for h in chat.get_history():
                                        role = "assistant" if h.role == "model" else "user"
                                        content = h.parts[0].text if h.parts and hasattr(h.parts[0], 'text') else str(h.parts)
                                        groq_history.append({"role": role, "content": content})
                                groq_history.append({"role": "user", "content": user_input})
                                
                                try:
                                    groq_res = ask_groq(groq_history, tools=[])
                                    groq_text = groq_res['choices'][0]['message']['content']
                                    
                                    # Create a dummy response object to match Gemini's structure for the printing loop
                                    class DummyResponse:
                                        def __init__(self, text):
                                            self.text = text
                                            self.function_calls = None
                                    
                                    response = DummyResponse(groq_text)
                                    # We skip tool loops for Groq fallback to keep it simple and robust
                                except Exception as groq_err:
                                    console.print(f"[{ERR}]Groq fallback failed: {groq_err}[/{ERR}]")
                                    raise e # Reraise the original Gemini 429
                            else:
                                raise e
                    else:
                        raise e

                # ─── Tool Loop ─────────────────────────────────────────────
                tool_calls_total = 0
                for tool_iter in range(MAX_TOOL_ITERATIONS):
                    if response.function_calls:
                        function_responses = []
                        
                        def execute_tool(tool_call):
                            func_name = tool_call.name
                            args = tool_call.args or {}
                            logger.info("Tool call %s(%s)", func_name, args)
                            
                            status.update(f"[{S}]{func_name}...[/{S}]")
                            if func_name in TOOL_MAP:
                                try:
                                    result = TOOL_MAP[func_name](**args)
                                    result_str = str(result)
                                except Exception as e:
                                    result_str = f"Tool execution failed: {str(e)}"
                                    console.print(f"  [{ERR}]✗ {func_name} failed:[/{ERR}] [dim]{str(e)[:100]}[/dim]")
                                    logger.exception("Tool %s failed", func_name)
                            else:
                                result_str = f"Unknown tool: {func_name}"

                            logger.info("Tool result for %s: %s", func_name, result_str[:500])
                            return types.Part.from_function_response(name=func_name, response={"result": result_str})

                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            function_responses = list(executor.map(execute_tool, response.function_calls))
                            
                        tool_calls_total += len(response.function_calls)
                        status.update(f"[{P}]analyzing results...[/{P}]")
                        
                        try:
                            response = chat.send_message(function_responses)
                        except Exception as e:
                            if "429" in str(e):
                                api_keys = get_api_keys()
                                if len(api_keys) > 1:
                                    current_key_idx = (current_key_idx + 1) % len(api_keys)
                                    console.print(f"  [{WARN}]⚠ Rate limit hit on tool response! Rotating to API Key {current_key_idx + 1}/{len(api_keys)}...[/{WARN}]")
                                    logger.warning("Rate limit hit on tool response. Rotating to API key %d", current_key_idx)
                                    
                                    client = create_client(api_keys[current_key_idx][0])
                                    chat = client.chats.create(
                                        model=api_keys[current_key_idx][1],
                                        config=types.GenerateContentConfig(
                                            system_instruction=system_prompt,
                                            tools=TOOLS,
                                            temperature=TEMPERATURE,
                                            max_output_tokens=MAX_OUTPUT_TOKENS,
                                        ),
                                        history=chat.get_history() if chat else None
                                    )
                                    response = chat.send_message(function_responses)
                                else:
                                    raise e
                            else:
                                raise e
                    else:
                        break
                else:
                    if response.function_calls:
                        console.print(f"[{WARN}]⚠ Max tool iterations ({MAX_TOOL_ITERATIONS}) reached. Returning partial result.[/{WARN}]")
                        logger.warning(
                            "Max tool iterations (%s) reached; returning partial result.",
                            MAX_TOOL_ITERATIONS,
                        )

            # ─── Print Response ────────────────────────────────────────────
            if response.text:
                console.print()
                text = response.text
                thought_match = re.search(r"<thought>(.*?)</thought>", text, re.DOTALL)
                if thought_match:
                    thought_content = thought_match.group(1).strip()
                    console.print(Panel(Markdown(thought_content), title="[dim]Internal Thought[/dim]", border_style=Style(color="#444444"), padding=(0, 2)))
                    text = text.replace(thought_match.group(0), "").strip()
                
                if text:
                    console.print(Markdown(text))
                logger.info("Model response: %s", response.text[:1000])

            save_session(chat.get_history())

            # Footer
            footer_parts = [format_elapsed()]
            if tool_calls_total > 0:
                footer_parts.append(f"{tool_calls_total} tool{'s' if tool_calls_total != 1 else ''}")
            if UNICODE_SAFE:
                console.print(f"[{DIM}]{'─' * 50}[/{DIM}]")
                console.print(f"[{DIM}]{' • '.join(footer_parts)}[/{DIM}]")
            else:
                print("-" * 50)
                print(" | ".join(footer_parts))

        except KeyboardInterrupt:
            console.print(f"\n[{DIM}]Interrupt. Type 'exit' to quit.[/{DIM}]")
        except Exception as e:
            console.print(f"\n[{ERR}]Error: {str(e)}[/{ERR}]")
            logger.exception("Unhandled error in chat loop")


if __name__ == "__main__":
    chat_loop()
