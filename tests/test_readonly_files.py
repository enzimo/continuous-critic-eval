"""Codex critics without a shell sandbox get read-only file tools and an isolated home."""

import asyncio
import json

import pytest

from critic_observer import trials
from critic_observer.readonly_files import build, resolve


def call(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    content = result[0] if isinstance(result, tuple) else result
    return "\n".join(block.text for block in content)


def test_file_tools_read_inside_the_folder_only(tmp_path):
    root = tmp_path / "case"
    (root / "src").mkdir(parents=True)
    (root / "src/app.py").write_text("first\nsecret = 1\nthird\n")
    (tmp_path / "outside.txt").write_text("outside")
    (root / "link.txt").symlink_to(tmp_path / "outside.txt")
    server = build(root)

    assert call(server, "read_file", {"path": "src/app.py", "offset": 2, "limit": 1}).startswith(
        "2: secret = 1"
    )
    assert call(server, "list_files", {}) == "src/app.py"
    assert call(server, "grep", {"pattern": "secret"}) == "src/app.py:2: secret = 1"
    for path in ("../outside.txt", "link.txt"):
        with pytest.raises(ValueError):
            resolve(root.resolve(), path)
    with pytest.raises(Exception, match="outside the review folder"):
        call(server, "read_file", {"path": "../outside.txt"})


@pytest.mark.parametrize("file_tools", [False, True])
def test_codex_command_uses_file_tools_and_isolated_home_only_when_asked(
    tmp_path, monkeypatch, file_tools
):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(command=command, env=kwargs.get("env"))
        final = command[command.index("--output-last-message") + 1]
        result = {
            "status": "completed",
            "inspected_paths": ["a.py"],
            "limitations": [],
            "findings": [],
        }
        with open(final, "w") as file:
            json.dump(result, file)
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr(trials.subprocess, "run", fake_run)
    critic = {"prompt": "Review", "provider": "codex", "model": None, "settings": {}}
    trials.execute_critic(
        "codex", critic, tmp_path, "Goal", tmp_path, 60, file_tools, tmp_path / "home"
    )
    command = " ".join(captured["command"])
    assert ("features.shell_tool=false" in command) is file_tools
    assert ("critic_observer.readonly_files" in command) is file_tools
    assert 'web_search="disabled"' in command
    assert captured["env"]["CODEX_HOME"] == str(tmp_path / "home")
