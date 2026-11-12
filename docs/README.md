# Documentation

`xstate-python` loads XState-style statechart data and runs it with Python
implementations for the live parts of a machine. Start with the concepts that
match the runtime boundary you need:

- [Machines and implementations](./concepts/machines-and-implementations.md):
  XState JSON, events, actions, guards, delays, `setup()`, and pure transitions.
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

- [Statechart and workflow direction](./plans/statechart-workflow-roadmap.md):
  proposed XState compatibility milestone, structured diagnostics, restoration
  contracts, scenario tooling, and restartable workflow examples, with ordered
  work packages and acceptance criteria.
- [November 12, 2026 evidence](./plans/statechart-workflow-evidence.md): pinned
  repository observations, baseline test receipts, and runnable Python/JavaScript
  comparisons supporting that plan. This is a dated audit, not an implementation
  completion claim.
