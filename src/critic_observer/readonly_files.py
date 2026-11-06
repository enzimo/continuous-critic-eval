"""Read-only file tools over MCP stdio for critics that cannot use a shell sandbox.

Codex's read-only sandbox needs Linux namespaces, which some containers forbid. Trial
critics then run with the shell disabled and use these tools instead, giving them the
same access as Claude's Read, Grep and Glob: read files under one root, nothing else.
"""

import re
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

MAX_LIST = 2000
MAX_READ_LINES = 2000
MAX_MATCHES = 500


def resolve(root, relative):
    """Resolve a path inside root, refusing escapes and symbolic links."""
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"{relative} is outside the review folder")
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{relative} goes through a symbolic link")
    return path


def build(root):
    root = Path(root).resolve(strict=True)
    server = FastMCP("review-files")

    def files(pattern):
        for path in sorted(root.glob(pattern)):
            if path.is_file() and not path.is_symlink() and ".git" not in path.parts:
                yield path

    @server.tool()
    def list_files(pattern: str = "**/*") -> str:
        """List files matching a glob pattern, relative to the review folder."""
        names = [str(p.relative_to(root)) for p in files(pattern)]
        more = f"\n... {len(names) - MAX_LIST} more" if len(names) > MAX_LIST else ""
        return "\n".join(names[:MAX_LIST]) + more

    @server.tool()
    def read_file(path: str, offset: int = 1, limit: int = 400) -> str:
        """Read numbered lines of a file. offset is the first line (1-based)."""
        lines = resolve(root, path).read_text(errors="replace").splitlines()
        start, count = max(offset, 1), min(max(limit, 1), MAX_READ_LINES)
        chunk = lines[start - 1 : start - 1 + count]
        body = "\n".join(f"{n}: {line}" for n, line in enumerate(chunk, start))
        return body + (f"\n... {len(lines)} lines total" if start - 1 + count < len(lines) else "")

    @server.tool()
    def grep(pattern: str, glob: str = "**/*", ignore_case: bool = False) -> str:
        """Search files for a regular expression; returns path:line: text."""
        regex = re.compile(pattern, re.I if ignore_case else 0)
        matches = []
        for path in files(glob):
            try:
                text = path.read_text(errors="strict")
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{path.relative_to(root)}:{n}: {line[:300]}")
                    if len(matches) >= MAX_MATCHES:
                        return "\n".join(matches) + "\n... more matches omitted"
        return "\n".join(matches) or "No matches"

    return server


if __name__ == "__main__":
    build(sys.argv[1]).run("stdio")
