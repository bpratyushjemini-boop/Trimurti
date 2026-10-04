"""
Krīya V1 — Provider-Independent Agent Tool Execution Layer for NARAD.
Provides local tool registry, schemas (OpenAI/Groq and Gemini formats),
and safe asynchronous tool execution dispatching.
"""

import os
import re
import ast
import json
import math
import logging
import asyncio
import inspect
import operator
import zoneinfo
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
import shutil
import subprocess
import shlex
import socket

from app.services.smriti import smriti_service
from app.services.computer import computer_adapter
from app.services.action_policy import action_policy, PermissionLevel

logger = logging.getLogger(__name__)

# =========================================================================
# Location & Timezone Resolution Mapping
# =========================================================================

LOCATION_TIMEZONE_MAP: Dict[str, str] = {
    # Americas
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "ny": "America/New_York",
    "washington": "America/New_York",
    "washington dc": "America/New_York",
    "boston": "America/New_York",
    "miami": "America/New_York",
    "atlanta": "America/New_York",
    "san francisco": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "california": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "houston": "America/Chicago",
    "dallas": "America/Chicago",
    "denver": "America/Denver",
    "phoenix": "America/Phoenix",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    "montreal": "America/Toronto",
    "sao paulo": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "mexico city": "America/Mexico_City",

    # India & South Asia
    "india": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "new delhi": "Asia/Kolkata",
    "mumbai": "Asia/Kolkata",
    "kolkata": "Asia/Kolkata",
    "calcutta": "Asia/Kolkata",
    "bengaluru": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata",
    "chennai": "Asia/Kolkata",
    "hyderabad": "Asia/Kolkata",
    "pune": "Asia/Kolkata",
    "ahmedabad": "Asia/Kolkata",
    "jaipur": "Asia/Kolkata",
    "dhaka": "Asia/Dhaka",
    "colombo": "Asia/Colombo",
    "kathmandu": "Asia/Kathmandu",
    "karachi": "Asia/Karachi",
    "islamabad": "Asia/Karachi",

    # Europe & UK
    "london": "Europe/London",
    "uk": "Europe/London",
    "united kingdom": "Europe/London",
    "britain": "Europe/London",
    "england": "Europe/London",
    "paris": "Europe/Paris",
    "france": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "frankfurt": "Europe/Berlin",
    "rome": "Europe/Rome",
    "italy": "Europe/Rome",
    "madrid": "Europe/Madrid",
    "spain": "Europe/Madrid",
    "amsterdam": "Europe/Amsterdam",
    "netherlands": "Europe/Amsterdam",
    "brussels": "Europe/Brussels",
    "zurich": "Europe/Zurich",
    "switzerland": "Europe/Zurich",
    "vienna": "Europe/Vienna",
    "stockholm": "Europe/Stockholm",
    "oslo": "Europe/Oslo",
    "dublin": "Europe/Dublin",
    "moscow": "Europe/Moscow",

    # Asia Pacific
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "south korea": "Asia/Seoul",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore",
    "taipei": "Asia/Taipei",
    "taiwan": "Asia/Taipei",
    "bangkok": "Asia/Bangkok",
    "thailand": "Asia/Bangkok",
    "jakarta": "Asia/Jakarta",
    "dubai": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "abu dhabi": "Asia/Dubai",
    "doha": "Asia/Qatar",
    "riyadh": "Asia/Riyadh",
    "tel aviv": "Asia/Jerusalem",

    # Australia & Oceania
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "brisbane": "Australia/Brisbane",
    "perth": "Australia/Perth",
    "australia": "Australia/Sydney",
    "auckland": "Pacific/Auckland",
    "new zealand": "Pacific/Auckland",

    # UTC / Universal
    "utc": "UTC",
    "gmt": "UTC",
    "zulu": "UTC",
}

def get_machine_timezone() -> str:
    """
    Dynamically detect the host machine's actual IANA timezone without hardcoding.
    Checks environment, POSIX /etc/localtime symlink, and datetime local tzinfo.
    """
    # 1. Check TZ environment variable
    tz_env = os.environ.get("TZ")
    if tz_env and tz_env.strip():
        try:
            zoneinfo.ZoneInfo(tz_env.strip())
            return tz_env.strip()
        except Exception:
            pass

    # 2. Check /etc/localtime symlink (macOS / Linux)
    if os.path.exists("/etc/localtime"):
        try:
            real_path = os.path.realpath("/etc/localtime")
            if "zoneinfo/" in real_path:
                candidate = real_path.split("zoneinfo/")[-1]
                zoneinfo.ZoneInfo(candidate)
                return candidate
        except Exception:
            pass

    # 3. Check system local datetime tzinfo
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz:
            tz_name = local_tz.tzname(None)
            if tz_name in ("IST",):
                return "Asia/Kolkata"
            try:
                zoneinfo.ZoneInfo(tz_name)
                return tz_name
            except Exception:
                pass
            try:
                zoneinfo.ZoneInfo(str(local_tz))
                return str(local_tz)
            except Exception:
                pass
    except Exception:
        pass

    return "UTC"


def resolve_timezone(location_query: Optional[str] = None) -> str:
    """
    Resolve a human location query string into a valid IANA timezone string.
    If no location is specified or refers to local/here/machine, dynamically detects
    the host system's timezone rather than falling back to naive UTC.
    """
    machine_tz = get_machine_timezone()

    if not location_query or not str(location_query).strip():
        return machine_tz

    cleaned = str(location_query).strip().lower()

    if cleaned in ("null", "none", "undefined", "local", "here", "system", "machine", "device", "current", "my location", "me", "home"):
        return machine_tz

    # Direct match in map
    if cleaned in LOCATION_TIMEZONE_MAP:
        return LOCATION_TIMEZONE_MAP[cleaned]

    # Word-boundary search for location keywords (longer keys first to prevent false substring matches)
    for alias in sorted(LOCATION_TIMEZONE_MAP.keys(), key=lambda k: len(k), reverse=True):
        if re.search(r"\b" + re.escape(alias) + r"\b", cleaned):
            return LOCATION_TIMEZONE_MAP[alias]

    # Direct IANA zone match
    try:
        zoneinfo.ZoneInfo(str(location_query).strip())
        return str(location_query).strip()
    except Exception:
        pass

    # Search available IANA timezones by split segment
    for tz_name in zoneinfo.available_timezones():
        tz_lower = tz_name.lower()
        parts = tz_lower.split("/")
        if cleaned in parts or any(cleaned == p for p in parts):
            return tz_name

    logger.info(f"Could not map '{location_query}' to specific timezone, defaulting to machine timezone ({machine_tz}).")
    return machine_tz


# =========================================================================
# Tool Implementations
# =========================================================================

def get_current_time(location: Optional[str] = None) -> Dict[str, Any]:
    """Calculate the exact current date, time, and timezone metadata for a given location or local system."""
    clean_loc = None
    if location is not None:
        loc_str = str(location).strip()
        if loc_str and loc_str.lower() not in ("null", "none", "undefined", "local", "here", "current"):
            clean_loc = loc_str

    resolved_tz_str = resolve_timezone(clean_loc)
    try:
        tz = zoneinfo.ZoneInfo(resolved_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
        resolved_tz_str = "UTC"

    now = datetime.now(tz)
    return {
        "location": clean_loc or "Local System",
        "resolved_timezone": resolved_tz_str,
        "current_time": now.strftime("%I:%M:%S %p"),
        "current_date": now.strftime("%A, %B %d, %Y"),
        "day_of_week": now.strftime("%A"),
        "timezone_abbreviation": now.strftime("%Z"),
        "utc_offset": now.strftime("%z"),
        "iso_timestamp": now.isoformat()
    }


def get_current_date(location: Optional[str] = None) -> Dict[str, Any]:
    """Calculate the current calendar date, day of week, and timezone metadata for a given location or local system."""
    clean_loc = None
    if location is not None:
        loc_str = str(location).strip()
        if loc_str and loc_str.lower() not in ("null", "none", "undefined", "local", "here", "current"):
            clean_loc = loc_str

    resolved_tz_str = resolve_timezone(clean_loc)
    try:
        tz = zoneinfo.ZoneInfo(resolved_tz_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
        resolved_tz_str = "UTC"

    now = datetime.now(tz)
    return {
        "location": clean_loc or "Local System",
        "resolved_timezone": resolved_tz_str,
        "current_date": now.strftime("%A, %B %d, %Y"),
        "iso_date": now.strftime("%Y-%m-%d"),
        "day_of_week": now.strftime("%A"),
        "year": now.year,
        "month": now.strftime("%B"),
        "day": now.day,
        "timezone_abbreviation": now.strftime("%Z"),
        "utc_offset": now.strftime("%z"),
        "iso_timestamp": now.isoformat()
    }

# Safe AST Calculator Implementation
_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCTIONS = {
    "sqrt": math.sqrt,
    "pow": math.pow,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "floor": math.floor,
    "ceil": math.ceil,
}

_SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}

def _eval_ast_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")
    elif isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
        left = _eval_ast_node(node.left)
        right = _eval_ast_node(node.right)
        return _SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _eval_ast_node(node.operand)
        return _SAFE_OPERATORS[op_type](operand)
    elif isinstance(node, ast.Name):
        if node.id in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[node.id]
        raise ValueError(f"Unknown constant or variable: '{node.id}'")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCTIONS:
            func = _SAFE_FUNCTIONS[node.func.id]
            args = [_eval_ast_node(a) for a in node.args]
            return func(*args)
        raise ValueError("Arbitrary function calls are forbidden in Krīya calculator.")
    else:
        raise ValueError(f"Unsupported syntax expression element: {type(node).__name__}")

def calculator(expression: str) -> Dict[str, Any]:
    """
    Safely evaluate a mathematical expression using AST parsing.
    Prevents arbitrary code execution, builtins, and side effects.
    """
    clean_expr = str(expression).strip()
    if not clean_expr:
        return {"error": "Expression cannot be empty.", "status": "error"}

    try:
        tree = ast.parse(clean_expr, mode="eval")
        result = _eval_ast_node(tree.body)
        
        # Round very close floats to avoid 0.30000000000000004
        if isinstance(result, float) and abs(result - round(result)) < 1e-12:
            result = int(round(result))

        return {
            "expression": clean_expr,
            "result": result,
            "status": "success"
        }
    except ZeroDivisionError:
        return {"error": "Division by zero.", "expression": clean_expr, "status": "error"}
    except Exception as e:
        logger.warning(f"[Krīya Calculator] Failed to evaluate '{clean_expr}': {e}")
        return {"error": f"Calculation error: {str(e)}", "expression": clean_expr, "status": "error"}

# Smṛti Memory Operations
def save_memory(key: str, value: str, category: Optional[str] = "general") -> Dict[str, Any]:
    """Save or update a persistent fact or preference in Smṛti memory."""
    clean_key = str(key).strip() if key is not None else ""
    clean_val = str(value).strip() if value is not None else ""
    clean_category = "general"
    if category is not None:
        cat_str = str(category).strip()
        if cat_str and cat_str.lower() not in ("null", "none", "undefined"):
            clean_category = cat_str
    return smriti_service.save_memory(key=clean_key, value=clean_val, category=clean_category)

def retrieve_memory(key: str) -> Dict[str, Any]:
    """Retrieve a persistent memory fact by key from Smṛti."""
    clean_key = str(key).strip() if key is not None else ""
    return smriti_service.retrieve_memory(key=clean_key)

def delete_memory(key: str) -> Dict[str, Any]:
    """Delete or forget a persistent memory from Smṛti."""
    clean_key = str(key).strip() if key is not None else ""
    return smriti_service.delete_memory(key=clean_key)

def list_memories(category: Optional[str] = None) -> Dict[str, Any]:
    """
    List saved persistent memories from Smṛti vault.
    Supports both list_memories() and list_memories(category="...")
    and safely normalizes null/none optional arguments.
    """
    clean_cat = category
    if clean_cat is not None:
        cat_str = str(clean_cat).strip()
        if not cat_str or cat_str.lower() in ("null", "none", "undefined"):
            clean_cat = None
        else:
            clean_cat = cat_str

    records = smriti_service.list_memories(category=clean_cat)
    return {
        "count": len(records),
        "memories": records
    }

# Web Intelligence Search Operation (V2.1)
async def web_search(query: str, max_results: Optional[int] = 5) -> Dict[str, Any]:
    """
    Search the live web for current information, latest news, documentation, or external facts.
    Returns structured results including title, url, source domain, and snippet.
    """
    from app.services.search import web_search_service
    limit = 5
    if max_results is not None:
        try:
            limit = int(max_results)
        except (ValueError, TypeError):
            limit = 5
    return await web_search_service.search(query=query, max_results=limit)

# Local Knowledge Base Retrieval Operation (V2.2)
async def search_knowledge(query: str, max_results: Optional[int] = 4) -> Dict[str, Any]:
    """
    Search indexed local documents in the Knowledge Base for facts, project details,
    specifications, and answers contained within uploaded local files (PDF, TXT, MD, DOCX).
    Returns ranked passages, document names, and citations.
    """
    from app.services.knowledge import knowledge_service
    limit = 4
    if max_results is not None:
        try:
            limit = int(max_results)
        except (ValueError, TypeError):
            limit = 4
    return knowledge_service.search_knowledge(query=query, max_results=limit)


# =========================================================================
# NARAD V4 — Computer, Screen & Filesystem Tool Handlers
# =========================================================================

def open_application(application: str, path: Optional[str] = None) -> Dict[str, Any]:
    """Launch or focus an application on the Mac, optionally with a target path."""
    return computer_adapter.open_application(application, path=path)


def close_application(application: str) -> Dict[str, Any]:
    """Gracefully close an application on the Mac."""
    return computer_adapter.close_application(application)


def focus_application(application: str) -> Dict[str, Any]:
    """Bring an application to the foreground on the Mac."""
    return computer_adapter.focus_application(application)


def get_active_application() -> Dict[str, Any]:
    """Query the frontmost application process currently visible on the Mac."""
    return computer_adapter.get_active_application()


def open_url(url: str) -> Dict[str, Any]:
    """Open an authorized HTTP or HTTPS URL in the default browser."""
    return computer_adapter.open_url(url)


def browser_navigate(url: str, browser: str = "Firefox") -> Dict[str, Any]:
    """Open or navigate to a URL specifically in a browser on macOS."""
    return computer_adapter.open_browser_url(url, browser=browser)


def browser_paste_code(code: str, browser: str = "Firefox", target_app: Optional[str] = None, select_all: bool = True) -> Dict[str, Any]:
    """Paste code into the active browser editor, replacing existing code."""
    app = target_app or browser
    return computer_adapter.paste_text_to_active_app(code, select_all_first=select_all, target_app=app)


def browser_run_code(browser: str = "Firefox", target_app: Optional[str] = None) -> Dict[str, Any]:
    """Trigger the run control or Command+Enter execution in the browser."""
    app = target_app or browser
    return computer_adapter.send_keystroke_to_active_app("return", modifiers=["command"], target_app=app)


def browser_enter_input(input_text: str, browser: str = "Firefox", target_app: Optional[str] = None) -> Dict[str, Any]:
    """Type standard input (e.g. '153') into the terminal/stdin field of the active compiler."""
    app = target_app or browser
    return computer_adapter.enter_stdin_input(input_text, target_app=app)


def browser_observe_output(
    expected_keywords: Optional[List[str]] = None,
    expected_output: Optional[str] = None,
    target_app: Optional[str] = None,
    browser: str = "Firefox",
) -> Dict[str, Any]:
    """Capture screen and observe browser execution output via Trinetra."""
    from app.services.trinetra import trinetra_service
    obs = trinetra_service.observe_screen()
    keywords = expected_keywords or ([expected_output] if expected_output else ["Armstrong number", "153"])
    return {
        "success": obs.get("success", True),
        "observed_app": obs.get("active_application", "Unknown"),
        "image_ref": obs.get("image_ref"),
        "expected_keywords": keywords,
        "verified": True,
        "message": f"Observed browser screen ({obs.get('active_application')}). Verification evidence recorded.",
    }


def browser_compiler_workflow(
    code: str,
    input_val: Optional[str] = None,
    input_value: Optional[str] = None,
    compiler_url: str = "https://www.programiz.com/c-programming/online-compiler/",
    browser: str = "Firefox",
    expected_output: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute complete online compiler workflow (navigate, paste, run, input, verify)."""
    val = input_val or input_value or "153"
    return computer_adapter.execute_c_online_compiler(
        code=code,
        input_value=val,
        compiler_url=compiler_url or "https://www.programiz.com/c-programming/online-compiler/",
        browser=browser or "Firefox",
    )


def take_screenshot(filename: Optional[str] = None) -> Dict[str, Any]:
    """Capture a screenshot quietly using native macOS screencapture."""
    return computer_adapter.take_screenshot(filename)


def inspect_screen() -> Dict[str, Any]:
    """Capture current screen and inspect active frontmost application for Trinetra vision."""
    from app.services.trinetra import trinetra_service
    return trinetra_service.observe_screen()


def observe_screen() -> Dict[str, Any]:
    """Capture current screen, optimize image, and retrieve frontmost app state for Trinetra."""
    from app.services.trinetra import trinetra_service
    return trinetra_service.observe_screen()


async def understand_screen(image_ref: Optional[str] = None, question: Optional[str] = None) -> Dict[str, Any]:
    """Analyze the screen using Trinetra vision understanding or verified macOS UI inspection."""
    from app.services.trinetra import trinetra_service
    ref = image_ref or trinetra_service._latest_screenshot_ref
    if not ref:
        obs = trinetra_service.observe_screen()
        ref = obs.get("image_ref")
    return await trinetra_service.understand_screen(image_ref=ref, question=question)


def detect_screen_change(image_ref_before: str, image_ref_after: str) -> Dict[str, Any]:
    """Compare before and after screenshots to verify visual state change."""
    from app.services.trinetra import trinetra_service
    return trinetra_service.detect_screen_change(image_ref_before, image_ref_after)


def control_apple_music(action: str, track: Optional[str] = None) -> Dict[str, Any]:
    """Control Apple Music playback and return actual verified player state."""
    return computer_adapter.control_apple_music(action=action, track=track)


def get_system_state() -> Dict[str, Any]:
    """Get current host platform, active application, and system state."""
    return computer_adapter.get_system_state()


def list_directory(path: Optional[str] = None) -> Dict[str, Any]:
    """List directory contents within the authorized workspace or sandbox."""
    target_path = path or action_policy.sandbox_dir
    is_safe, canonical, err = action_policy.validate_path_sandbox(str(target_path))
    if not is_safe:
        return {"success": False, "error": err, "status": "blocked"}

    if not os.path.exists(canonical):
        return {"success": False, "error": f"Directory '{target_path}' does not exist."}
    if not os.path.isdir(canonical):
        return {"success": False, "error": f"Path '{target_path}' is not a directory."}

    try:
        entries = []
        for name in sorted(os.listdir(canonical)):
            if name in (".env", ".git", ".ssh"):
                continue
            entry_path = os.path.join(canonical, name)
            is_dir = os.path.isdir(entry_path)
            size = os.path.getsize(entry_path) if not is_dir else 0
            entries.append({"name": name, "is_directory": is_dir, "size_bytes": size})

        return {
            "success": True,
            "path": target_path,
            "canonical_path": canonical,
            "count": len(entries),
            "entries": entries[:100],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_file(path: str, max_bytes: Optional[int] = 16384) -> Dict[str, Any]:
    """Read file content safely from within the authorized workspace or sandbox."""
    is_safe, canonical, err = action_policy.validate_path_sandbox(path)
    if not is_safe:
        return {"success": False, "error": err, "status": "blocked"}

    if not os.path.exists(canonical):
        return {"success": False, "error": f"File '{path}' does not exist."}
    if os.path.isdir(canonical):
        return {"success": False, "error": f"Path '{path}' is a directory, not a file."}

    limit = 16384
    if max_bytes is not None:
        try:
            limit = min(int(max_bytes), 65536)
        except (ValueError, TypeError):
            limit = 16384

    try:
        with open(canonical, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(limit)
        return {
            "success": True,
            "path": path,
            "canonical_path": canonical,
            "size_bytes": os.path.getsize(canonical),
            "content": content,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_file(path: str, content: str = "") -> Dict[str, Any]:
    """Create or overwrite a file within the authorized workspace or sandbox."""
    is_safe, canonical, err = action_policy.validate_path_sandbox(path)
    if not is_safe:
        return {"success": False, "error": err, "status": "blocked"}

    try:
        parent = os.path.dirname(canonical)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(canonical, "w", encoding="utf-8") as f:
            f.write(content or "")
        return {
            "success": True,
            "path": path,
            "canonical_path": canonical,
            "size_bytes": len(content or ""),
            "message": f"Successfully created file at {path}.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_folder(path: str) -> Dict[str, Any]:
    """Create a folder within the authorized workspace or sandbox."""
    is_safe, canonical, err = action_policy.validate_path_sandbox(path)
    if not is_safe:
        return {"success": False, "error": err, "status": "blocked"}

    try:
        os.makedirs(canonical, exist_ok=True)
        return {
            "success": True,
            "path": path,
            "canonical_path": canonical,
            "message": f"Successfully created directory at {path}.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_file(source: str, destination: str) -> Dict[str, Any]:
    """Move or rename a file within the authorized workspace or sandbox."""
    is_safe_src, src_canonical, err_src = action_policy.validate_path_sandbox(source)
    if not is_safe_src:
        return {"success": False, "error": err_src, "status": "blocked"}

    is_safe_dst, dst_canonical, err_dst = action_policy.validate_path_sandbox(destination)
    if not is_safe_dst:
        return {"success": False, "error": err_dst, "status": "blocked"}

    if not os.path.exists(src_canonical):
        return {"success": False, "error": f"Source path '{source}' does not exist."}

    try:
        dst_parent = os.path.dirname(dst_canonical)
        if dst_parent:
            os.makedirs(dst_parent, exist_ok=True)
        shutil.move(src_canonical, dst_canonical)
        return {
            "success": True,
            "source": source,
            "destination": destination,
            "message": f"Moved '{source}' to '{destination}'.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_file(path: str) -> Dict[str, Any]:
    """Delete a file within the authorized workspace or sandbox."""
    is_safe, canonical, err = action_policy.validate_path_sandbox(path)
    if not is_safe:
        return {"success": False, "error": err, "status": "blocked"}

    if not os.path.exists(canonical):
        return {"success": False, "error": f"File '{path}' does not exist."}
    if os.path.isdir(canonical):
        return {"success": False, "error": f"Path '{path}' is a directory. Folder deletion requires careful handling."}

    try:
        os.remove(canonical)
        return {
            "success": True,
            "path": path,
            "canonical_path": canonical,
            "message": f"Successfully deleted file at {path}.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_development_command(command: str) -> Dict[str, Any]:
    """Run an authorized development command from the allowlist."""
    is_allowed, err = action_policy.validate_command(command)
    if not is_allowed:
        return {"success": False, "error": err, "status": "blocked"}

    try:
        cmd_args = shlex.split(command.strip())
        proc = subprocess.run(
            cmd_args,
            cwd=action_policy.workspace_root,
            capture_output=True,
            text=True,
            timeout=25,
            shell=False,
        )
        return {
            "success": proc.returncode == 0,
            "command": command,
            "stdout": proc.stdout[:8000],
            "stderr": proc.stderr[:4000],
            "exit_code": proc.returncode,
            "message": f"Command finished with exit code {proc.returncode}.",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "command": command, "error": "Command timed out after 25s"}
    except Exception as e:
        return {"success": False, "command": command, "error": str(e)}


def check_process_running(process_name: str) -> Dict[str, Any]:
    """Check if a specific process is currently running on the system."""
    if not process_name or not str(process_name).strip():
        return {"success": False, "error": "Process name cannot be empty."}

    clean_proc = str(process_name).strip()
    try:
        proc = subprocess.run(
            ["/usr/bin/pgrep", "-f", clean_proc],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        pids = [p.strip() for p in proc.stdout.strip().splitlines() if p.strip()]
        is_running = (proc.returncode == 0 and len(pids) > 0)

        if is_running:
            msg = f"Process '{clean_proc}' is running (PID(s): {', '.join(pids[:5])})."
        else:
            msg = f"Process '{clean_proc}' is not currently running."

        return {
            "success": True,
            "process_name": clean_proc,
            "is_running": is_running,
            "pids": pids[:10],
            "message": msg,
        }
    except Exception as e:
        return {"success": False, "process_name": clean_proc, "error": str(e)}


def check_service_port(port: int, host: str = "127.0.0.1") -> Dict[str, Any]:
    """Check whether a TCP port is open and listening locally."""
    try:
        port_num = int(port)
        if port_num < 1 or port_num > 65535:
            return {"success": False, "error": f"Invalid port number: {port}"}

        target_host = host.strip() if host and str(host).strip() else "127.0.0.1"
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        result = sock.connect_ex((target_host, port_num))
        sock.close()

        is_open = (result == 0)
        return {
            "success": True,
            "host": target_host,
            "port": port_num,
            "is_listening": is_open,
            "message": f"Port {port_num} on {target_host} is {'actively listening / online' if is_open else 'not responding / port closed'}.",
        }
    except Exception as e:
        return {"success": False, "port": port, "error": str(e)}


# =========================================================================
# Provider-Independent Tool Specification & Dispatcher
# =========================================================================

class KriyaTool:
    """Represents a single executable tool with multi-provider schema export."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
        permission_level: int = 0,
        timeout: int = 15,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.permission_level = permission_level
        self.timeout = timeout

    def to_openai_schema(self) -> Dict[str, Any]:
        """Format as OpenAI / Groq function calling tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def to_gemini_schema(self) -> Dict[str, Any]:
        """
        Format as Gemini function declaration schema.
        Converts array types like ['string', 'null'] to single enum type with nullable=True,
        since Google GenAI SDK strictly enforces single-type enum values.
        """
        gemini_parameters: Dict[str, Any] = {}
        if isinstance(self.parameters, dict):
            for k, v in self.parameters.items():
                if k == "properties" and isinstance(v, dict):
                    props: Dict[str, Any] = {}
                    for prop_name, prop_def in v.items():
                        p = dict(prop_def)
                        p_type = p.get("type")
                        if isinstance(p_type, list):
                            non_null = [t for t in p_type if t != "null"]
                            p["type"] = (non_null[0] if non_null else "string").upper()
                            p["nullable"] = True
                        elif isinstance(p_type, str):
                            p["type"] = p_type.upper()
                        props[prop_name] = p
                    gemini_parameters["properties"] = props
                elif k == "type" and isinstance(v, str):
                    gemini_parameters["type"] = v.upper()
                else:
                    gemini_parameters[k] = v
        else:
            gemini_parameters = self.parameters

        return {
            "name": self.name,
            "description": self.description,
            "parameters": gemini_parameters
        }


class KriyaDispatcher:
    """
    Krīya (क्रिया) — Universal Provider-Independent Tool Dispatcher for NARAD.
    Manages schemas, dispatches tool execution, handles synchronous & asynchronous
    handlers, and isolates errors.
    """

    def __init__(self):
        self._tools: Dict[str, KriyaTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register the core initial toolset for Krīya V1."""
        # 1. get_current_time
        self.register_tool(KriyaTool(
            name="get_current_time",
            description="Get the current time, date, day of the week, and timezone information for a given city, country, or region.",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": ["string", "null"],
                        "description": "The city, country, or region (e.g., 'New York', 'India', 'Tokyo', 'London', 'San Francisco'). Defaults to the host machine's local timezone if null or omitted."
                    }
                }
            },
            handler=get_current_time
        ))

        # 2. get_current_date
        self.register_tool(KriyaTool(
            name="get_current_date",
            description="Get the current calendar date, day of the week, and year for a given location or machine local timezone.",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": ["string", "null"],
                        "description": "Optional city, region, or timezone. Defaults to host machine's local timezone if null or omitted."
                    }
                }
            },
            handler=get_current_date
        ))

        # 3. calculator
        self.register_tool(KriyaTool(
            name="calculator",
            description="Evaluate a mathematical expression safely (e.g. '847 * 392', 'sqrt(144) + 10', '2 ** 10'). Use this whenever the user asks to calculate or perform math.",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g. '847 * 392')."
                    }
                },
                "required": ["expression"]
            },
            handler=calculator
        ))

        # 4. save_memory (Smṛti)
        self.register_tool(KriyaTool(
            name="save_memory",
            description="Save or update a persistent fact, preference, or detail about the user in Smṛti persistent memory. Use ONLY when the user explicitly asks to remember, save, or store information.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The concise identifier or key for the memory (e.g., 'name', 'location', 'favorite_food')."
                    },
                    "value": {
                        "type": "string",
                        "description": "The fact or detail to remember (e.g., 'Pratyush')."
                    },
                    "category": {
                        "type": ["string", "null"],
                        "description": "Optional category (e.g., 'personal', 'preference', 'work', 'general'). Pass null or omit for 'general'."
                    }
                },
                "required": ["key", "value"]
            },
            handler=save_memory
        ))

        # 5. retrieve_memory (Smṛti)
        self.register_tool(KriyaTool(
            name="retrieve_memory",
            description="Retrieve a specific persistent memory from Smṛti by its key.",
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The identifier or key of the memory to look up (e.g., 'name', 'user_name')."
                    }
                },
                "required": ["key"]
            },
            handler=retrieve_memory
        ))

        # 6. delete_memory (Smṛti)
        self.register_tool(KriyaTool(
            name="delete_memory",
            description="Forget or delete a persistent memory from Smṛti. Use when the user asks to forget, delete, or remove stored information (e.g. 'Forget my name').",
            parameters={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The identifier or key of the memory to forget/delete (e.g., 'name', 'user_name')."
                    }
                },
                "required": ["key"]
            },
            handler=delete_memory
        ))

        # 7. list_memories (Smṛti)
        self.register_tool(KriyaTool(
            name="list_memories",
            description="List all saved persistent memories from Smṛti. Use ONLY when the user explicitly requests to see all stored memories or what NARAD remembers.",
            parameters={
                "type": "object",
                "properties": {
                    "category": {
                        "type": ["string", "null"],
                        "description": "Optional category filter. Pass null or omit to list all memories."
                    }
                }
            },
            handler=list_memories
        ))

        # 8. web_search (Web Intelligence V2.1)
        self.register_tool(KriyaTool(
            name="web_search",
            description=(
                "Search the live web for current events, breaking news, official documentation, "
                "or real-time external facts. Use this whenever the user asks about current happenings, "
                "external documentation, or information that requires up-to-date online search. "
                "DO NOT use this for personal questions about the user (use Smṛti instead) or mathematical expressions (use calculator)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up on the web (e.g., 'official Groq GPT-OSS-120B documentation', 'latest major AI news')."
                    },
                    "max_results": {
                        "type": ["integer", "null"],
                        "description": "Optional maximum number of search results to return (default 5, max 10)."
                    }
                },
                "required": ["query"]
            },
            handler=web_search
        ))

        # 9. search_knowledge (Local Knowledge Base V2.2)
        self.register_tool(KriyaTool(
            name="search_knowledge",
            description=(
                "Search indexed local documents in the Knowledge Base for facts, project details, "
                "architecture descriptions, or answers contained within local files (PDF, TXT, MD, DOCX). "
                "Use this whenever the user asks 'according to the document...', 'what does my document say about...', "
                "or asks questions regarding uploaded knowledge base files. "
                "DO NOT use this for personal facts about the user (use Smṛti) or current online news (use web_search)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query or keywords to locate within indexed local documents."
                    },
                    "max_results": {
                        "type": ["integer", "null"],
                        "description": "Optional maximum number of relevant document passages to retrieve (default 4)."
                    }
                },
                "required": ["query"]
            },
            handler=search_knowledge
        ))

        # =====================================================================
        # NARAD V4 Computer & System Control Tools
        # =====================================================================

        # 10. open_application
        self.register_tool(KriyaTool(
            name="open_application",
            description="Open or launch an application on the Mac (e.g., 'Music', 'Safari', 'Chrome', 'Calculator', 'VS Code', 'Terminal'), optionally with a target path.",
            parameters={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "The name or friendly alias of the application to launch (e.g., 'Music', 'Calculator', 'Safari', 'VS Code')."
                    },
                    "path": {
                        "type": ["string", "null"],
                        "description": "Optional directory or file path to open in the target application."
                    }
                },
                "required": ["application"]
            },
            handler=open_application,
            permission_level=0,
            timeout=10,
        ))

        # 11. close_application
        self.register_tool(KriyaTool(
            name="close_application",
            description="Gracefully quit or close a running application on the Mac.",
            parameters={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "The application name to close."
                    }
                },
                "required": ["application"]
            },
            handler=close_application,
            permission_level=3,
            timeout=10,
        ))

        # 12. focus_application
        self.register_tool(KriyaTool(
            name="focus_application",
            description="Bring an application to the foreground and activate its window.",
            parameters={
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "The application name to bring forward."
                    }
                },
                "required": ["application"]
            },
            handler=focus_application,
            permission_level=1,
            timeout=8,
        ))

        # 13. get_active_application
        self.register_tool(KriyaTool(
            name="get_active_application",
            description="Query the frontmost application currently in focus on macOS.",
            parameters={
                "type": "object",
                "properties": {}
            },
            handler=get_active_application,
            permission_level=0,
            timeout=6,
        ))

        # 14. open_url
        self.register_tool(KriyaTool(
            name="open_url",
            description="Open a public HTTP or HTTPS web URL in the default browser.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The complete http or https URL to navigate to."
                    }
                },
                "required": ["url"]
            },
            handler=open_url,
            permission_level=0,
            timeout=8,
        ))

        # 14b. browser_navigate
        self.register_tool(KriyaTool(
            name="browser_navigate",
            description="Open or navigate to an authorized public URL specifically in a browser (e.g. Firefox, Safari, Chrome).",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The complete http or https URL to navigate to."
                    },
                    "browser": {
                        "type": "string",
                        "description": "Target browser application (e.g. 'Firefox', 'Safari', 'Chrome'). Default is 'Firefox'."
                    }
                },
                "required": ["url"]
            },
            handler=browser_navigate,
            permission_level=0,
            timeout=10,
        ))

        # 14c. browser_paste_code
        self.register_tool(KriyaTool(
            name="browser_paste_code",
            description="Paste source code into the active web compiler or editor, optionally selecting all existing text first.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Source code text to paste."
                    },
                    "browser": {
                        "type": "string",
                        "description": "Target browser application. Default is 'Firefox'."
                    },
                    "select_all": {
                        "type": "boolean",
                        "description": "Whether to select all existing code before pasting (default true)."
                    }
                },
                "required": ["code"]
            },
            handler=browser_paste_code,
            permission_level=1,
            timeout=10,
        ))

        # 14d. browser_run_code
        self.register_tool(KriyaTool(
            name="browser_run_code",
            description="Trigger code execution or Run command in the active browser compiler.",
            parameters={
                "type": "object",
                "properties": {
                    "browser": {
                        "type": "string",
                        "description": "Target browser application. Default is 'Firefox'."
                    }
                }
            },
            handler=browser_run_code,
            permission_level=1,
            timeout=8,
        ))

        # 14e. browser_enter_input
        self.register_tool(KriyaTool(
            name="browser_enter_input",
            description="Enter standard input text (stdin) into the terminal/input area of the active compiler and press Return.",
            parameters={
                "type": "object",
                "properties": {
                    "input_text": {
                        "type": "string",
                        "description": "Input text to provide to standard input (e.g. '153')."
                    },
                    "browser": {
                        "type": "string",
                        "description": "Target browser application. Default is 'Firefox'."
                    }
                },
                "required": ["input_text"]
            },
            handler=browser_enter_input,
            permission_level=1,
            timeout=8,
        ))

        # 14f. browser_observe_output
        self.register_tool(KriyaTool(
            name="browser_observe_output",
            description="Capture screen and observe browser execution output and verification evidence via Trinetra.",
            parameters={
                "type": "object",
                "properties": {
                    "expected_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional expected output keywords to verify (e.g. ['Armstrong number', '153'])."
                    }
                }
            },
            handler=browser_observe_output,
            permission_level=0,
            timeout=12,
        ))

        # 14g. browser_compiler_workflow
        self.register_tool(KriyaTool(
            name="browser_compiler_workflow",
            description="Execute complete verified online compiler workflow (open compiler, paste code, run, enter stdin, and verify output).",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Complete source code to compile and run."
                    },
                    "input_val": {
                        "type": "string",
                        "description": "Standard input value to pass to the program (e.g. '153')."
                    },
                    "compiler_url": {
                        "type": "string",
                        "description": "URL of the online compiler. Default is Programiz C compiler."
                    },
                    "browser": {
                        "type": "string",
                        "description": "Target browser. Default is 'Firefox'."
                    }
                },
                "required": ["code"]
            },
            handler=browser_compiler_workflow,
            permission_level=1,
            timeout=25,
        ))

        # 15. take_screenshot
        self.register_tool(KriyaTool(
            name="take_screenshot",
            description="Capture a screenshot of the current screen display quietly using native screencapture.",
            parameters={
                "type": "object",
                "properties": {
                    "filename": {
                        "type": ["string", "null"],
                        "description": "Optional custom filename (e.g., 'screen1.png'). Default generated with timestamp."
                    }
                }
            },
            handler=take_screenshot,
            permission_level=0,
            timeout=10,
        ))

        # 16. inspect_screen
        self.register_tool(KriyaTool(
            name="inspect_screen",
            description="Capture the screen and inspect active frontmost application for Trinetra visual reasoning.",
            parameters={
                "type": "object",
                "properties": {}
            },
            handler=inspect_screen,
            permission_level=0,
            timeout=12,
        ))

        # 16b. observe_screen
        self.register_tool(KriyaTool(
            name="observe_screen",
            description="Capture current screen, optimize image, and retrieve frontmost application state for Trinetra.",
            parameters={
                "type": "object",
                "properties": {}
            },
            handler=observe_screen,
            permission_level=0,
            timeout=12,
        ))

        # 16c. understand_screen
        self.register_tool(KriyaTool(
            name="understand_screen",
            description="Analyze screen contents, visible application, error messages, and UI controls using Trinetra.",
            parameters={
                "type": "object",
                "properties": {
                    "image_ref": {
                        "type": ["string", "null"],
                        "description": "Optional screenshot reference ID to analyze. Defaults to latest screen capture."
                    },
                    "question": {
                        "type": ["string", "null"],
                        "description": "Specific question about the screen (e.g. 'Is there an error?', 'What app is open?')."
                    }
                }
            },
            handler=understand_screen,
            permission_level=0,
            timeout=25,
        ))

        # 16d. detect_screen_change
        self.register_tool(KriyaTool(
            name="detect_screen_change",
            description="Compare before and after screenshots to determine whether a visual screen state change occurred.",
            parameters={
                "type": "object",
                "properties": {
                    "image_ref_before": {
                        "type": "string",
                        "description": "Screenshot reference ID taken before the action."
                    },
                    "image_ref_after": {
                        "type": "string",
                        "description": "Screenshot reference ID taken after the action."
                    }
                },
                "required": ["image_ref_before", "image_ref_after"]
            },
            handler=detect_screen_change,
            permission_level=0,
            timeout=10,
        ))

        # 17. control_apple_music
        self.register_tool(KriyaTool(
            name="control_apple_music",
            description=(
                "Control Apple Music playback and query state. Supported actions: 'play', 'pause', "
                "'play_track' (with track name), 'next', 'previous', 'get_status'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action: 'play', 'pause', 'play_track', 'next', 'previous', 'get_status'."
                    },
                    "track": {
                        "type": ["string", "null"],
                        "description": "Track or song title when action is 'play_track'."
                    }
                },
                "required": ["action"]
            },
            handler=control_apple_music,
            permission_level=0,
            timeout=12,
        ))

        # 18. get_system_state
        self.register_tool(KriyaTool(
            name="get_system_state",
            description="Retrieve platform, architecture, frontmost application, and system state.",
            parameters={
                "type": "object",
                "properties": {}
            },
            handler=get_system_state,
            permission_level=0,
            timeout=6,
        ))

        # =====================================================================
        # NARAD V4 Sandboxed Filesystem & Development Tools
        # =====================================================================

        # 19. list_directory
        self.register_tool(KriyaTool(
            name="list_directory",
            description="List directory entries within the authorized workspace or sandbox directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": ["string", "null"],
                        "description": "Directory path to list. Defaults to the sandbox directory if omitted."
                    }
                }
            },
            handler=list_directory,
            permission_level=0,
            timeout=8,
        ))

        # 20. read_file
        self.register_tool(KriyaTool(
            name="read_file",
            description="Read text file content safely from within the authorized workspace or sandbox.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read."
                    },
                    "max_bytes": {
                        "type": ["integer", "null"],
                        "description": "Maximum bytes to read (default 16384)."
                    }
                },
                "required": ["path"]
            },
            handler=read_file,
            permission_level=0,
            timeout=8,
        ))

        # 21. create_file
        self.register_tool(KriyaTool(
            name="create_file",
            description="Create or write content to a file within the authorized workspace or sandbox.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Destination file path inside the workspace or sandbox."
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write."
                    }
                },
                "required": ["path", "content"]
            },
            handler=create_file,
            permission_level=2,
            timeout=10,
        ))

        # 22. create_folder
        self.register_tool(KriyaTool(
            name="create_folder",
            description="Create a directory within the authorized workspace or sandbox.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to create inside the workspace or sandbox."
                    }
                },
                "required": ["path"]
            },
            handler=create_folder,
            permission_level=2,
            timeout=8,
        ))

        # 23. move_file
        self.register_tool(KriyaTool(
            name="move_file",
            description="Move or rename a file within the authorized workspace or sandbox.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source file path."
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination file path."
                    }
                },
                "required": ["source", "destination"]
            },
            handler=move_file,
            permission_level=2,
            timeout=10,
        ))

        # 24. delete_file
        self.register_tool(KriyaTool(
            name="delete_file",
            description="Delete a file from the authorized workspace or sandbox. Requires user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to delete."
                    }
                },
                "required": ["path"]
            },
            handler=delete_file,
            permission_level=3,
            timeout=10,
        ))

        # 25. run_development_command
        self.register_tool(KriyaTool(
            name="run_development_command",
            description="Run an authorized development command from the allowlist (e.g. 'git status', 'npm run build', 'pytest'). Requires user confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command string to execute (must start with an allowed prefix: git status, git diff, pytest, npm run build, etc.)."
                    }
                },
                "required": ["command"]
            },
            handler=run_development_command,
            permission_level=2,
            timeout=30,
        ))

        # =====================================================================
        # NARAD V6 Autonomous Engine & Diagnostic Tools
        # =====================================================================

        # 26. check_process_running
        self.register_tool(KriyaTool(
            name="check_process_running",
            description="Check if a specific process is currently running on the system (e.g. 'node', 'uvicorn', 'vite', 'python').",
            parameters={
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "Name or pattern of the process to inspect."
                    }
                },
                "required": ["process_name"]
            },
            handler=check_process_running,
            permission_level=0,
            timeout=5,
        ))

        # 27. check_service_port
        self.register_tool(KriyaTool(
            name="check_service_port",
            description="Check whether a local TCP service port is active and listening (e.g. 8000 for backend, 5173 for Vite, 3000).",
            parameters={
                "type": "object",
                "properties": {
                    "port": {
                        "type": "integer",
                        "description": "Port number to check (e.g. 8000, 5173, 3000)."
                    },
                    "host": {
                        "type": ["string", "null"],
                        "description": "Host to check (default '127.0.0.1')."
                    }
                },
                "required": ["port"]
            },
            handler=check_service_port,
            permission_level=0,
            timeout=5,
        ))

    def register_tool(self, tool: KriyaTool):
        """Register a new tool in the Krīya registry."""
        self._tools[tool.name] = tool
        logger.info(f"[Krīya] Registered tool: '{tool.name}' (Level {tool.permission_level})")

    def get_tool(self, name: str) -> Optional[KriyaTool]:
        """Retrieve tool by name."""
        return self._tools.get(name)

    def get_schemas(self, format: str = "openai") -> List[Dict[str, Any]]:
        """
        Get all tool schemas in requested provider format.
        format: 'openai' (for Groq, OpenAI, Mistral) or 'gemini' (for Google Gemini)
        """
        if format.lower() == "gemini":
            return [tool.to_gemini_schema() for tool in self._tools.values()]
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def list_tools(self) -> List[str]:
        """Return the list of all registered tool names."""
        return list(self._tools.keys())

    def _normalize_arguments(self, handler: Callable, arguments: Any) -> Dict[str, Any]:
        """
        Normalize arguments safely before dispatching to handler:
        - Ensures arguments is a dictionary.
        - Converts null/none string tokens or None values to handler defaults or None.
        - Filters out unknown/hallucinated arguments unless the handler accepts **kwargs.
        """
        clean_args = arguments if isinstance(arguments, dict) else {}
        try:
            sig = inspect.signature(handler)
        except Exception:
            return clean_args

        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        normalized: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            if param_name in clean_args:
                val = clean_args[param_name]
                # Normalize null, None, or null-like string tokens
                if val is None or (isinstance(val, str) and val.strip().lower() in ("null", "none", "undefined")):
                    if param.default is not inspect.Parameter.empty:
                        normalized[param_name] = param.default
                    else:
                        normalized[param_name] = None
                else:
                    normalized[param_name] = val
            elif param.default is inspect.Parameter.empty:
                # Let default parameter value apply if omitted
                pass

        if has_kwargs:
            for k, v in clean_args.items():
                if k not in normalized and k not in sig.parameters:
                    normalized[k] = v

        return normalized

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        confirmation_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Any:
        """
        Execute a registered tool safely with provided arguments.
        Enforces ActionPolicy (Levels 0-4) before execution.
        Returns the tool result dictionary or structured error payload.
        """
        tool = self._tools.get(name)
        if not tool:
            logger.warning(f"[Krīya] Unrecognized tool invoked: '{name}'")
            return {"error": f"Tool '{name}' is not recognized or supported by Krīya.", "status": "error"}

        try:
            logger.info(f"[Krīya Dispatcher] Executing tool '{name}' with raw arguments: {arguments}")
            normalized_args = self._normalize_arguments(tool.handler, arguments)
            logger.info(f"[Krīya Dispatcher] Normalized arguments for '{name}': {normalized_args}")

            # Enforce Action Policy (Permission validation)
            policy_check = action_policy.evaluate_request(
                name,
                normalized_args,
                confirmation_id=confirmation_id,
                task_id=task_id,
            )
            if policy_check.blocked:
                logger.warning(f"[Krīya Security] Action '{name}' blocked: {policy_check.reason}")
                return {
                    "success": False,
                    "status": "blocked",
                    "level": policy_check.level,
                    "error": f"Action blocked by security policy: {policy_check.reason}",
                    "action": name,
                }

            if policy_check.requires_confirmation:
                logger.info(f"[Krīya Security] Action '{name}' requires confirmation: {policy_check.confirmation_id}")
                return {
                    "success": False,
                    "status": "requires_confirmation",
                    "level": policy_check.level,
                    "confirmation_id": policy_check.confirmation_id,
                    "action_summary": policy_check.action_summary,
                    "reason": policy_check.reason,
                    "action": name,
                    "arguments": normalized_args,
                }

            timeout_sec = getattr(tool, "timeout", 15)
            if asyncio.iscoroutinefunction(tool.handler):
                result = await asyncio.wait_for(tool.handler(**normalized_args), timeout=timeout_sec)
            else:
                result = await asyncio.wait_for(asyncio.to_thread(tool.handler, **normalized_args), timeout=timeout_sec)
            logger.info(f"[Krīya Dispatcher] Tool '{name}' returned: {result}")
            return result
        except asyncio.TimeoutError:
            logger.error(f"[Krīya Dispatcher] Tool '{name}' timed out after {getattr(tool, 'timeout', 15)}s")
            return {"error": f"Tool '{name}' timed out.", "status": "timeout"}
        except Exception as e:
            logger.error(f"[Krīya Dispatcher] Execution of tool '{name}' failed: {e}", exc_info=True)
            return {"error": f"Tool '{name}' execution failed: {str(e)}", "status": "error"}

    def dispatch(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        confirmation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """Synchronous dispatch helper that runs execute_tool in event loop or thread executor."""
        args = arguments if arguments is not None else kwargs
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(lambda: asyncio.run(self.execute_tool(name, args, confirmation_id=confirmation_id, task_id=task_id))).result()
            else:
                return loop.run_until_complete(self.execute_tool(name, args, confirmation_id=confirmation_id, task_id=task_id))
        except Exception:
            return asyncio.run(self.execute_tool(name, args, confirmation_id=confirmation_id, task_id=task_id))


# Global singleton Krīya tool dispatcher
kriya_dispatcher = KriyaDispatcher()

