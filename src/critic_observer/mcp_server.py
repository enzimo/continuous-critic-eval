"""MCP tools use the same validated application operations as HTTP."""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from .models import Batch, Critic


def observations(detail):
    """Review clients never receive independent answer keys or outcome judgments."""
    return {
        "run": {k: v for k, v in detail["run"].items() if k != "evaluation"},
        **{k: detail[k] for k in ("invocations", "findings", "verdicts", "decisions")},
    }


def build_mcp(store, settings):
    from urllib.parse import urlsplit

    public_host = urlsplit(settings.public_url).netloc
    server = FastMCP(
        "Critic observer",
        stateless_http=True,
        json_response=True,
        instructions="Record evidence using stable event IDs. Register critics, then start a run. "
        "Submit dependent events in order. On conflict retry after delivering dependencies. "
        "Only an operator can independently adjudicate correctness. Never invent usage. "
        "Read reporting instructions at observer://reporting before the first recorded review.",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[public_host, "localhost:*", "127.0.0.1:*"],
            allowed_origins=[settings.public_url],
        ),
    )

    @server.tool()
    def register_critic(definition: Critic) -> dict:
        """Register an immutable critic configuration. Identical definitions return the same ID."""
        return store.register_critic(definition)

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
    )
    def list_critics(role: str = "", specialty: str = "") -> list[dict]:
        """List critic definitions as summaries, most-used first, to find one to reuse.

        Optionally filter by specialty or legacy role (case-insensitive).
        Prompts are shortened; call get_critic for a full definition.
        """
        return store.critic_summaries(role, specialty)

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
    )
    def get_critic(critic_id: str) -> dict:
        """Get one complete critic definition, including its full prompt and settings."""
        return store.critic(critic_id)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True))
    def record_review_events(batch: Batch) -> dict:
        """Atomically record a batch with stable event IDs; retries are idempotent.

        Start the run before its invocations, then findings and exact-version verdicts.
        Only observation events are permitted. Operator judgments belong in the UI.
        """
        return store.ingest(batch, actor="ingest")

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
    )
    def get_review(run_id: str) -> dict:
        """Inspect a registered review's observations, without independent judgments."""
        return observations(store.run(run_id))

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
    )
    def get_experiment_brief(experiment_id: str, variant_id: str, case_id: str) -> dict:
        """Get frozen inputs and critic prompts. Expected defects are deliberately excluded."""
        return store.brief(experiment_id, variant_id, case_id)

    @server.resource("observer://reporting")
    def reporting() -> str:
        return (
            "Keep one run_id across the review. Use a fresh run for a new target revision. "
            "Use review_type=architecture for architecture, designs and implementation plans, "
            "with a separate run_id from any PR review of the same revision. Select the "
            "architecture starting team in references/critics.md; PR team results do not "
            "establish architecture effectiveness. "
            "The lead collates subagent results. "
            "Register reusable critic definitions with an explicit specialty, such as Security, "
            "Bug hunting, Requirements, or Evidence and testing. Specialty is what the reviewer "
            "checks; phase records the responsibility (lead=coordinator, independent=reviewer, "
            "critique=challenger), and context records exposure to earlier findings. "
            "Do not use lead or independent critic as a specialty. General review is appropriate "
            "when no narrower specialty applies. Keep the legacy role label stable for existing "
            "definitions; prompt holds only reusable specialty instructions. Never put project "
            "names, paths, revisions, PR numbers, dates, or round labels in a definition. "
            "Check list_critics for an existing definition of the role first. "
            "Each independent pass and critique round gets its own invocation_id, critic_id, "
            "actual provider/model if known, and a scope holding the task-specific brief. "
            "The definition prompt plus the invocation scope record what the critic was told. "
            "Record findings with stable finding_id, issue_id, and contiguous versions. "
            "A verdict must reference finding_id and finding_version. Preserve evidence on both "
            "sides. Merge duplicate issues explicitly, before operator adjudication. "
            "Record invocation_finished for every pass, including failures. "
            "Finish the run with a reason. Do not call agreement truth. "
            "Use the installed critic-observer submit client for durable offline delivery if "
            "MCP is unavailable. An unregistered skill invocation is invisible to this server."
        )

    @server.resource("observer://schema")
    def schema() -> dict:
        return Batch.model_json_schema()

    return server
