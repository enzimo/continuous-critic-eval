"""Run Claude Code isolated from this machine's setup.

Critic trials use explicit CLI options to isolate settings, skills, slash commands
and automatic memory. This keeps hooks from a reviewed repository from executing
through inherited client settings.
The repository's CLAUDE.md still loads: it is part of the code under review, as AGENTS.md
is for Codex.
"""

CLAUDE_ISOLATION_ARGS = ("--setting-sources", "", "--disable-slash-commands")
CLAUDE_ISOLATION_ENV = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
