# Documentation

`xstate-python` loads XState-style statechart data and runs it with Python
implementations for the live parts of a machine. Start with the concepts that
match the runtime boundary you need:

- [Machines and implementations](./concepts/machines-and-implementations.md):
  XState JSON, events, actions, guards, delays, `setup()`, and pure transitions.
- [Runtime choices](./concepts/runtimes.md): `Machine.transition`, the sync and
  async interpreters, actors, subscriptions, clocks, and run-to-completion.
- [Runnable examples](./examples/README.md): complete programs exercised by the
  test suite.

Additional guides for actors, persistence, and SCXML import are being added as
part of the current documentation milestone.
