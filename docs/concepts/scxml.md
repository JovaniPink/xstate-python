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
| `<datamodel><data id="x" expr="0"/></datamodel>` | Top-level context with non-negative integer literal values |
| `cond="..."` | Guard compiled from the safe Boolean and integer-equality subset |
| `<assign location="x" expr="x + 1"/>` | Increment a declared integer datum by exactly one |
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
`<script>`, `<send>`, other assignment forms, or general ECMAScript evaluation
during import.

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
atomic self-transition exits and re-enters only that branch, without cycling the
parallel parent or its siblings. Other external transitions use the nearest
compound ancestor as their transition domain, so affected branches exit and
re-enter correctly. Competing transitions are resolved by their exit sets and
document order.

## Safe Expressions

SCXML conditions support Boolean literals and operators:

```text
true
false
!true
true && false
true || (false && !false)
```

When a top-level `ecmascript` datamodel declares an integer literal, conditions
may also use one standalone comparison between that simple identifier and a
non-negative integer with `===`:

```xml
<datamodel>
  <data id="x" expr="0"/>
</datamodel>
<transition event="GO" cond="x === 2" target="ready"/>
```

The only supported `<assign>` expression increments its own declared integer
location by exactly one. Whitespace around `+` is optional:

```xml
<assign location="x" expr="x + 1"/>
```

In XML, escape `&&` as `&amp;&amp;` inside an attribute:

```xml
<transition event="GO" cond="true &amp;&amp; !false" target="ready"/>
```

Expressions are parsed once when the machine is imported. A data comparison or
assignment can read only its declared integer location; it cannot read events,
properties, call functions, or evaluate JavaScript.

Undeclared identifiers, property access, other arithmetic or comparisons, and
JavaScript raise `InvalidConfigError` instead of being evaluated:

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

Expressions such as `count > 0`, `count + 2`, and `user.count + 1` are rejected
in the same way; declaring data does not expand the supported grammar.

## Conformance Boundary

The configured repository subset contains 56 passing conformance cases, including all 15 enabled
`more-parallel` cases, plus a fixture inventory/provenance guard. This is a focused subset, not a
claim of complete W3C SCXML conformance. The broader datamodel and executable content surface
remains future work.

Run the self-contained [SCXML toggle example](../examples/scxml_toggle.py), or
run the configured conformance suite against the checked-in fixture subset:

```bash
PYTHONPATH=src python3 docs/examples/scxml_toggle.py
poetry run python -m pytest tests/test_scxml.py
```
