// Execute the literal fixture charts with the installed, pinned XState runtime.
const fs = require('node:fs');
const { createMachine, createActor, assign, raise, fromCallback, SimulatedClock } = require('xstate');
const version = require('xstate/package.json').version;
const clone = (value) => structuredClone(value);

function run(fixture) {
  const clock = new SimulatedClock();
  const actions = [];
  const children = [];
  const errors = [];
  let generation = 0;
  const machine = createMachine(fixture.chart, {
    actions: {
      record: ({ context, event }, params) => actions.push({
        time: clock.now(), context: clone(context), event: clone(event), params: clone(params ?? null),
      }),
      increment: assign({ n: ({ context }) => context.n + 1 }),
      raiseInner: raise({ type: 'INNER' }),
    },
    guards: { allowed: ({ event }) => event.allow === true },
    delays: fixture.delays ?? {},
    actors: {
      worker: fromCallback(({ input }) => {
        const current = ++generation;
        children.push({ time: clock.now(), kind: 'start', generation: current, input: clone(input) });
        return () => children.push({ time: clock.now(), kind: 'stop', generation: current });
      }),
    },
  });
  const actor = createActor(machine, { clock });
  // XState routes actor failures to observers rather than always throwing to send().
  actor.subscribe({ error: (error) => errors.push({ type: error.name, message: error.message }) });
  const steps = [];
  try {
    for (const command of fixture.commands) {
      actions.length = children.length = errors.length = 0;
      try {
        if (command.type === 'start') actor.start();
        else if (command.type === 'send') actor.send(command.event);
        else if (command.type === 'advance') clock.increment(command.ms);
        else throw new Error(`Unknown command: ${command.type}`);
      } catch (error) {
        errors.push({ type: error.name, message: error.message });
      }
      const snapshot = actor.getSnapshot();
      steps.push(clone({
        time: clock.now(), value: snapshot.value, context: snapshot.context,
        status: snapshot.status, output: snapshot.output ?? null,
        actions, children: { ids: Object.keys(snapshot.children), events: children },
        errors,
      }));
      if (errors.length) break;
    }
    return steps;
  } finally {
    // Teardown is outside the command trace; fixture transitions test child cleanup.
    actor.stop();
  }
}

if (process.version !== 'v24.22.1' || version !== '5.33.4') {
  console.error(`Reference version mismatch: Node ${process.version}, XState ${version}; require v24.22.1 / 5.33.4`);
  process.exitCode = 1;
} else {
  const fixtures = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  console.log(JSON.stringify({
    node: process.version, xstate: version,
    results: Object.fromEntries(fixtures.map((fixture) => [fixture.id, run(fixture)])),
  }));
}
