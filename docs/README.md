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
- [Runnable examples](./examples/README.md): complete programs exercised by the
  test suite.
