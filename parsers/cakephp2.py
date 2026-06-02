"""
parsers/cakephp2.py
Parses CakePHP 2 plain-text error logs.

Sample CakePHP 2 log line:
2024-01-15 10:23:45 Error: Fatal error: Call to undefined method Model::findById()
in /var/www/app/Model/Order.php on line 77
Stack trace:
#0 /var/www/app/Controller/OrdersController.php(120): Order->findById()
"""

import re
from parsers.laravel import ParsedError, StackFrame


_HEADER_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>Error|Warning|Notice|Fatal error):\s+"
    r"(?P<msg>.+)"
)

_PRIMARY_FILE_RE = re.compile(
    r"in (?P<file>/[^\s]+) on line (?P<line>\d+)"
)

_FRAME_RE = re.compile(
    r"#\d+\s+(?P<file>[^\(]+)\((?P<line>\d+)\):\s+(?P<func>.+)"
)


def parse(log_block: str, domain: str | None = None) -> ParsedError | None:
    """Parse a CakePHP 2 multi-line log block."""
    header = _HEADER_RE.search(log_block)
    if not header:
        return None

    timestamp = header.group("ts")
    level = header.group("level").upper()
    raw_msg = header.group("msg").strip()

    # Normalise level
    if "fatal" in level.lower():
        level = "CRITICAL"
    elif level == "ERROR":
        level = "ERROR"

    # Error type heuristic
    error_type = "PHPError"
    type_match = re.match(r"(Fatal error|Parse error|TypeError|ValueError):\s*(.*)", raw_msg, re.I)
    if type_match:
        error_type = type_match.group(1)
        raw_msg = type_match.group(2).strip()

    # Primary file + line
    frames: list[StackFrame] = []
    primary = _PRIMARY_FILE_RE.search(log_block)
    if primary:
        frames.append(StackFrame(
            file=primary.group("file"),
            line=int(primary.group("line")),
            function="__primary__"
        ))

    # Stack frames
    for m in _FRAME_RE.finditer(log_block):
        frames.append(StackFrame(
            file=m.group("file").strip(),
            line=int(m.group("line")),
            function=m.group("func").strip()
        ))

    return ParsedError(
        framework="cakephp2",
        timestamp=timestamp,
        level=level,
        error_type=error_type,
        error_message=raw_msg,
        stack_frames=frames,
        domain=domain,
        raw=log_block
    )