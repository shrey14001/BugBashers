"""
parsers/laravel.py
Parses Laravel JSON log lines and plain-text stack traces.

Sample Laravel log line:
[2024-01-15 10:23:45] production.ERROR: Call to a member function id() on null
{"exception":"[object] (Error(code: 0): Call to a member function id() on null
at /var/www/app/Http/Controllers/PaymentController.php:42)
[stacktrace]
#0 /var/www/app/Services/PaymentService.php(88): ...
"}
"""

import re
import json
from dataclasses import dataclass, field


@dataclass
class StackFrame:
    file: str
    line: int
    function: str


@dataclass
class ParsedError:
    framework: str
    timestamp: str
    level: str
    error_type: str
    error_message: str
    stack_frames: list[StackFrame]
    domain: str | None = None
    url: str | None = None
    raw: str = ""

    # Paths that belong to the framework / shared libs — never the root cause
    _SKIP_PREFIXES = (
        "/usr/share/",
        "/vendor/",
    )
    _SKIP_FRAGMENTS = ("/vendor/", "framework/src/", "Cake/")

    def top_frame(self) -> StackFrame | None:
        """First non-vendor, non-framework frame (basic heuristic)."""
        for frame in self.stack_frames:
            if "/vendor/" not in frame.file and "framework" not in frame.file:
                return frame
        return self.stack_frames[0] if self.stack_frames else None

    def best_frame(self) -> StackFrame | None:
        """
        Strongest heuristic for finding the actual application frame:
        - Skips framework/shared-lib prefixes (Cake core, Laravel framework,
          shared /usr/share/… paths)
        - Prefers frames whose path contains /sites/ or a known app pattern
        - Falls back to top_frame() if nothing matches
        """
        def _is_app(frame: StackFrame) -> bool:
            f = frame.file
            if any(f.startswith(p) for p in self._SKIP_PREFIXES):
                return False
            if any(seg in f for seg in self._SKIP_FRAGMENTS):
                return False
            return True

        for frame in self.stack_frames:
            if _is_app(frame):
                return frame
        return self.top_frame()

    def embedding_text(self) -> str:
        """Text used for ChromaDB embedding & similarity search."""
        top = self.top_frame()
        frame_str = f"{top.file}:{top.line}" if top else ""
        return f"{self.error_type}: {self.error_message}\n{frame_str}"


# ── Regexes ───────────────────────────────────────────────────────────────────

_HEADER_RE = re.compile(
    r"\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+"
    r"\w+\.(?P<level>ERROR|CRITICAL|WARNING|INFO):\s+"
    r"(?P<msg>.+?)(?=\s*\{|$)",
    re.DOTALL
)

_FRAME_RE = re.compile(
    r"#\d+\s+(?P<file>[^\(]+)\((?P<line>\d+)\):\s+(?P<func>.+)"
)

_EXCEPTION_FILE_RE = re.compile(
    r"at (?P<file>/[^\:]+):(?P<line>\d+)\)"
)


def parse(log_line: str, domain: str | None = None) -> ParsedError | None:
    """
    Parse a Laravel log line.
    Handles two formats:
      1. Standard:  [2024-01-15 10:23:45] production.ERROR: Message {...}
      2. Bizom:     Message {"userId":123,"exception":"..."}  (no timestamp header)
    """
    timestamp = "N/A"
    level     = "ERROR"
    raw_msg   = ""

    # Try standard Laravel header first
    header = _HEADER_RE.search(log_line)
    if header:
        timestamp = header.group("ts")
        level     = header.group("level")
        raw_msg   = header.group("msg").strip()
    else:
        # Bizom-style: "Message text {"userId":...}"
        # Must contain a stacktrace to be considered a Laravel error log
        if "[stacktrace]" not in log_line and "#0 " not in log_line:
            return None
        msg_match = re.match(r'^(.+?)\s*\{', log_line)
        if not msg_match:
            return None
        raw_msg = msg_match.group(1).strip()

    # Extract exception text from JSON blob if present
    exception_text = raw_msg
    json_match = re.search(r'"exception"\s*:\s*"(.*?)"(?:\s*[,}])', log_line, re.DOTALL)
    if json_match:
        exception_text = json_match.group(1).replace("\\n", "\n")

    # Determine error type
    error_type    = "Error"
    error_message = raw_msg
    type_match = re.match(r"([A-Za-z\\]+Exception|[A-Za-z\\]+Error)[:\s]+(.*)", raw_msg)
    if type_match:
        error_type    = type_match.group(1).split("\\")[-1]
        error_message = type_match.group(2).strip()

    # Parse stack frames
    frames: list[StackFrame] = []

    # Primary error location from "at /path/file.php:line)"
    exc_file = _EXCEPTION_FILE_RE.search(exception_text)
    if exc_file:
        frames.append(StackFrame(
            file=exc_file.group("file"),
            line=int(exc_file.group("line")),
            function="__throw__"
        ))

    # Numbered stack frames: #0 /path/file.php(line): func()
    for m in _FRAME_RE.finditer(log_line):
        frames.append(StackFrame(
            file=m.group("file").strip(),
            line=int(m.group("line")),
            function=m.group("func").strip()
        ))

    if not frames:
        return None

    return ParsedError(
        framework="laravel",
        timestamp=timestamp,
        level=level,
        error_type=error_type,
        error_message=error_message,
        stack_frames=frames,
        domain=domain,
        raw=log_line
    )