"""Run frozen experiment cases using locally installed agent CLIs, never on the server."""

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from .claude_isolation import CLAUDE_ISOLATION_ARGS, CLAUDE_ISOLATION_ENV
from .client import batch_body
from .limits import LIMIT_REACHED, claude_error, codex_errors, is_account_limit
from .models import (
    MAX_BATCH_BYTES,
    MAX_BATCH_EVENTS,
    Batch,
    Category,
    Confidence,
    Event,
    Model,
    Severity,
    Usage,
    now,
)

log = logging.getLogger(__name__)
IGNORED = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".local"}


def target_files(directory):
    root = Path(directory).resolve(strict=True)
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Frozen case contains a symlink: {relative}")
        if path.is_file():
            yield path


def split_inspected(root, paths):
    """Separate a critic's inspected paths into case files and other entries.

    At least one real file shows the critic inspected the work. Other entries, such as
    a folder or a path with a note, are kept for audit rather than voiding the review.
    """
    files = {str(path.relative_to(root)) for path in target_files(root)}
    real, other = [], []
    for path in paths:
        (real if path.strip().removeprefix("./") in files else other).append(path)
    return real, other


def fingerprint(directory):
    root = Path(directory).resolve(strict=True)
    digest = hashlib.sha256()
    for path in target_files(root):
        digest.update(str(path.relative_to(root)).encode() + b"\0")
        with path.open("rb") as file:
            while block := file.read(65536):
                digest.update(block)
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def snapshot_context(directory):
    root = Path(directory).resolve(strict=True)
    files = list(target_files(root))
    if not files or len(files) > 100 or sum(p.stat().st_size for p in files) > 128_000:
        raise ValueError("Snapshot mode requires 1..100 UTF-8 files totaling at most 128 KB")
    sections = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        lines = "\n".join(f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1))
        sections.append(f"File: {path.relative_to(root)}\n{lines}")
    return (
        "\n\nAll case files are supplied below from the verified target. "
        "Analyze this snapshot directly. Do not call tools or execute commands.\n\n"
        + "\n\n".join(sections)
    )


REVIEW_GUIDES = {
    "pull_request": "pull-requests/README.md",
    "code": "code/README.md",
    "architecture": "architecture/README.md",
    "troubleshooting": "troubleshooting/README.md",
}


def skill_material(directory, review_type="code"):
    root = Path(directory).resolve(strict=True)
    files = [
        "SKILL.md",
        "REVIEW-PRINCIPLES.md",
        REVIEW_GUIDES[review_type],
        "references/recording.md",
    ]
    # Preserve frozen code experiments; new review types also freeze team policy.
    if review_type != "code":
        files.append("references/critics.md")
    texts = [(name, (root / name).read_text()) for name in files]
    digest = hashlib.sha256()
    for name, text in texts:
        digest.update(name.encode() + b"\0" + text.encode() + b"\0")
    context = "\n\n".join(f"{name}\n{text}" for name, text in texts[:3])
    return "sha256:" + digest.hexdigest(), context


class TrialFinding(Model):
    title: str
    severity: Severity
    confidence: Confidence
    category: Category
    location: str
    trigger: str
    impact: str
    evidence: str


class TrialResult(Model):
    status: Literal["completed", "blocked"]
    inspected_paths: list[str] = Field(max_length=100)
    limitations: list[str] = Field(max_length=30)
    findings: list[TrialFinding] = Field(max_length=30)


def event(run_id, payload):
    return {"event_id": str(uuid4()), "run_id": run_id, "occurred_at": now(), "data": payload}


def observation_batches(events):
    """Validate the entire trial output, then explicitly split before delivery."""
    validated = [Event.model_validate(item) for item in events]
    batches, current = [], []
    for item in validated:
        if current and (
            len(current) == MAX_BATCH_EVENTS
            or len(batch_body(Batch(events=[*current, item]))) > MAX_BATCH_BYTES
        ):
            batches.append(Batch(events=current))
            current = []
        if len(batch_body(Batch(events=[item]))) > MAX_BATCH_BYTES:
            raise ValueError("A single observation exceeds the collector byte limit")
        current.append(item)
    if current:
        batches.append(Batch(events=current))
    return batches


def codex_usage(events):
    # turn.completed is a per-turn measurement. Cache input is a subset, never added twice.
    usages = [e["usage"] for e in events if e.get("type") == "turn.completed" and e.get("usage")]
    if not usages:
        return None
    if not all("input_tokens" in u and "output_tokens" in u for u in usages):
        return None
    return Usage(
        source="runtime",
        input_tokens=sum(u["input_tokens"] for u in usages),
        output_tokens=sum(u["output_tokens"] for u in usages),
        cache_read_tokens=sum(u.get("cached_input_tokens", 0) for u in usages),
    )


def codex_file_tool_options(directory):
    """Disable Codex's shell and expose read-only file tools for this folder instead.

    Codex's shell sandbox needs Linux namespaces. Where a container forbids them, this
    gives Codex the same read-only access as Claude's Read, Grep and Glob.
    """
    return [
        "-c",
        "features.shell_tool=false",
        "-c",
        "features.unified_exec=false",
        "-c",
        "features.apps=false",
        "-c",
        "features.plugins=false",
        "-c",
        f"mcp_servers.review_files.command={json.dumps(sys.executable)}",
        "-c",
        "mcp_servers.review_files.args="
        + json.dumps(["-m", "critic_observer.readonly_files", str(directory)]),
        "-c",
        'mcp_servers.review_files.default_tools_approval_mode="approve"',
    ]


def execute_critic(
    client,
    critic,
    directory,
    instructions,
    trace_dir,
    timeout,
    codex_file_tools=False,
    codex_home=None,
):
    allowed = {"codex": {"reasoning_effort"}, "claude": {"effort", "max_budget_usd"}}[client]
    if set(critic["settings"]) - allowed:
        raise ValueError(
            f"Unsupported {client} settings: {sorted(set(critic['settings']) - allowed)}"
        )
    if critic["provider"] not in {None, client}:
        raise ValueError("Critic provider does not match the selected CLI")
    schema = TrialResult.model_json_schema()
    prompt = (
        critic["prompt"]
        + "\n\nReview goal:\n"
        + instructions
        + "\n\nInspect only the supplied working directory. Do not edit files, launch agents, "
        "or consult other reviews. Return concrete actionable findings in the required JSON "
        "schema. Report status blocked if you cannot inspect the work, never a clean review. "
        "List the relative paths of the files you actually inspected, one file per entry, "
        "without folders or notes, and any limitations. "
        "Use an empty findings array when none are supported. "
        + (
            "No shell is available; inspect files with the review_files tools "
            "(list_files, read_file, grep)."
            if client == "codex" and codex_file_tools
            else "All shell commands, if needed, must be routed through RTK."
        )
    )
    output_path, stderr_path = trace_dir / "stdout.jsonl", trace_dir / "stderr.txt"
    schema_path, final_path = trace_dir / "schema.json", trace_dir / "result.json"
    schema_path.write_text(json.dumps(schema))
    if client == "codex":
        command = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--cd",
            str(directory),
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(final_path),
            "--json",
            # Critics review only the frozen input; web search could reveal later fixes.
            "-c",
            'web_search="disabled"',
        ]
        if codex_file_tools:
            command.extend(codex_file_tool_options(directory))
        if critic["model"]:
            command.extend(["--model", critic["model"]])
        if "reasoning_effort" in critic["settings"]:
            command.extend(
                [
                    "-c",
                    "model_reasoning_effort=" + json.dumps(critic["settings"]["reasoning_effort"]),
                ]
            )
        command.append("-")
    else:
        command = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--no-session-persistence",
            "--tools",
            "Read,Grep,Glob",
            "--allowedTools",
            "Read,Grep,Glob",
            "--permission-mode",
            "dontAsk",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--json-schema",
            json.dumps(schema),
            # Keep trial execution isolated from the machine's client settings.
            *CLAUDE_ISOLATION_ARGS,
        ]
        if critic["model"]:
            command.extend(["--model", critic["model"]])
        for key, value in critic["settings"].items():
            command.extend(["--" + key.replace("_", "-"), str(value)])
    env = None
    if client == "codex" and codex_home:
        # A separate Codex home keeps global MCP servers, skills and instructions out.
        env = dict(os.environ, CODEX_HOME=str(codex_home))
    elif client == "claude":
        env = dict(os.environ, **CLAUDE_ISOLATION_ENV)
    with output_path.open("w") as output, stderr_path.open("w") as error:
        process = subprocess.run(
            command,
            input=prompt,
            text=True,
            cwd=directory,
            stdout=output,
            stderr=error,
            timeout=timeout,
            check=False,
            env=env,
        )
    # Claude marks failures in its JSON; Codex may log a retried error and still succeed.
    failure = ""
    if client == "claude":
        failure = claude_error(output_path.read_text())
    elif process.returncode:
        failure = codex_errors(output_path.read_text())
    if is_account_limit(failure):
        raise RuntimeError(f"{client} {LIMIT_REACHED}: {failure[:200]}; inspect {output_path}")
    if process.returncode:
        raise RuntimeError(
            f"{client} exited {process.returncode}; private diagnostics: {stderr_path}"
        )
    if output_path.stat().st_size > 8_000_000:
        raise RuntimeError(f"CLI output exceeds 8 MB; inspect {output_path}")
    if client == "codex":
        events = [json.loads(line) for line in output_path.read_text().splitlines() if line.strip()]
        result = TrialResult.model_validate_json(final_path.read_text())
        usage = codex_usage(events)
        model = critic["model"]
    else:
        output = json.loads(output_path.read_text())
        if output.get("is_error") or "structured_output" not in output:
            raise RuntimeError(f"Claude did not return structured success; inspect {output_path}")
        result = TrialResult.model_validate(output["structured_output"])
        measured = output.get("usage", {})
        usage_fields = {"source": "runtime"}
        # Preserve missing fields as unknown. Native input excludes cache reads in Claude.
        if measured.get("input_tokens") is not None:
            usage_fields["input_tokens"] = (
                measured["input_tokens"]
                + measured.get("cache_read_input_tokens", 0)
                + measured.get("cache_creation_input_tokens", 0)
            )
        if measured.get("output_tokens") is not None:
            usage_fields["output_tokens"] = measured["output_tokens"]
        if measured.get("cache_read_input_tokens") is not None:
            usage_fields["cache_read_tokens"] = measured["cache_read_input_tokens"]
        if output.get("total_cost_usd") is not None:
            usage_fields.update(cost_usd=output["total_cost_usd"], cost_basis="provider_estimate")
        usage = Usage(**usage_fields)
        models = list(output.get("modelUsage", {}))
        model = models[0] if len(models) == 1 else critic["model"]
    return result, usage, model


def run_trial(
    reporter,
    experiment_id,
    variant_id,
    case_id,
    trial,
    client,
    directory,
    skill_directory,
    timeout=300,
    trace_root=None,
    codex_file_tools=False,
    codex_home=None,
):
    brief = reporter.request(
        "GET",
        f"/api/experiments/{experiment_id}/brief",
        params={"variant_id": variant_id, "case_id": case_id},
    ).json()
    review_type = brief.get("review_type", "code")
    skill_revision, review_guidance = skill_material(skill_directory, review_type)
    if skill_revision != brief["skill_revision"]:
        raise ValueError("The review skill differs from the frozen experiment definition")
    root = Path(directory).resolve(strict=True)
    expected = brief["case"]["target_revision"]
    actual = fingerprint(root)
    if expected != actual:
        raise ValueError(f"Target fingerprint mismatch: expected {expected}, got {actual}")
    supplied = snapshot_context(root) if brief.get("input_mode") == "snapshot" else ""
    run_id = str(uuid4())
    traces = (
        Path(trace_root or Path.home() / ".local/state/critic-observer/trials") / run_id
    ).resolve()
    traces.mkdir(parents=True, mode=0o700)
    # Set a restrictive umask while this synchronous command writes private model transcripts.
    prior_umask = os.umask(0o077)
    run_started = {
        "type": "run_started",
        "project": brief["case"]["target"],
        "title": brief["case"]["title"],
        "review_type": review_type,
        "target": brief["case"]["target"],
        "target_revision": actual,
        "skill_revision": skill_revision,
        "client": client,
        "dataset": "benchmark",
        "experiment_id": experiment_id,
        "variant_id": variant_id,
        "case_id": case_id,
        "trial": trial,
        "expected_critic_ids": brief["variant"]["critic_ids"],
    }
    reporter.best_effort({"events": [event(run_id, run_started)]})
    failed, results, active = False, [], None
    usage, actual_model = None, None
    try:
        for critic in brief["critics"]:
            invocation_id = str(uuid4())
            active = invocation_id
            usage, actual_model = None, None
            reporter.best_effort(
                {
                    "events": [
                        event(
                            run_id,
                            {
                                "type": "invocation_started",
                                "invocation_id": invocation_id,
                                "critic_id": critic["id"],
                                "phase": "independent",
                                "round": 0,
                                "context": "independent",
                                "provider": client,
                                "model": critic["model"],
                                "scope": brief["case"]["instructions"]
                                + "\nInput mode: "
                                + brief.get("input_mode", "filesystem"),
                            },
                        )
                    ]
                }
            )
            trace = traces / invocation_id
            trace.mkdir(mode=0o700)
            try:
                result, usage, actual_model = execute_critic(
                    client,
                    critic,
                    root,
                    brief["case"]["instructions"]
                    + "\n\nReview guidance:\n"
                    + review_guidance
                    + supplied,
                    trace,
                    timeout,
                    codex_file_tools,
                    codex_home,
                )
                if fingerprint(root) != expected:
                    raise RuntimeError(
                        "Review target changed during execution; this trial is invalid"
                    )
                real_paths, other_paths = split_inspected(root, result.inspected_paths)
                if result.status == "blocked" or not real_paths:
                    failed = True
                    reason = (
                        "Review blocked"
                        if result.status == "blocked"
                        else "No inspected path is a file in the case "
                        f"(listed: {', '.join(result.inspected_paths)[:500] or 'none'})"
                    )
                    reporter.best_effort(
                        {
                            "events": [
                                event(
                                    run_id,
                                    {
                                        "type": "invocation_finished",
                                        "invocation_id": invocation_id,
                                        "status": "failed",
                                        "error": f"{reason}: " + "; ".join(result.limitations),
                                        "usage": usage.model_dump(mode="json") if usage else None,
                                        "resolved_model": actual_model,
                                    },
                                )
                            ]
                        }
                    )
                    active = None
                    continue
                events = []
                for n, finding in enumerate(result.findings, 1):
                    key = f"{invocation_id}.{n}"
                    events.append(
                        event(
                            run_id,
                            {
                                "type": "finding_recorded",
                                "finding_id": key,
                                "version": 1,
                                "issue_id": key,
                                "invocation_id": invocation_id,
                                **finding.model_dump(mode="json"),
                            },
                        )
                    )
                events.append(
                    event(
                        run_id,
                        {
                            "type": "invocation_finished",
                            "invocation_id": invocation_id,
                            "status": "completed",
                            "usage": usage.model_dump(mode="json") if usage else None,
                            "resolved_model": actual_model,
                            "error": None,
                        },
                    )
                )
                for batch in observation_batches(events):
                    reporter.best_effort(batch)
                if other_paths:
                    log.warning(
                        "critic_listed_non_file_paths run_id=%s invocation_id=%s entries=%s",
                        run_id,
                        invocation_id,
                        other_paths,
                    )
                results.append(
                    {
                        "critic_id": critic["id"],
                        "findings": len(result.findings),
                        "reported_model": actual_model,
                        "non_file_paths": other_paths,
                    }
                )
                active = None
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                failed = True
                log.warning(
                    "critic_trial_failed run_id=%s invocation_id=%s reason=%s",
                    run_id,
                    invocation_id,
                    exc,
                )
                reporter.best_effort(
                    {
                        "events": [
                            event(
                                run_id,
                                {
                                    "type": "invocation_finished",
                                    "invocation_id": invocation_id,
                                    "status": "failed",
                                    "error": str(exc),
                                    "usage": usage.model_dump(mode="json") if usage else None,
                                    "resolved_model": actual_model,
                                },
                            )
                        ]
                    }
                )
                active = None
            # Never feed earlier outputs to the next independent invocation.
        reporter.best_effort(
            {
                "events": [
                    event(
                        run_id,
                        {
                            "type": "run_finished",
                            "status": "failed" if failed else "completed",
                            "reason": "At least one critic failed"
                            if failed
                            else "Independent passes completed",
                        },
                    )
                ]
            }
        )
    except KeyboardInterrupt:
        if active:
            reporter.best_effort(
                {
                    "events": [
                        event(
                            run_id,
                            {
                                "type": "invocation_finished",
                                "invocation_id": active,
                                "status": "cancelled",
                                "error": "Local runner interrupted",
                                "usage": usage.model_dump(mode="json") if usage else None,
                                "resolved_model": actual_model,
                            },
                        )
                    ]
                }
            )
        reporter.best_effort(
            {
                "events": [
                    event(
                        run_id,
                        {
                            "type": "run_finished",
                            "status": "cancelled",
                            "reason": "Local runner interrupted",
                        },
                    )
                ]
            }
        )
        raise
    finally:
        os.umask(prior_umask)
    return {
        "run_id": run_id,
        "status": "failed" if failed else "completed",
        "critics": results,
        "trace_directory": str(traces),
        "pending_batches": len(list(reporter.directory.glob("*.json"))),
    }
