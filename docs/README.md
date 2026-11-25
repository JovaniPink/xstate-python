# Documentation

`xstate-python` provides Python statecharts and actors with typed domain data,
ordinary functions, explicit lifecycle contracts, and a tested XState JSON
boundary. Start with the concepts that match the runtime you need:

- [Machines and implementations](./concepts/machines-and-implementations.md):
  XState JSON, events, actions, guards, delays, `setup()`, and pure transitions.
- [XState compatibility](./concepts/xstate-compatibility.md): the pinned
  comparison contract, numeric JSON delays, migration, and known differences.
- [Runtime choices](./concepts/runtimes.md): `Machine.transition`, the sync and
  async interpreters, actors, subscriptions, clocks, and run-to-completion.
- [Actors](./concepts/actors.md): actor lifecycle, invocation, actor logic,
  trees, and messaging.
- [Snapshot persistence](./concepts/persistence.md): checkpoint format,
  restoration, compatibility, and operational limits.
- [SCXML import](./concepts/scxml.md): path-based loading, converted elements,
  parallel execution, safe conditions, and current limits.
- [Google ADK and Agent Skills](./integrations/adk-and-agent-skills.md): an
  honest proposed boundary between deterministic statecharts, durable agent
  workflows, and progressively loaded Skill instructions.
- [Local fetch inspector](./concepts/local-inspector.md): operate a synthetic
  retry workflow, inspect microsteps, and reproduce direct-execution comparisons.
- [Runnable examples](./examples/README.md): complete programs exercised by the
  test suite.

## Plans and evidence

- [Pythonic agent-workflow research](./plans/pythonic-agent-workflows-research.md):
  the November 20, 2026 product research and November 25 implementation status;
  provider and Measured Skills evidence, a bounded observation of this PR series,
  and remaining gates for a contribution-workflow application.
- [Statechart and workflow direction](./plans/statechart-workflow-roadmap.md):
  proposed XState compatibility milestone, structured diagnostics, restoration
  contracts, scenario tooling, and restartable workflow examples, with ordered
  work packages and acceptance criteria.
- [November 12, 2026 evidence](./plans/statechart-workflow-evidence.md): pinned
  repository observations, baseline test receipts, and runnable Python/JavaScript
  comparisons supporting that plan. This is a dated audit, not an implementation
  completion claim.
