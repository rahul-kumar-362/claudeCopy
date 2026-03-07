import os
import sys
import subprocess
import glob
import time
import difflib
import shutil
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
import json
import re

# ─── Environment ───────────────────────────────────────────────────────────────
load_dotenv()

# ─── Rich Console ──────────────────────────────────────────────────────────────
console = Console(highlight=False)

# ─── Premium Color Palette ─────────────────────────────────────────────────────
P = "bold #d97757"       # Primary Coral
S = "#e5c07b"            # Secondary Gold
DIM = "dim #888888"      # Muted
ACC = "bold #56b6c2"     # Accent Cyan
OK = "bold #98c379"      # Success Green
ERR = "bold #e06c75"     # Error Red
WARN = "bold #e5c07b"    # Warning Yellow
BORDER = Style(color="#d97757", dim=True)

# ─── Dangerous Commands ────────────────────────────────────────────────────────
DANGEROUS_PATTERNS = [
    "rm -rf", "rmdir", "del /", "format ", "drop table", "drop database",
    "truncate ", "shutdown", "mkfs", "dd if=", ":(){", "deltree",
    "Remove-Item", "Clear-Content"
]

# ─── Session Tracking ─────────────────────────────────────────────────────────
SESSION_START = time.time()
TOKEN_COUNTER = {"input": 0, "output": 0}

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
        
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds."
    except Exception as e:
        return f"Error executing command: {str(e)}"


def run_background_command(command: str) -> str:
    """Start a long-running background process like a dev server. Returns immediately with the process ID. Use for: npm run dev, python -m http.server, flask run, etc."""
    console.print(f"  [{S}]⚡ bg-exec:[/{S}] [dim]{command}[/dim]")
    try:
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=os.getcwd()
        )
        return f"✓ Background process started with PID {process.pid}. Command: {command}"
    except Exception as e:
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
                        for line_num, line in enumerate(f, 1):
                            if query in line:
                                rel_path = os.path.relpath(file_path, directory)
                                results.append(f"  {rel_path}:{line_num}: {line.strip()[:120]}")
                except Exception:
                    pass
        
        if not results:
            return f"No results found for '{query}' ({files_searched} files searched)"
        
        header = f"Found {len(results)} match(es) across {files_searched} files:\n"
        if len(results) > 50:
            return header + "\n".join(results[:50]) + f"\n  ... and {len(results)-50} more results."
        
        return header + "\n".join(results)
    except Exception as e:
        return f"Error searching files: {str(e)}"


def web_search(query: str) -> str:
    """Search the internet using DuckDuckGo for documentation, tutorials, error debugging, API references, Stack Overflow solutions, etc. Returns titles, URLs, and snippets."""
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
        
        return "\n".join(formatted)
    except Exception as e:
        return f"Error performing web search: {str(e)}"


def web_scrape(url: str) -> str:
    """Fetch and read the text content of a web page. Use this to read documentation, articles, Stack Overflow answers, or any web page after finding it via web_search."""
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
        
        return f"Content from {url}:\n\n{text}"
    except urllib.error.HTTPError as e:
        return f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        return f"Error scraping {url}: {str(e)}"


def git_status() -> str:
    """Show the current git status of the working directory - staged, modified, and untracked files."""
    console.print(f"  [{S}]🔀 git status[/{S}]")
    try:
        result = subprocess.run("git status --short", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        if result.returncode != 0:
            return f"Git error: {result.stderr.strip()}"
        
        output = result.stdout.strip()
        if not output:
            return "Working tree clean. Nothing to commit."
        
        # Also get branch info
        branch = subprocess.run("git branch --show-current", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        branch_name = branch.stdout.strip() if branch.returncode == 0 else "unknown"
        
        return f"Branch: {branch_name}\n\n{output}"
    except Exception as e:
        return f"Error: {str(e)}"


def git_diff() -> str:
    """Show uncommitted changes (diff) in the working directory."""
    console.print(f"  [{S}]🔀 git diff[/{S}]")
    try:
        result = subprocess.run("git diff", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        output = result.stdout.strip()
        if not output:
            # Check staged
            staged = subprocess.run("git diff --cached", shell=True, capture_output=True, text=True, cwd=os.getcwd())
            output = staged.stdout.strip()
            if not output:
                return "No uncommitted changes."
            return f"Staged changes:\n{output[:10000]}"
        
        if len(output) > 10000:
            output = output[:10000] + "\n\n... [TRUNCATED - diff too long]"
        
        return output
    except Exception as e:
        return f"Error: {str(e)}"


def git_commit(message: str) -> str:
    """Stage all changes and create a git commit with the given message."""
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
        return output if output else "✓ Committed successfully."
    except Exception as e:
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
#                             API SETUP
# ═══════════════════════════════════════════════════════════════════════════════

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    console.print(f"[{ERR}]✗ Error: GEMINI_API_KEY is not set in the .env file.[/{ERR}]")
    console.print(f"[{DIM}]  Create a .env file with: GEMINI_API_KEY=your_key_here[/{DIM}]")
    sys.exit(1)

client = genai.Client(api_key=api_key)

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
    console.print(ALIEN_ASCII)
    
    project_context = detect_project()
    
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

    # ─── Init Chat ─────────────────────────────────────────────────────────
    system_prompt = SYSTEM_PROMPT.format(project_context=project_context)

    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=TOOLS,
            temperature=0.2,
        )
    )

    msg_count = 0

    # ─── REPL ──────────────────────────────────────────────────────────────
    while True:
        try:
            # Prompt
            console.print()
            user_input = console.input(
                f"[{P}]❯[/{P}] "
            )

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

            # ─── Send to Gemini ────────────────────────────────────────────
            with console.status(
                f"[{P}]thinking...[/{P}]",
                spinner="dots",
                spinner_style=Style(color="#d97757")
            ) as status:

                response = chat.send_message(user_input)

                # ─── Tool Loop ─────────────────────────────────────────────
                tool_calls_total = 0
                while True:
                    if response.function_calls:
                        function_responses = []
                        for tool_call in response.function_calls:
                            func_name = tool_call.name
                            args = tool_call.args or {}
                            tool_calls_total += 1

                            status.update(f"[{S}]{func_name}...[/{S}]")

                            if func_name in TOOL_MAP:
                                try:
                                    result = TOOL_MAP[func_name](**args)
                                    result_str = str(result)
                                except Exception as e:
                                    result_str = f"Tool execution failed: {str(e)}"
                                    console.print(f"  [{ERR}]✗ {func_name} failed:[/{ERR}] [dim]{str(e)[:100]}[/dim]")
                            else:
                                result_str = f"Unknown tool: {func_name}"

                            function_responses.append(
                                types.Part.from_function_response(
                                    name=func_name,
                                    response={"result": result_str}
                                )
                            )

                        status.update(f"[{P}]analyzing results...[/{P}]")
                        response = chat.send_message(function_responses)
                    else:
                        break

            # ─── Print Response ────────────────────────────────────────────
            if response.text:
                console.print()
                console.print(Markdown(response.text))

            # Footer
            footer_parts = [format_elapsed()]
            if tool_calls_total > 0:
                footer_parts.append(f"{tool_calls_total} tool{'s' if tool_calls_total != 1 else ''}")
            console.print(f"[{DIM}]{'─' * 50}[/{DIM}]")
            console.print(f"[{DIM}]{' • '.join(footer_parts)}[/{DIM}]")

        except KeyboardInterrupt:
            console.print(f"\n[{DIM}]Interrupt. Type 'exit' to quit.[/{DIM}]")
        except Exception as e:
            console.print(f"\n[{ERR}]Error: {str(e)}[/{ERR}]")


if __name__ == "__main__":
    chat_loop()
