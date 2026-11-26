# Documentation

Build Python statecharts with ordinary functions, typed domain data, and explicit
resource lifecycles. Choose the path that matches what you want to do next.

## Start Here

1. [Getting started](getting-started.md): install the source, run your first
   chart, and choose an execution API.
2. [Runnable examples](examples/README.md): a guided catalog with commands,
   expected results, and the boundary each program demonstrates.
3. [Machines and implementations](concepts/machines-and-implementations.md):
   states, events, guards, assignments, named functions, and strict configuration.
4. [Typing](concepts/typing.md): typed event mappings, handler arguments,
   dataclass contexts, and the limits of static validation.

## Build An Application

| Task | Guide | Runnable example |
| --- | --- | --- |
| Model a review with Python domain data | [Typing](concepts/typing.md) | [Typed context](examples/typed_context.py) |
| Bind CI and review evidence to a code revision | [Revision gate](guides/revision-gate.md) | [Python](examples/revision_gate.py) + [JSON](examples/revision_gate.json) |
| Choose pure, sync, async, or actor execution | [Runtime choices](concepts/runtimes.md) | [Async workflow](examples/async_workflow.py) |
| Invoke work and retry a failure | [Actors](concepts/actors.md) | [Fetch with retry](examples/fetch_with_retry.py) |
| Stop, serialize, and restore chart state | [Snapshot persistence](concepts/persistence.md) | [Snapshot resume](examples/snapshot_resume.py) |
| Wrap a chart in typed application methods | [Controllers](concepts/controllers.md) | [Docking controller](examples/docking_controller.py) |
| Explore a chart's state and microsteps | [Local inspector](concepts/local-inspector.md) | [Inspector server](examples/local_inspector.py) |
| Import the supported SCXML subset | [SCXML import](concepts/scxml.md) | [SCXML toggle](examples/scxml_toggle.py) |

The revision gate uses recorded inputs to teach evidence policy. A real host
still owns event authority, durable storage, and tool execution. Snapshot
restoration does not recover external effects or in-flight work.

## Contracts And Reference

- [XState compatibility](concepts/xstate-compatibility.md): the pinned comparison
  contract, supported numeric JSON delays, migration notes, and known differences.
- [Action arguments and migration](concepts/machines-and-implementations.md#action-arguments-and-migration):
  the context and event each deferred action observes.
- [Runtime lifecycle and failure](concepts/runtimes.md): action completion,
  reentry, actor ownership, cleanup, and asynchronous execution boundaries.
- [Microstep traces](concepts/runtimes.md#bounded-execution-and-microstep-traces):
  bounded execution and immutable observations for diagnostics.
- [Persistence contract](concepts/persistence.md): stored output, constructor
  snapshots, compatibility, and application-owned recovery responsibilities.
- [Library comparison](comparison.md): the existing comparison of statechart
  capabilities and Python integration styles.

## Product Direction And Research

These documents record rationale and proposals. Use the guides and examples
above for implemented public behavior.

- [Product notes](PRODUCT.md): current capabilities, product hypotheses, and
  evidence required before expanding the library.
- [Pythonic agent-workflow research](plans/pythonic-agent-workflows-research.md):
  the November 20, 2026 product research and November 25 implementation status;
  provider and Measured Skills evidence, a bounded observation of the PR series,
  and remaining gates for a contribution-workflow application.
- [Statechart and workflow direction](plans/statechart-workflow-roadmap.md):
  compatibility, diagnostics, restoration contracts, scenario tooling, and
  restartable workflow proposals with ordered acceptance criteria.
- [November 12, 2026 evidence](plans/statechart-workflow-evidence.md): pinned
  repository observations, baseline test receipts, and runnable Python/JavaScript
  comparisons. This is a dated audit, not an implementation completion claim.
- [Gstate and a Python-first runtime](plans/gstate-pythonic-runtime-research.md):
  the November 25 source audit of composition, ownership, observation, and
  restoration, with merged runtime improvements and remaining evidence gates.
- [Google ADK and Agent Skills](integrations/adk-and-agent-skills.md): a proposed
  integration boundary between statecharts, durable workflows, and progressively
  loaded Skill instructions.

For development commands and contribution conventions, see
[CONTRIBUTING.md](../CONTRIBUTING.md).
