# Google ADK and Agent Skills

This document describes a possible integration between `xstate-python`, Google
Agent Development Kit (ADK) workflows, and Agent Skills. It is an architecture
proposal, not a claim that the integration exists in this repository.

## Status and decision

As of August 30, 2026:

- `xstate-python` 0.7.1 has no runtime dependencies and does not import, wrap,
  test, or ship Google ADK.
- ADK documents graph and dynamic workflows for Python starting in 2.0.0. The
  latest ADK Python GitHub release observed while writing this page was 2.8.0.
- ADK documents Agent Skills support for Python starting in 1.25.0, but still
  labels the feature experimental.
- No claim of API compatibility, checkpoint compatibility, or production
  readiness has been tested between `xstate-python` and ADK.

The recommended design is composition through an optional adapter or example,
not an ADK dependency in the `xstate` core package:

```text
Agent Skills                         Google ADK
discovery and instructions           model turns, tools, checkpoints, HITL
              \                         /
               \                       /
                ADK agent or workflow node
                           |
                    explicit event mapping
                           |
                     xstate-python
              deterministic domain statechart
```

Each layer has a different job:

| Layer | Owns | Does not own |
|---|---|---|
| Agent Skill | Discovery metadata, task instructions, references, assets, and optional scripts | Credentials, authorization, durable workflow state, or run-to-completion semantics |
| ADK | Agent and tool execution, workflow nodes, checkpoint and resume behavior, session integration, and human input | SCXML statechart semantics unless an application implements them |
| `xstate-python` | Hierarchical and parallel domain state, guarded transitions, internal events, eventless transitions, history, and SCXML-style run-to-completion | ADK sessions, model calls, durable distributed execution, or Skill discovery |

## Why the layers should not be collapsed

An ADK graph and an XState statechart are both drawn as nodes and edges, but
they do not have the same execution contract.

An ADK graph routes typed values between workflow nodes. A node may be an
agent, tool, function, or nested workflow. An ADK dynamic workflow uses normal
Python control flow and `ctx.run_node(...)`; ADK checkpoints successful child
node executions and can skip them during resume.

An `xstate-python` machine performs one external event as a macrostep. That
macrostep can contain several ordered microsteps, internal events, `always`
transitions, parallel regions, entry and exit behavior, and history. See
[Runtime choices](../concepts/runtimes.md) and
[SCXML import](../concepts/scxml.md).

Consequently, a general statechart-to-ADK-graph compiler would need to prove
semantic equivalence for at least transition priority, hierarchy, parallel
regions, internal queue order, history, eventless transitions, cancellation,
and resume. This repository has no such compiler or proof. Treating state names
as ADK node names would only work for a deliberately restricted subset.

## Recommended integration pattern

Use an ADK dynamic workflow as the durable outer orchestrator and an
`xstate-python` machine as its deterministic decision core.

1. Accept a typed ADK node input and map it to an explicit domain event.
2. Restore one `xstate-python` snapshot owned by the application.
3. Apply exactly one external event with `Machine.transition(...)` or a small
   adapter built on that API.
4. Persist the resulting snapshot before invoking an external effect.
5. Read an allowlisted command or route from the machine context.
6. Invoke the corresponding ADK node with `ctx.run_node(...)`.
7. Map the node result to a new domain event and repeat until the statechart is
   done, waiting, or failed.

The statechart should select a domain command such as `request-approval` or
`fetch-order`. The adapter should map that command to a registered ADK node.
Do not allow statechart data, model output, or Skill text to select an arbitrary
Python import, shell command, URL, or tool name.

The following is illustrative pseudocode. It has not been executed against an
installed ADK version in this repository:

```python
from google.adk import Context
from google.adk.workflow import node
from xstate import Machine
from xstate.snapshot import deserialize_snapshot, serialize_snapshot

NODES = {
    "request-approval": request_approval_node,
    "fetch-order": fetch_order_node,
}


@node(rerun_on_resume=True)
async def run_statechart(ctx: Context, node_input: dict) -> dict:
    snapshot = deserialize_snapshot(machine, node_input["statechart"])
    event = {"type": "START", "input": node_input["input"]}

    while snapshot.status == "active":
        snapshot = machine.transition(snapshot, event)
        checkpoint = serialize_snapshot(snapshot)

        command = snapshot.context.get("command")
        if command is None:
            return {"statechart": checkpoint, "status": "waiting"}

        child = NODES[command["type"]]
        result = await ctx.run_node(child, node_input=command["input"])
        event = {"type": "COMMAND_DONE", "output": result}

    return {"statechart": serialize_snapshot(snapshot), "status": snapshot.status}
```

The real adapter must use the exact result contract of its pinned ADK version.
It must also handle interruption separately from a successful result. ADK's
dynamic-workflow documentation requires parent nodes that call
`ctx.run_node(...)` to use `rerun_on_resume=True` and explains that child run
identifiers participate in resume behavior.

## State, checkpoint, and effect ownership

Choose one authoritative persisted copy of the statechart snapshot. A practical
choice is an application-owned field inside the ADK workflow input, output, or
session state. Do not independently update an ADK route flag and an XState
state value and then assume they will remain consistent.

`serialize_snapshot(...)` produces JSON-compatible state value, context,
status, history, output, and error fields. Current restoration has important
limits:

- It restores configuration, context, and recognized history node IDs.
- A serialized error is represented as text rather than reconstructed as the
  original exception.
- Callables, open network resources, timers, and in-flight actions are not
  durable snapshot data.
- Final output restoration has not been proven as a lossless ADK checkpoint
  round trip.

For an integration, add round-trip contract tests for every field the product
depends on before calling resume behavior durable.

External effects should be ADK nodes or registered tools with idempotency keys,
not interpreter actions whose completion exists only in process memory. Persist
the next state and an effect identifier before the effect, or use an outbox
with an atomic store if the effect and checkpoint cannot share a transaction.
ADK's node checkpointing does not by itself prove exactly-once behavior in an
external service.

Keep `after` timers and delayed sends inside `xstate-python` only for
process-local behavior. For a workflow that must survive process loss, use a
durable scheduler or ADK-supported pause/resume mechanism and feed the wake-up
back as a statechart event.

## Where Agent Skills fit

An Agent Skill can teach an ADK agent how to design, inspect, or operate a
statechart-backed workflow. ADK's experimental `SkillToolset` exposes tools to
load a Skill's instructions and resources and, when present, run its scripts.
That is useful inside an LLM-powered ADK node. It is not required for
deterministic function nodes.

A focused Skill might contain:

```text
xstate-workflow-design/
├── SKILL.md
├── references/
│   ├── event-contract.md
│   └── checkpoint-boundary.md
├── scripts/
│   └── validate-machine.py
├── assets/
│   └── machine-template.json
└── evals/
    └── evals.json
```

Only `SKILL.md` is required by the Agent Skills specification. `scripts/`,
`references/`, and `assets/` are recommended conventions. The official
evaluation guide currently recommends `evals/evals.json`; `evals/` is not a
required directory and the singular `eval/` spelling in some ecosystem advice
is not the documented convention.

The Skill should explain when to use the statechart, how to form events, how to
interpret snapshots, and when to stop for approval. It should not embed cloud
credentials, claim a script is authorized because it is listed in
`allowed-tools`, or dynamically download executable content during a run.

## Agent Skills rules: requirement versus advice

The following table fact-checks common claims against the current official
specification and guidance.

| Claim | Honest status |
|---|---|
| `name` is at most 64 characters, uses lowercase ASCII letters, numbers, and hyphens, has no leading, trailing, or consecutive hyphen, and matches its directory | Required |
| `description` is non-empty and at most 1,024 characters | Required |
| A specific description helps routing | Recommended; exact discovery behavior remains client-specific |
| `compatibility` is optional and at most 500 characters | Required if the field is present |
| `allowed-tools` is a space-separated string | Specified, but experimental and not uniformly supported |
| Every Skill needs `scripts/`, `references/`, `assets/`, or evals | False; only `SKILL.md` is required |
| Keep `SKILL.md` under 500 lines and about 5,000 tokens | Official recommendation, not a validation requirement |
| Resources load only when the `SKILL.md` body links to them | Too absolute; resources are loaded on demand, but exact selection and loading behavior belongs to the client |
| Skills fall into exactly three official archetypes | Ecosystem design advice, not part of the specification |
| skills.sh or `npx skills add` is the standard registry and installer | External ecosystem tooling, not part of the Agent Skills specification |
| A downloaded Skill is safe because its frontmatter validates | False; validation does not establish script safety, provenance, or authority |

`allowed-tools` should be treated as a client hint, not a portable security
boundary. The host application still needs to register tools, authenticate the
caller, enforce resource-level authorization, constrain filesystem and network
access, request approvals where required, and record effects.

## Suggested package boundary

Keep the first implementation outside `src/xstate/algorithm.py` and outside the
zero-dependency core. A small optional package or example can depend on a pinned
ADK version and provide:

- typed conversion between ADK node input and XState events;
- snapshot schema/version validation;
- an allowlisted command-to-node registry;
- interruption, cancellation, and error mapping;
- deterministic child-run identifiers where the workflow needs them;
- trace correlation between ADK workflow/node IDs and
  `xstate.MacrostepTrace` data;
- conformance tests for fresh run, resume, duplicate delivery, and failure
  after the state commit but before the external effect.

Do not modify the SCXML algorithm to imitate ADK checkpoint behavior. The
adapter should translate between the two runtimes while preserving each one's
contract.

## Smallest credible experiment

Before advertising an integration, build one bounded example with no live
external writes:

1. Pin `google-adk` in an example-specific lockfile or test environment.
2. Create a three-state machine: `idle -> awaiting_approval -> complete`.
3. Wrap it in an ADK dynamic workflow with one human-input child node.
4. Store and restore the serialized statechart snapshot across the pause.
5. Prove that resuming does not repeat a completed child node or statechart
   effect.
6. Run duplicate-event and crash-boundary tests with stable event and run IDs.
7. Capture the XState macrostep trace and ADK workflow events in one test
   receipt.
8. Add an Agent Skill only after a test shows that an LLM node needs reusable
   statechart guidance; compare runs with and without the Skill.

Success would prove this example on one pinned ADK version. It would not prove
general graph compilation, exactly-once effects, every Agent Skills client, or
production readiness.

## Sources and observation limits

Primary sources checked on August 30, 2026:

- [ADK graph-based workflows](https://adk.dev/graphs/)
- [ADK dynamic workflows](https://adk.dev/graphs/dynamic/)
- [ADK Agent Skills](https://adk.dev/skills/)
- [ADK Python 2.8.0 release](https://github.com/google/adk-python/releases/tag/v2.8.0)
- [Agent Skills specification](https://agentskills.io/specification)
- [Agent Skills authoring guidance](https://agentskills.io/skill-creation/best-practices)
- [Agent Skills evaluation guidance](https://agentskills.io/skill-creation/evaluating-skills)

The ADK APIs discussed here are version-sensitive, and its Skills support is
experimental. Recheck the documentation and lockfile before implementing or
upgrading an adapter.
