# SCXML Import

`xstate-python` can convert an SCXML document into the same `Machine` used by
the pure transition API, interpreters, and actors. The importer is deliberately
focused: it supports the project test subset without evaluating arbitrary
JavaScript or claiming complete W3C conformance.

## Load From A Path

Pass a filesystem path or `PathLike` object to `scxml_to_machine(...)`:

```python
from pathlib import Path

from xstate.scxml import scxml_to_machine

source = Path("workflow.scxml")
machine = scxml_to_machine(source)

state = machine.initial_state
state = machine.transition(state, "NEXT")
```

The importer parses the document immediately. Keep the XML file available only
for machine construction; the resulting machine does not read it again while
processing events.

## Converted Structure

The current converter handles this focused XML surface:

| SCXML | Machine configuration |
|---|---|
| `<scxml initial="...">` | Root machine and initial state |
| `<state id="...">` | Compound or atomic state |
| `<parallel id="...">` | Parallel state with all child regions entered |
| `<transition event="..." target="...">` | Event transition to one or more state IDs |
| `cond="..."` | Guard compiled from the safe Boolean subset |
| `<onentry><raise .../></onentry>` | Entry raise actions |
| `<onexit><raise .../></onexit>` | Exit raise actions |
| `<transition><raise .../></transition>` | Transition raise actions |

Transition target IDs are resolved as machine IDs. Multiple space-separated
targets are preserved, and source/document order is preserved for transition
selection and conflict resolution.

Other SCXML datamodels, executable-content elements, and JavaScript semantics are
outside this import surface. Structural `<final>`, `<history>`, and explicit
`<initial>` elements are also not converted yet, even though the native machine
configuration supports equivalent statechart concepts. Do not depend on
`<script>`, `<assign>`, `<send>`, or general ECMAScript evaluation during import.

Malformed XML, an empty document, missing state IDs or raise events, and
duplicate state IDs raise `InvalidConfigError` during import. State IDs are
validated across the complete document because SCXML transition targets are
document-global.

## Transition Execution

The imported machine uses the regular run-to-completion algorithm. Exit
actions run before transition actions, entry actions run after them, and raised
events are consumed internally before the macrostep completes. This behavior is
the same whether the machine is driven through `Machine.transition(...)`,
`interpret(...)`, or `create_actor(...)`.

For `<parallel>`, entering the parallel state enters every child region. An
external transition uses the nearest compound ancestor as its transition
domain, so affected branches exit and re-enter correctly. Competing transitions
are resolved by their exit sets and document order.

## Safe Conditions

SCXML conditions support only Boolean literals and operators:

```text
true
false
!true
true && false
true || (false && !false)
```

In XML, escape `&&` as `&amp;&amp;` inside an attribute:

```xml
<transition event="GO" cond="true &amp;&amp; !false" target="ready"/>
```

The expression is parsed once when the machine is imported. It cannot read the
event, context, or an SCXML datamodel.

Unsupported identifiers, property access, comparisons, and JavaScript raise
`InvalidConfigError` instead of being evaluated:

```xml
<transition event="GO" cond="event.name === 'GO'" target="ready"/>
```

```python
from xstate.exceptions import InvalidConfigError
from xstate.scxml import scxml_to_machine

try:
    scxml_to_machine("unsupported.scxml")
except InvalidConfigError as exc:
    print(exc)
```

An expression such as `count > 0` is rejected in the same way; defining
`count` in an SCXML `<datamodel>` does not expand the supported subset.

## Conformance Boundary

The configured repository suite currently reports `54 passed`, `0 failed`,
including all 13 enabled `more-parallel` cases. This is a focused subset, not a
claim of complete W3C SCXML conformance. The broader datamodel and executable
content surface remains future work, and the `more-parallel` `test10` and
`test10b` fixtures remain outside the configured set because they require
additional assignment support.

Run the self-contained [SCXML toggle example](../examples/scxml_toggle.py), or
run the configured conformance suite after initializing its submodule:

```bash
PYTHONPATH=src python3 docs/examples/scxml_toggle.py
git submodule update --init
poetry run python -m pytest tests/test_scxml.py
```
