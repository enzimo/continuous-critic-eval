# Architecture reviews

Architecture reviews run alongside PR reviews with their own recorded runs,
team observations and statistics. Use the [architecture guide](../architecture/README.md)
for a proposed design, implementation plan or existing system architecture.

The starting team is Architecture requirements tracer, Architecture boundary
reviewer, Architecture failure analyst and Architecture reality checker.
These reusable prompts are in the built-in catalog. The team covers intent,
component ownership, failure sequences and the evidence behind design claims.
Evaluate architecture teams on matched architecture cases with independent
assessment. See [selection policy](../references/critics.md).

Ask an agent with this skill and a configured collector:

> Review this system's architecture using project-review-process. Freeze the
> design documents and relevant code/configuration revision, use the architecture
> starting team, and record it as a production architecture review. Keep any PR
> review of the same revision in its own run.

The lead records the actual participants, scope, findings, explicit duplicate
merges, reviewer decisions, challenges and completion. Available runtime tokens
and cost are recorded; missing measurements remain unknown. Reviewer acceptance
is provisional until an operator independently judges it. Registering the four
definitions does not create a review or any statistics.

## Website and comparisons

The website starts with Pull requests. Select Architecture in Review type to
load architecture contributions, issue assessment, disagreement, rounds, quality,
review runs and experiments. No website option pools review types. Shared critic
definitions remain visible in the authoring catalog, while all their result
tables use only the selected type. Detail pages label their actual review type,
including when opened directly. Dataset selection still separates production,
benchmark and demonstration history within each type.

Experiments freeze a single review type. For architecture use:

```bash
critic-observer skill-fingerprint /path/to/project-review-process --review-type architecture
```

Use that fingerprint and select Architecture when creating the experiment.
The existing trial command reads the type from the frozen definition, loads the
architecture guide, and files its run under architecture. Answer keys remain
operator-only. Compare teams on shared architecture cases with independent
assessment before recommending a winner. Do not pool PR trial scores.

Existing experiments without a type remain code experiments with unchanged IDs.
Existing recorded runs keep their original type. API clients can explicitly
request `review_type=` for a cross-type export or analysis; omitted dashboard
and experiment-list types default to `pull_request`. This explicit API escape
does not appear in website controls. Metric definitions remain 1.2.

Rebuild and redeploy the collector to change the hosted website. Skill-linked
clients use this checkout's guidance immediately; other machines need the same
reviewed revision. Configure each client's collector connection and credentials
using [the quickstart](../QUICKSTART.md).
