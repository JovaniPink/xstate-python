# What gstate can teach a Python-first xstate-python

Research date: November 25, 2026. Status: research and proposed work; no runtime
change is delivered by this document.

## Recommendation

Borrow gstate's explicit contracts for composition, ownership, lifecycle, and
observation. Adapt those contracts to ordinary Python functions, typed events,
dataclass contexts, and the existing statechart engine. Preserve the separation
between transition computation and external effects.

For the proposed agent-assisted software-development niche, the useful product
is a small, inspectable coordinator that knows which goal revision, code
revision, attempt, and evidence authorize the next action. A statechart should
coordinate that work; provider harnesses should execute it. Gstate supplies
useful mechanisms and counterexamples, but its example is not evidence that we
should build a general workflow platform.

The highest-value immediate work is small: fix observable factory input,
reject duplicate state IDs, and avoid unnecessary initialization when an actor
receives a snapshot at construction. These three slices now have draft
implementations linked below. Then test the coordination hypothesis with
recorded events and the existing Measured Skills evaluation plan before
extracting new public APIs.

This follows the user's Python-first direction and the proposal in
[draft PR #63](https://github.com/JovaniPink/xstate-python/pull/63). That PR was
still open and unmerged when researched. The current merged product notes still
describe the older compatibility-first positioning; this document does not
silently treat the draft as merged policy. The supported JSON boundary and its
behavioral tests remain responsibilities of the library.

## Evidence and revision boundary

| Project | Revision inspected | Status at the initial research snapshot |
| --- | --- | --- |
| gstate | [`fbbb3d8`](https://github.com/floodfx/gstate/commit/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c) | `main`, release `v0.3.5`, November 19, 2026 |
| xstate-python | [`fdc5df0`](https://github.com/JovaniPink/xstate-python/commit/fdc5df06ce87622fbc91aa88a5d8ab09de62041d) | `master`, after PR #64 merged November 25, 2026 |
| Python-first proposal | [`34d80b0`](https://github.com/JovaniPink/xstate-python/commit/34d80b0b7937e30dbcbccc803afa43b1885381d6) | Draft PR #63; proposal, not merged runtime behavior |

Sources below are pinned to those revisions. **Observed** means code, a named
test, or an executable probe supports the claim. **Inference** means the design
consequence follows from those observations. **Proposal** means behavior that
does not yet exist. An issue remaining open is not proof that its original bug
still exists.

An important planning correction: [PR #64][P64] already preserves stored
completed output during `deserialize_snapshot()`, including explicit null and
other falsey values, with detached copies and defined legacy fallback. Do not
schedule that repair again. Issue #54 remains open for broader restoration
questions. The documented construction-time initialization caveat is a distinct
follow-up. [PERSIST]

### Implementation follow-through — November 25, 2026

The maintainer authorized proceeding with the proposals after reviewing current
PRs and issues. The first three slices are implemented in independent draft PRs
based on `master` at `fdc5df06ce87622fbc91aa88a5d8ab09de62041d`:

| Proposal | Draft implementation | Acceptance and remaining boundary |
| --- | --- | --- |
| A — Observable factory input | [#66](https://github.com/JovaniPink/xstate-python/pull/66), [implementation](https://github.com/JovaniPink/xstate-python/commit/ee8695feee8d1600d94bbae0b99036ce32c312d0) | Shared promise/observable binding, actual emissions, call-once errors, cancellation, and type inference; resolves #53 when merged |
| B — Definition validation | [#67](https://github.com/JovaniPink/xstate-python/pull/67), [implementation](https://github.com/JovaniPink/xstate-python/commit/24125bc938a479282382e0f2362ccbc751aa1aec) | Reject duplicate resolved state IDs with distinct paths; classify ignored `invoke.systemId` as unsupported in strict mode; broader normalized diagnostics/composition remain proposed |
| C — Constructor restoration | [#68](https://github.com/JovaniPink/xstate-python/pull/68), [implementation](https://github.com/JovaniPink/xstate-python/commit/ad04c891ce3b40eb594065d69a893de31797897b) | A constructor-supplied snapshot replaces fresh initialization; default eager construction and normal startup policies remain; #54 stays open |

These PRs contain their regression, migration, local validation, and hosted CI
records. They are draft implementations, not merged capabilities. Their
research baselines below remain pinned historical observations; for example,
the successful #53 reproduction describes `fdc5df0`, not the #66 branch.

The existing [Python-first direction PR #63](https://github.com/JovaniPink/xstate-python/pull/63)
is updated in place to reflect this sequence. PR #64's completed-output repair
is already merged and is not scheduled again. The broader restoration issue
[#54](https://github.com/JovaniPink/xstate-python/issues/54), contribution/recovery
experiment [#56](https://github.com/JovaniPink/xstate-python/issues/56), and
distribution decision [#57](https://github.com/JovaniPink/xstate-python/issues/57)
remain open. The Measured comparison remains `prepared_not_run`; these runtime
fixes do not establish application value or justify a durable host.

## 1. The architectural comparison

Gstate is a Go-native statechart implementation inspired by XState. Its generic
machine uses state and event string types plus a data type that implements
`Clone()`. A builder creates a shared machine definition; actors own live data,
an active configuration, history, a buffered event mailbox, timers, invocation
generations, and lifecycle observers. [GTYPES] [GACTOR]

Xstate-python already provides more than a JSON parser: generic machine,
context, event and output types; handler protocols; context adapters; a pure
transition API; sync and async interpreters; actor logic; microstep inspection;
simulated clocks; and dependency-free Mermaid output. These are foundations to
improve, not missing features to reimplement. [PTYPING] [PCONTEXT] [PTRACE]
[PRUNTIMES] [PMERMAID]

| Concern | Gstate's approach | Current Python foundation | Useful transfer |
| --- | --- | --- | --- |
| Authoring | Generic fluent builder and reusable builder functions | Typed JSON-shaped configuration, `setup()`, ordinary Python callbacks | Improve Python authoring and diagnostics over the existing normalizer |
| Composition | Additive entry/exit reducers; exclusive fields; checked replacement | Application factories and explicit registry overrides | Make conflicting structural changes fail visibly |
| Data ownership | Required user-supplied `Clone()` and ownership rules | Default deep copy; configurable `ContextAdapter`; immutable dataclass policy | Explain ownership and measure realistic copy costs |
| Events | Typed event IDs; optional data reducer attached to a send | Typed event mappings with payloads | Preserve data events and explicit assignment; avoid closures as persisted commands |
| Lifecycle | Enqueue errors, bounded mailbox, `Done`, `StopCtx` | RTC queues, awaitable async sends, invocation reconciliation | Specify acceptance, completion, cancellation and termination separately |
| Observation | Nine opt-in event kinds | Selected-transition and microstep traces; subscriptions | Add correlated runtime outcomes where a consumer needs them |
| Restore | Normalized configuration; optional restart of restored services | Detached serialization; context codecs; stored completed output | Separate decode, inspection, and effectful resume |
| Validation | Build-time structural checks | Raw-key diagnostics and parser resolution | Close concrete structural gaps before adding a new DSL |
| Tooling | Race tests, fuzzing, real Mermaid rendering, generated examples | SCXML fixtures, pinned XState comparison, deterministic clocks, inspectors | Add boundary-focused properties and renderer checks |

The implementations have materially different execution policies. Similar
names are not a compatibility specification.

### Do not transplant the execution algorithm

Gstate selects enabled external-event transitions before running their actions,
then executes each selected transition's entire exit/action/entry sequence.
Python's `microstep()` executes exits for the selected set, transition content,
and then entries. That distinction is observable when parallel regions share
context or emit effects. [GSELECT] [PSTEP]

Gstate also makes targeted self-transitions external, resolves equal-depth
external conflicts by state ID, and chooses one eventless transition per
stabilization iteration. Python already has its documented reentry policy and
SCXML-oriented ordering. Importing those Go policies would change behavior and
would require explicit compatibility decisions, fixtures, and migration work.
[GSELECT] [GCOMPLETE] [PCOMPAT]

## 2. Checked composition is the strongest authoring idea

### What gstate actually provides

`Use()` applies ordinary builder functions in order. `Extend()` reopens an
existing state. Entry and exit reducers append in registration order. Repeated
writes to exclusive settings such as initial state and invocation record errors
and retain the earlier definition. Intentional replacement states the expected
prior value:

- `ReplaceInitial(expectedChild, nextChild)`;
- `ReplaceInvoke(expectedLabel, ...)`;
- `ReplaceOnDone(expectedTarget)`.

These are useful preconditions on structural edits. If two extensions both
expect the original default, the second cannot silently replace the first.
They do not make arbitrary plugin execution commutative; additive ordering and
intentional replacement chains remain meaningful. [GBUILDER] [GCOMPOSITION]

For our proposed domain, imagine a base workflow that advances directly from
review to delivery. One extension inserts an approval gate; another inserts a
policy check. A generic dictionary merge can accidentally replace a route. A
checked replacement can report the state path, expected route, actual route,
and extension responsible before any worker starts.

### What Python should take

Begin with ordinary factory functions that return fresh configurations and
named implementations. For a real consumer, prototype an explicit composition
operation with these rules:

1. Declare which fields append and which have one owner.
2. Require a precondition for structural replacement.
3. Preserve deterministic declaration order.
4. Report both conflicting sources and the configuration path.
5. Normalize through the same parser and execute through the same engine.
6. Avoid mutating shared configuration after machine construction.

Use stable component identities for replacement preconditions, separate from
human-readable diagram labels. Preserve scoped local names and individual
action occurrences in Python traces. Gstate uses an invocation label as a
replacement contract and can combine multiple assignments into one reducer
notification; neither detail needs to become Python's policy. [GBUILDER]

This is a proposal for an example-owned helper first. Extract a public builder
only after independent consumers demonstrate repeated friction. A typed
Python facade should improve state/target references and callback checking,
not create a second transition engine or another subtly different action API.

Gstate's builder is not a fully immutable intermediate representation:
`BuildWithError()` returns the same mutable machine, and exported maps and
retained builder references remain caller-owned hazards. Its generic string
types prevent some type mixing, but untyped string literals can still contain
typos. Build-time validation remains necessary. Python should claim exactly
the combination it provides: static hints plus runtime structural validation.
[GTYPES] [GBUILDER]

## 3. Structural diagnostics should precede a larger DSL

Gstate validates state hierarchy, target existence, initial-child relationships,
final-state restrictions, invoke targets, completion routes and selected
cross-region rules. `Validate()` and `BuildWithError()` avoid executing runtime
callbacks, but return a first error with unspecified ordering; declaration-time
duplicate IDs still panic. Its validation API is useful, not a model to copy
literally into Python. [GBUILDER]

Python already has structured `ConfigIssue` records with document paths and
stable traversal order. They currently identify unknown and unsupported keys;
they are not a comprehensive structural validator. [PVALIDATE]

### Observed gap: duplicate explicit IDs

This configuration is accepted even with `strict=True` at the inspected Python
revision:

```python
Machine(
    {
        "id": "example",
        "initial": "a",
        "states": {"a": {"id": "duplicate"}, "b": {"id": "duplicate"}},
    },
    strict=True,
)
```

The initial configuration contains `a`, while the ID registry maps `duplicate`
to `b`: `_register()` overwrites the earlier mapping. A local probe also
confirmed that `find_config_issues()` returns no findings. This creates an
ambiguous addressing and restoration boundary. [PREGISTER] [PVALIDATE]

**Proposed first validation PR:** reject duplicate resolved IDs before a
registry entry is overwritten, with both declaration paths in the error. Cover
explicit duplicates, collisions with generated IDs, valid repeated local state
names under different parents, and references/history targeting distinct IDs.
Decide and document whether rejection applies at all constructors or initially
through strict validation; ambiguous IDs should never silently become a
supported addressing contract.

Broader diagnostics can follow concrete findings. Do not import all gstate
restrictions wholesale: globally unique local names, required completion
fallbacks, and cross-region rules are design choices that must be reconciled
with Python's supported JSON and SCXML behavior.

One adjacent source-confirmed gap deserves its own small classification decision:
strict validation recognizes `invoke.systemId`, but invoke normalization drops
that field. Either implement the advertised alias or classify it as unsupported
until implemented. Recognition by the key validator alone does not establish
behavioral support. [PVALIDATE] [PINVOKEPARSER]

### A separate Pythonic correctness fix

Issue #53 remains reproducible: `from_observable()` calls a factory through
keyword-name filtering. An async generator factory named `input` succeeds;
the same unary factory named `count` fails with a missing positional argument.
Promise logic already has a richer call-binding path. Normalize the observable
factory once, preserving supported legacy forms, and report genuine signature
errors clearly. No new authoring facade is needed to fix this. [POBSERVABLE]
[PPROMISE]

## 4. Data ownership: make the cost and the contract explicit

Gstate requires `Clone()` and uses it for snapshot/data reads, invoked-service
inputs, and data-bearing observer payloads. The type system verifies that the
method exists; it cannot prove that nested maps, slices, or pointers were copied.
`Start()` can take ownership of the supplied initial data without cloning it.
Guards and reducers still require disciplined behavior; a `Clone()` method does
not sandbox arbitrary callback mutations. [GTYPES] [GACTOR] [GOBS]

A local probe supplied a correct deep clone, then deliberately mutated a map
inside a guard that returned false. The event was dropped and the original state
remained active, but the map retained the mutation. This demonstrates the
documented purity/ownership boundary; it is not a failure of a pure guard.
[GSELECT]

Python's default context adapter already snapshots mutable data, and causal
action capture preserves the context at each deferred effect's position. The
immutable dataclass adapter provides an existing route to inexpensive ownership
when the application actually uses immutable contents. A frozen dataclass
containing a mutable list is not deeply immutable. [PCONTEXT] [PHANDLERS]

For a repository workflow, keep large documents out of every action snapshot.
Use small immutable references containing a document identity, content digest,
revision, and storage locator. The host owns document storage and verifies the
referenced contents when needed. This avoids copying prompt histories, patches,
and full test logs through every transition while keeping evidence attributable.

Gstate's `SendWith()` is also instructive: it applies a payload reducer to a
clone before guard selection, retaining that candidate data only if a
transition is selected. The rollback concerns actor data when the event is
unhandled; it is not a database transaction or rollback of external effects.
[GSEND]

Python already has event payloads. Prefer serializable typed events and explicit
`assign` operations after successful guard selection. A lambda that mutates
data on enqueue is difficult to persist, inspect, compare, or replay. For our
niche, a recorded `VerificationCompleted` event tied to a goal, code revision,
attempt and evidence reference is more useful than an opaque mutation closure.

### Measure ownership on the actual workflow

The existing Python benchmark is a useful starting point. Add the representative
workflow when it exists and report context size, mutable versus immutable
policy, effect count, tracing configuration, allocations/memory, and latency
units separately. The previous synthetic causal-binding cost should motivate
measurement; it is not a reason to weaken captured-argument correctness.
[PBENCH]

Do not cite gstate's historical benchmark table as a current zero-allocation
guarantee. `BENCHMARKS.md` describes Go 1.26.2 on an M1 Pro and still names an
obsolete allocation test. The current allocation assertion measures enqueue
into a buffered mailbox with no consumer. The lifecycle benchmark measures
start, 100 transitions, and stop. Also, the helper behind the benchmark named
`TransitionOnlyObserver` installs `ObserverFuncs`, which implements all event
kinds. These are different workloads. [GBENCHDOC] [GBENCH]

## 5. Lifecycle guarantees are more useful than another actor abstraction

Gstate clearly separates several milestones:

| Milestone | Observed contract | Consequence for a Python host |
| --- | --- | --- |
| Enqueue acceptance | `SendCtx()` succeeds when the mailbox accepts the event | Acceptance is not processing, verification, or durable storage |
| Backpressure | Mailbox capacity is configurable; enqueue can wait for a slot, cancellation, or shutdown | Specify capacity and overload behavior if the host buffers work |
| Cancellation | State exit and actor shutdown cancel owned invokes | Cancellation is a request; external work may continue |
| Termination | `Done()` closes after tracked loop/invokes/completion callbacks finish | Expose evidence that owned work actually finished |
| Bounded wait | `StopCtx()` bounds the caller's wait, including lock acquisition | A timeout is not successful shutdown and does not kill workers |
| Pending events | Shutdown abandons buffered, unprocessed events | Must-run delivery requires a separate persistence/effect contract |

These contracts are supported by implementation and dedicated tests. A wording
limitation matters: gstate says enqueue "never blocks forever," but it supplies
no deadline itself. A background context plus a full mailbox and a stuck
consumer can still wait indefinitely. The bound depends on the supplied deadline
or actual progress/shutdown. [GSTOP] [GSEND] [GSTOPTEST]

Gstate also uses state-entry and invocation generations to reject stale timer,
completion, and mutation callbacks. This is a useful correctness pattern, but
Python's merged reentry work already guards replaced invocation emissions.
Do not present cancellation and stale-child protection as wholly missing.
[GACTOR] [PACTORS] [PCOMPAT]

For agent work there are two distinct identities:

- **Runtime generation:** is this callback still owned by the active invocation?
- **Domain revision:** does this result apply to the current goal and code?

Generation checks cannot establish the second. A provider can return a valid
result for an obsolete commit. The host must carry explicit attempt/revision
identity and the workflow must decide whether the evidence still applies.

Avoid copying gstate's invocation mutation callback into the core by default.
It acquires the actor lock and stabilizes synchronously outside the mailbox;
serialized access is not one FIFO order for every input source. Python's
event-based result delivery is a better fit for traceable recorded workflows.
[GINVOKE]

Do not create a new async actor runtime merely to imitate Go goroutines.
Python's async interpreter and machine-backed actor currently have distinct
capabilities. First document the workload's required ownership boundary; add a
termination-wait or bounded-host-queue API only for a demonstrated need.
[PRUNTIMES] [PACTORS]

## 6. Observation should explain decisions and effects separately

Gstate has nine narrow observer interfaces covering event receipt, guard
evaluation, dropped events, exits, actions, entries, transitions, invoke start,
and invoke completion. Payload construction is conditional on subscriptions.
Data-bearing payloads capture event-time data and share one cached copy among
subscribers, with a read-only ownership contract. Metadata-only hooks avoid the
data clone. [GOBS] [GACTOR]

Python traces already expose unhandled events through empty transition
selections. Gstate adds function-guard results and invocation lifecycle/error
observations. It does not identify every blocking predicate or provide a
general external-effect failure record after state commitment. Those broader
outcomes belong to the proposed Python observation contract below. [PRUNTIMES]
[GOBS]

Python already has `MacrostepTrace`, `MicrostepTrace`, and selected transition
summaries. Preserve their computation semantics. A selected action in a trace
must not be relabeled as a successfully executed external effect. [PTRACE]
[PHANDLERS]

**Proposal:** where the workflow experiment requires it, add opt-in runtime
records that distinguish selection, state commitment, effect start, effect
outcome, invocation outcome, and rejected stale results. Correlate records with
actor ID, macrostep sequence, cause/event ID, invocation generation, and the
host's attempt/revision identity. Do not expose all fields as permanent public
API until the consumer and serialization needs are known.

Important implementation constraints:

1. Build expensive context payloads only for subscribed kinds.
2. Retained records must preserve causal values, including across awaits.
3. Define observer ordering and exception policy.
4. Keep observation from scheduling effects during pure transition evaluation.
5. Export or persist records outside the runtime lock.
6. Bound buffers and state how dropped telemetry is reported.

Gstate is a caution here too. Most observers run under the actor's write lock,
while invoke-completion observers run concurrently. Calling actor methods or
blocking sends from lock-held callbacks can deadlock. Shared payloads are not
deeply immutable. Convenience `ObserverFuncs` implements every observer kind,
so nil callback fields do not mean zero subscription/copy cost. [GOBS]

Even guard observation is narrower than all candidate decisions: `GuardIn`
membership checks can return before the function-guard observer runs. An
explanation API must specify whether it covers those structural conditions too.
[GSELECT]

For our use case, traces should support an evidence explanation: a transition
was permitted because current tests and review covered a particular revision.
Logging more tokens is not that explanation.

## 7. Restore needs explicit modes and a wider checkpoint boundary

### What gstate snapshots contain

Its snapshot stores active state IDs, history, cloned data, and a stable actor
ID. Hydration repairs configuration, restores missing ancestors/parallel
regions, skips entry actions on restored states, and normally restarts services.
Unknown active IDs are ignored; conflicting choices are normalized; an empty
configuration falls back to initial. Queued events, elapsed timer time, and
external invocation progress are absent. [GHYDRATE] [GTYPES]

That is useful logical state restoration. It is not durable execution. Silent
repair is also a policy decision: an unknown state caused by a bad migration
should probably be rejected with a structured diagnostic in an evidence-driven
workflow, rather than normalized into a plausible new configuration.

### Observed counterexample: suppressing restored services is not inspection

`WithHydrateServices(false)` suppresses services attached to initially restored
states. Hydration still stabilizes eventless transitions; newly entered states
run their entry actions and start their services. An isolated Go probe restored
a state with data count 7, whose eventless transition entered a new state that
increments the count and starts an invocation. The result was:

```text
state=fresh count=8 restoredInvokes=0 newInvokeSnapshot=8
```

The old state's entry and invocation were skipped, but new work started.
This matches the implementation; it is not a claim of a bug against the narrow
documented option. [GHYDRATE] [GINVOKE]

For Python, define these operations separately before adding API names:

| Operation | Desired contract to decide and test |
| --- | --- |
| Decode and validate | Reconstruct a compatible logical snapshot without running chart callbacks or launching work |
| Inspect | Query/visualize the stored state and metadata without effectful stabilization |
| Resume | Explicitly choose timer and invocation policy, then run the live actor |

Python already has a useful standalone deserializer. The immediate gap is
that constructing a machine-backed actor first initializes its interpreter,
then applies the supplied snapshot. An initially final chart can therefore
call an output function during actor construction. The persistence guide now
documents this precisely. Removing unnecessary initialization is a bounded
follow-up to #64; it is not evidence that #64's output restoration failed.
[PERSIST] [PINIT]

### Atomic state plus metadata

Gstate's `SnapshotWith(fn)` captures the snapshot and invokes a fast metadata
capture function under the same actor read lock. Synchronous state/action
observers cannot interleave, but invoke-completion observers can. The function
must not perform I/O or reenter actor methods. This aligns part of the host's
metadata with logical state; it does not create a storage transaction.
[GSNAPSHOT]

For our proposed host, a checkpoint envelope should eventually bind:

- format version, machine/config identity, and implementation version;
- logical run ID and distinct attempt/generation identity;
- goal revision and code/workspace revision;
- committed event sequence and logical snapshot;
- prompt, skill and harness versions relevant to the evidence;
- document/evidence references and remaining budgets;
- pending external-effect intents and the receipts known at capture time.

This is an architectural sketch, not a new Measured Skills knowledge schema.
Use existing authoritative contracts where they exist; do not invent field
names that claim to be compatible with an unavailable schema.

A host still needs to decide how snapshot, event position, effect intents and
receipts are committed. A lock-consistent read followed by a file write is not
atomic with GitHub, a subprocess, or a model provider. Recovery must reconcile
an effect whose external write succeeded before its receipt was persisted.
Use idempotency and reconciliation appropriate to that external system; do
not claim exactly-once effects from snapshot serialization.

## 8. Error routes and completion carry product lessons

Gstate distinguishes a false predicate from an error in predicate evaluation.
`GuardErr()` requires a declared error route at build time. On failure it uses
that route instead of the transition's assignment; selection stops and
previously selected parallel candidates are discarded. The behavior is
explicitly tested. [GGUARD]

The useful Python principle is to distinguish **policy denied**, **verification
failed**, and **verification could not run**. A missing executable is not a
negative architecture review. However, importing gstate's full error-routing
semantics would alter transition selection and parallel behavior. Keep network
checks and model calls in effects/invocations; convert their outcomes into
explicit events, then let pure guards evaluate recorded facts. Propose a core
guard-error policy only if local fallible predicates justify it.

Gstate's local `OnDone()` and `GuardIn()` also reinforce that completion does
not imply success. A nested workflow can finish in different final states and
the parent can route accordingly. Python already has completion and state
membership guards, so this is chiefly an example/design lesson. [GCOMPLETE]
[PGUARDS] [PCOMPAT]

The gstate agent example has investigate, approve, fix, verify and retry phases,
but diagnostics are simulated and the controller supplies success/approval
events. Decline, invocation failure, exhausted retries and success ultimately
reach the same final `done`. It demonstrates control flow, not real model
integration, durable recovery, or evidence-based delivery. [GAGENT]

Our example should represent successful delivery, rejection, cancellation,
exhaustion and failure distinctly, with a typed outcome or explicit final
states. A model finishing a prompt should produce an observation; verified
acceptance and delivery authorization require their own evidence.

## 9. Testing and diagrams: adopt the verification method

Gstate exercises race detection, leaked-goroutine checks, bounded fuzzing and
saved regression seeds. Its fuzz targets cover snapshot hydration, builder
inputs, and event sequences. Its Mermaid checks include a pinned real parser
and renderer, plus checked-in diagrams for human review. Example diagrams can
be regenerated from compiled declarations and checked for drift. [GFUZZ]
[GCI] [GMERMAIDTEST]

Python already has complementary strengths: deterministic clocks, a configured
SCXML corpus, an actual pinned JavaScript runtime comparison, trace replay and
consumer-shaped controller examples. Keep those. Add properties around real
boundaries rather than translating Go test counts. [PCOMPAT] [PCONTROLLERS]

Good initial properties and scenarios:

- duplicate IDs never silently change lookup ownership;
- legal active configurations retain ancestor closure and valid parallel regions;
- stale invocation completions cannot advance a new attempt;
- decode/inspection never starts invokes or timers;
- explicit resume obeys documented restart/deadline policy;
- completed stored output survives serialization without recomputation;
- selected action traces and actual effect outcomes remain distinguishable;
- changed goal/code revisions invalidate prior evidence appropriately;
- composition conflicts fail independently of the order of conflicting extensions;
- retained observations keep their causal context and event values.

Use precise language for termination safeguards. Gstate's stabilization budget
is `max(100, 2 * number_of_states)`, shared by eventless and completion
transitions. A finite one-state reducer requiring 101 iterations stopped at 100
with `ErrAlwaysLimit` in a local probe. This is a resource bound, not cycle
detection or proof of nontermination. Python already has a configurable
microstep budget; keep that distinction clear in both documentation and tests.
[GCOMPLETE] [PRUNTIMES]

Use bounded property/stateful tests with saved failing examples as development
dependencies, and meaningful invariants alongside differential tests. A
reference implementation agreeing is not proof when both interpretations are
outside their advertised scope.

For diagrams, Python already exports Mermaid. Test hostile identifiers and
labels with a pinned real renderer in development CI, assert nonempty fixture
coverage, and expose semantically important edges such as reentry and error
routes. No Node dependency belongs in the installed Python runtime.

Gstate's exporters also have limits: an internal targetless action and an
explicit self-target can render as the same self-edge, despite different
reentry behavior. SCXML output uses descriptive placeholders for Go callbacks;
it is not an executable round trip. Parser acceptance and visual readability
do not establish semantic equivalence. [GMERMAID] [GSCXML]

## 10. A focused product experiment

Proposed niche: **Python statecharts for coordinating agent-assisted software
changes with revision-bound evidence and explicit handoff.** This is a product
hypothesis, not established demand or an exclusive market claim.

Keep the existing Measured Skills comparison and acceptance/review contracts as
the evidence gate described in PR #63. First ask whether real users lose goal,
revision, review coverage, budget or verification state across resumptions.
Statecharts earn their complexity when those interactions and invalidations
matter. A straightforward linear script may be enough for a single pass.

If that need is observed, build one recorded-event contribution workflow:

1. Accept a goal revision and concrete acceptance requirements.
2. Request a plan or change from an existing provider harness.
3. Persist result references and the exact code revision assessed.
4. Run verification and bounded review, keeping their findings distinct.
5. Revise within explicit remaining budgets when evidence fails.
6. Request delivery authorization bound to the current revision and action.
7. Deliver only when the prerequisites still hold; persist the resulting receipt.

The first example should consume recorded events and a fake effect adapter.
It should not perform live model calls or publish a PR. This establishes
deterministic coordination behavior before evaluating provider quality, cost,
or a production recovery host.

| Layer | Responsibility | Suggested starting point |
| --- | --- | --- |
| Statechart core | States, transitions, guards, assignment, causal action capture | Existing `Machine`, adapters and runtime |
| Example coordinator | Revision identity, evidence validity, budget and phase decisions | Small typed dataclass context and typed event mappings |
| Host | Workspace, document store, command execution, provider calls, delivery, receipts | Fake/recorded adapter first; one real adapter only for a demonstrated bottleneck |
| Skills | Versioned instructions and evaluation/review procedures | Existing measured library and authoritative contracts |
| Project records | Goal, acceptance evidence, architectural decisions, review findings | Versioned artifacts referenced by the coordinator |

Do not encode every task or document paragraph as a state. Use states for
meaningful execution phases; use a ledger for individual requirements and
evidence. Preserve the distinction between review coverage, findings,
verification and completion. Skills are instructions used by a worker, not
automatically executable statechart plugins or authority to perform an action.

Minimum acceptance cases for the experiment:

| Case | Expected outcome |
| --- | --- |
| Provider reports success without evidence | Acceptance remains unverified |
| Tests passed for an older commit | New commit cannot advance using those results |
| Goal changes while review is running | Old review result is recorded but cannot satisfy the new goal |
| Attempt 1 completes after attempt 2 starts | Attempt 2's state is not advanced by the old result |
| Verification executable is unavailable | Report blocked/error, not a failed requirement or a pass |
| Review budget is exhausted | Preserve unresolved scope and remaining findings |
| Previously closed finding is reopened | Completion/authorization is reevaluated |
| Approval names a different revision or action | Delivery stays gated |
| Checkpoint is inspected | No commands, invokes or timers are launched |
| Resume occurs after an uncertain external write | Reconcile receipts; do not blindly repeat the write |

The last case is a host/recovery acceptance requirement, not a capability the
initial recorded-event example can prove about a real external service.

## 11. Proposed PR sequence

The dated implementation update above records draft PRs for A–C. D–G remain
proposed work, not a commitment to implement the whole table. Keep compatibility
fixtures and pure/runtime boundaries visible in each.

| Order | Proposed PR | Concrete acceptance boundary | Dependency or stop condition |
| --- | --- | --- | --- |
| A | Normalize observable factory input ([draft #66](https://github.com/JovaniPink/xstate-python/pull/66)) | Positional unary, keyword `input`, positional-only, supported legacy signatures and real binding errors are covered | Reproduced at the audited baseline; closes #53 when merged |
| B | Reject duplicate resolved state IDs ([draft #67](https://github.com/JovaniPink/xstate-python/pull/67)) | Both conflicting paths reported; valid nested local names and existing target/history behavior preserved; strict `systemId` classified unsupported | Concrete addressing gap; no DSL or alias implementation |
| C | Avoid initial computation when constructing from a supplied snapshot ([draft #68](https://github.com/JovaniPink/xstate-python/pull/68)) | No unnecessary initial assignment/guard/output evaluation; stored output, lifecycle and trace semantics preserved | Constructor-supplied snapshot only; follow-up to still-open #54, not a repeat of #64 |
| D | Run coordination/adoption evaluation | Record whether revision, evidence, review or budget loss occurs and whether explicit state helps | Preserve PR #63's evaluation gate; stop expansion if a simpler approach suffices |
| E | Add one typed recorded-event workflow | Cases above for stale results, evidence, outcomes and budgets pass; no real publishing/model dependency | Only if D justifies the coordinator |
| F | Add the missing runtime observations/checkpoint contract | Correlation and effect outcomes meet the example's actual needs; disabled observations avoid extra payload work | Extract from E; no generic observability platform |
| G | Extract checked composition/authoring helpers | Two consumers need the same operation; conflicts are diagnosed; existing JSON engine remains authoritative | Defer until repeated consumer evidence |

Property tests and real Mermaid rendering are independent improvements that can
run alongside this sequence. A termination-wait API or durable host should be a
separate proposal tied to an actual ownership/recovery need. Broad async actor
parity, automatic package renaming, a skill execution engine and multi-provider
orchestration are not prerequisites for the first useful workflow.

## 12. Verification performed for this research

| Check | Result and limit |
| --- | --- |
| Exact source baseline | Fresh checkouts at the two pinned commits above |
| Gstate tests | `go test -count=1 ./...` passed locally with Go 1.26.6 on Linux/amd64 |
| Gstate race detector | `go test -race -count=1 ./...` passed locally; covers executed tests, not a proof of all schedules |
| Gstate hosted checks | [Go CI run 44633330451](https://github.com/floodfx/gstate/actions/runs/44633330451) succeeded at the pinned commit; its logs include the bounded fuzz targets |
| Hydration probe | Confirmed suppressed restored services can be followed by new entry actions and a new invocation during eventless stabilization |
| Parallel-phase probe | Observed `a:exit, a:assign, a:entry, b:exit, b:assign, b:entry` for two selected Go transitions, confirming the source-level ordering difference |
| Guard-purity probe | A deliberately reference-mutating false guard retained the map mutation despite a correct `Clone()`; ownership requires pure guards |
| Stabilization-budget probe | A finite 101-step targetless Go computation stopped at 100 with `ErrAlwaysLimit` |
| Python focused tests | 46 existing snapshot, context and raw-config validation cases passed with Python 3.13.5 and pytest/plugin versions from `poetry.lock` |
| Python observable input probe | Equivalent unary factories named `input` and `count` behave differently; #53 remains reproducible |
| Python duplicate-ID probe | Strict configuration accepted the duplicate; registry selected the later declaration |
| Current completed output | Source and focused tests include merged #64; not reported as missing |

An initial Python test attempt with newly resolved pytest/plugin versions stopped
at configuration because of a new fixture-loop-scope warning. Repeating with
the repository's locked versions passed; no warning policy, test gate or source
configuration was weakened. The full Python, SCXML and JavaScript comparison
suites were not rerun for this documentation-only research change. No fresh
performance comparison, live-model evaluation, or durable recovery study was
performed.

## Pinned source index

### Gstate

[GTYPES]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/types.go
[GACTOR]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/actor.go#L38-L190
[GBUILDER]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/builder.go
[GCOMPOSITION]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/composition_builder_test.go
[GSELECT]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/actor.go#L1018-L1354
[GCOMPLETE]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/completion.go
[GOBS]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/observer.go
[GSEND]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/actor.go#L923-L1060
[GSTOP]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/actor.go#L568-L663
[GSTOPTEST]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/stopctx_test.go
[GINVOKE]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/actor.go#L688-L792
[GHYDRATE]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/actor.go#L148-L361
[GSNAPSHOT]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/actor.go#L795-L825
[GGUARD]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/guard_err_test.go#L204-L268
[GAGENT]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/examples/agent/main.go
[GFUZZ]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/fuzz_test.go
[GCI]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/justfile
[GMERMAIDTEST]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/mermaid_truth_test.go
[GMERMAID]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/mermaid.go
[GSCXML]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/scxml.go
[GBENCHDOC]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/BENCHMARKS.md
[GBENCH]: https://github.com/floodfx/gstate/blob/fbbb3d8155da691c4aeba8ee01ed58b69cc37b2c/bench_test.go

- [Types and ownership][GTYPES]; [actor construction][GACTOR];
  [builder validation/composition][GBUILDER]; [composition tests][GCOMPOSITION].
- [External selection and transition execution][GSELECT];
  [completion and eventless stabilization][GCOMPLETE];
  [guard-error regression][GGUARD].
- [Observer contracts][GOBS]; [send contracts][GSEND];
  [shutdown][GSTOP]; [bounded-shutdown tests][GSTOPTEST];
  [invocation lifecycle][GINVOKE].
- [Hydration][GHYDRATE]; [snapshot metadata capture][GSNAPSHOT].
- [Agent example][GAGENT]; [fuzz targets][GFUZZ]; [CI recipes][GCI];
  [real renderer tests][GMERMAIDTEST]; [Mermaid][GMERMAID]; [SCXML][GSCXML].
- [Published benchmark baseline][GBENCHDOC]; [current benchmark source][GBENCH].

### Xstate-python

[P64]: https://github.com/JovaniPink/xstate-python/pull/64
[PERSIST]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/docs/concepts/persistence.md
[PTYPING]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/docs/concepts/typing.md
[PCONTEXT]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/context.py
[PTRACE]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/trace.py
[PRUNTIMES]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/docs/concepts/runtimes.md
[PMERMAID]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/mermaid.py
[PSTEP]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/algorithm.py#L1212-L1265
[PCOMPAT]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/docs/concepts/xstate-compatibility.md
[PVALIDATE]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/config_validation.py
[PREGISTER]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/machine.py#L325-L330
[POBSERVABLE]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/actor.py#L552-L575
[PPROMISE]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/actor.py#L277-L313
[PHANDLERS]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/docs/concepts/machines-and-implementations.md#L148-L186
[PINVOKEPARSER]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/config_parser.py#L208-L236
[PBENCH]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/scripts/benchmark_runtime.py
[PACTORS]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/docs/concepts/actors.md
[PINIT]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/interpreter.py#L122-L200
[PGUARDS]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/src/xstate/guards.py
[PCONTROLLERS]: https://github.com/JovaniPink/xstate-python/blob/fdc5df06ce87622fbc91aa88a5d8ab09de62041d/docs/concepts/controllers.md

- [Merged output repair][P64]; [persistence contract][PERSIST];
  [construction/start boundary][PINIT].
- [Typing][PTYPING]; [context adapters][PCONTEXT]; [runtime choices][PRUNTIMES];
  [actor model][PACTORS]; [handler migration][PHANDLERS].
- [Pure microstep ordering][PSTEP]; [compatibility contract][PCOMPAT];
  [traces][PTRACE]; [guards][PGUARDS].
- [Raw-key diagnostics][PVALIDATE]; [ID registration][PREGISTER];
  [invoke normalization][PINVOKEPARSER]; [observable call binding][POBSERVABLE];
  [promise call binding][PPROMISE].
- [Mermaid exporter][PMERMAID]; [runtime benchmark][PBENCH];
  [controller/replay example][PCONTROLLERS].
