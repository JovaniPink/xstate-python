"""Extended history-state tests ported from XState v4 test corpus (PR #49).

Covers behaviors beyond the basic shallow/deep tests already in test_history.py:
  - Two history pseudo-states (shallow + deep) on the same compound parent
  - History in parallel regions (per-region shallow and deep history)
  - Multi-target transitions that restore multiple regions simultaneously
"""

import pytest
from xstate import Machine

# ---------------------------------------------------------------------------
# Machine: compound state with both shallow and deep history pseudo-states
# ---------------------------------------------------------------------------
#
# off --POWER--> on.shallow_hist  (shallow: restores on's immediate child)
#     --DEEP_POWER--> on.deep_hist (deep:    restores full atomic path inside on)
# on has first -> second -> A -> B -> P -> Q chain


def make_dual_history():
    return Machine(
        {
            "id": "dual_hist",
            "initial": "off",
            "states": {
                "off": {
                    "on": {
                        "POWER": "#dual_shallow",
                        "DEEP_POWER": "#dual_deep",
                    }
                },
                "on": {
                    "initial": "first",
                    "states": {
                        "first": {"on": {"SWITCH": "second"}},
                        "second": {
                            "initial": "A",
                            "states": {
                                "A": {"on": {"INNER": "B"}},
                                "B": {
                                    "initial": "P",
                                    "states": {
                                        "P": {"on": {"INNER": "Q"}},
                                        "Q": {},
                                    },
                                },
                            },
                        },
                        "shallow_hist": {
                            "type": "history",
                            "history": "shallow",
                            "id": "dual_shallow",
                        },
                        "deep_hist": {
                            "type": "history",
                            "history": "deep",
                            "id": "dual_deep",
                        },
                    },
                    "on": {"POWER": "off"},
                },
            },
        }
    )


def test_dual_hist_no_history_uses_initial():
    machine = make_dual_history()
    state = machine.initial_state
    state = machine.transition(state, "POWER")
    assert state.value == {"on": "first"}


def test_dual_hist_shallow_restores_immediate_child():
    """Shallow history records on's immediate active child (second), not B.P."""
    machine = make_dual_history()
    state = machine.initial_state
    state = machine.transition(state, "POWER")  # on.first
    state = machine.transition(state, "SWITCH")  # on.second.A
    state = machine.transition(state, "INNER")  # on.second.B.P
    assert state.value == {"on": {"second": {"B": "P"}}}
    state = machine.transition(state, "POWER")  # off (records shallow hist: second)
    assert state.value == "off"
    # POWER uses shallow history → restores second at its initial child (A)
    state = machine.transition(state, "POWER")
    assert state.value == {"on": {"second": "A"}}


def test_dual_hist_deep_restores_full_path():
    """Deep history records the full atomic descendant path (second.B.P)."""
    machine = make_dual_history()
    state = machine.initial_state
    state = machine.transition(state, "POWER")  # on.first
    state = machine.transition(state, "SWITCH")  # on.second.A
    state = machine.transition(state, "INNER")  # on.second.B.P
    state = machine.transition(state, "POWER")  # off (records deep hist: second.B.P)
    state = machine.transition(state, "DEEP_POWER")  # restore deep → second.B.P
    assert state.value == {"on": {"second": {"B": "P"}}}


def test_dual_hist_deep_tracks_updates():
    """Deep history tracks the most recent exit, not the first."""
    machine = make_dual_history()
    state = machine.initial_state
    state = machine.transition(state, "POWER")  # on.first
    state = machine.transition(state, "SWITCH")  # on.second.A
    state = machine.transition(state, "INNER")  # on.second.B.P
    state = machine.transition(state, "INNER")  # on.second.B.Q
    assert state.value == {"on": {"second": {"B": "Q"}}}
    state = machine.transition(state, "POWER")  # off (records deep hist: second.B.Q)
    state = machine.transition(state, "DEEP_POWER")
    assert state.value == {"on": {"second": {"B": "Q"}}}


# ---------------------------------------------------------------------------
# Machine: parallel state with per-region history pseudo-states
# ---------------------------------------------------------------------------
#
# Adapted from XState's history.test.ts "parallel history states" describe block.
#
# off can re-enter `on` in several ways:
#   SWITCH         → on (enters all regions at initial)
#   POWER          → on.hist (shallow history of the parallel root)
#   DEEP_POWER     → on.deep_hist (deep history of the parallel root)
#   PARALLEL_HIST  → [A.hist, K.hist] (per-region shallow history)
#   PARALLEL_DEEP  → [A.deep, K.deep] (per-region deep history)
#
# Region A: B -> C(initial=D -> E)
# Region K: L -> M(initial=N -> O)


def make_parallel_history():
    return Machine(
        {
            "id": "parhist",
            "initial": "off",
            "states": {
                "off": {
                    "on": {
                        "SWITCH": "on",
                        "POWER": "#ph_on_shallow",
                        "DEEP_POWER": "#ph_on_deep",
                        "PARALLEL_HIST": [
                            {"target": ["#ph_A_shallow", "#ph_K_shallow"]}
                        ],
                        "PARALLEL_DEEP": [{"target": ["#ph_A_deep", "#ph_K_deep"]}],
                    }
                },
                "on": {
                    "type": "parallel",
                    "states": {
                        "A": {
                            "initial": "B",
                            "states": {
                                "B": {"on": {"INNER_A": "C"}},
                                "C": {
                                    "initial": "D",
                                    "states": {
                                        "D": {"on": {"INNER_A": "E"}},
                                        "E": {},
                                    },
                                },
                                "hist": {
                                    "type": "history",
                                    "history": "shallow",
                                    "id": "ph_A_shallow",
                                },
                                "deep_hist": {
                                    "type": "history",
                                    "history": "deep",
                                    "id": "ph_A_deep",
                                },
                            },
                        },
                        "K": {
                            "initial": "L",
                            "states": {
                                "L": {"on": {"INNER_K": "M"}},
                                "M": {
                                    "initial": "N",
                                    "states": {
                                        "N": {"on": {"INNER_K": "O"}},
                                        "O": {},
                                    },
                                },
                                "hist": {
                                    "type": "history",
                                    "history": "shallow",
                                    "id": "ph_K_shallow",
                                },
                                "deep_hist": {
                                    "type": "history",
                                    "history": "deep",
                                    "id": "ph_K_deep",
                                },
                            },
                        },
                        "hist": {
                            "type": "history",
                            "history": "shallow",
                            "id": "ph_on_shallow",
                        },
                        "deep_hist": {
                            "type": "history",
                            "history": "deep",
                            "id": "ph_on_deep",
                        },
                    },
                    "on": {"POWER": "off"},
                },
            },
        }
    )


def _reach_ACEKMN(machine):
    """Return state with A=C.E, K=M.N."""
    s = machine.initial_state
    s = machine.transition(s, "SWITCH")  # on: A=B, K=L
    s = machine.transition(s, "INNER_A")  # A=C.D, K=L
    s = machine.transition(s, "INNER_A")  # A=C.E, K=L
    s = machine.transition(s, "INNER_K")  # A=C.E, K=M.N
    return s


def _reach_ACEKMO(machine):
    """Return state with A=C.E, K=M.O."""
    s = _reach_ACEKMN(machine)
    s = machine.transition(s, "INNER_K")  # A=C.E, K=M.O
    return s


def test_parallel_switch_enters_initials():
    machine = make_parallel_history()
    state = machine.initial_state
    state = machine.transition(state, "SWITCH")
    assert state.value == {"on": {"A": "B", "K": "L"}}


def test_parallel_shallow_history_of_root_ignores_region_substates():
    """Shallow history of the parallel root records only its immediate children
    (the regions A and K themselves), so re-entry resets each region to initial."""
    machine = make_parallel_history()
    s = machine.initial_state
    s = machine.transition(s, "SWITCH")  # A=B, K=L
    s = machine.transition(s, "INNER_A")  # A=C.D
    assert s.value == {"on": {"A": {"C": "D"}, "K": "L"}}
    s = machine.transition(s, "POWER")  # off; shallow hist of on records {A, K}
    s = machine.transition(s, "POWER")  # restore via shallow: enters A→B, K→L
    assert s.value == {"on": {"A": "B", "K": "L"}}


def test_parallel_deep_history_of_root_restores_full_path():
    """Deep history of the parallel root records the full atomic configuration."""
    machine = make_parallel_history()
    s = machine.initial_state
    s = machine.transition(s, "SWITCH")  # A=B, K=L
    s = machine.transition(s, "INNER_A")  # A=C.D, K=L
    assert s.value == {"on": {"A": {"C": "D"}, "K": "L"}}
    s = machine.transition(s, "POWER")  # off; deep hist records {C.D, L}
    s = machine.transition(s, "DEEP_POWER")  # restore: A→C.D, K→L
    assert s.value == {"on": {"A": {"C": "D"}, "K": "L"}}


def test_parallel_deep_history_restores_both_regions():
    """Deep history of root restores full path in both regions."""
    machine = make_parallel_history()
    s = _reach_ACEKMO(machine)
    assert s.value == {"on": {"A": {"C": "E"}, "K": {"M": "O"}}}
    s = machine.transition(s, "POWER")  # off
    s = machine.transition(s, "DEEP_POWER")  # restore A=C.E, K=M.O
    assert s.value == {"on": {"A": {"C": "E"}, "K": {"M": "O"}}}


def test_parallel_per_region_shallow_history():
    """PARALLEL_HIST targets A.hist and K.hist simultaneously.

    Shallow history of A records its immediate active child (C when A=C.E),
    so re-entry enters C then C.initial=D. Same for K (M→N).
    """
    machine = make_parallel_history()
    s = _reach_ACEKMO(machine)  # A=C.E, K=M.O
    s = machine.transition(s, "POWER")  # off; A_shallow={C}, K_shallow={M}
    s = machine.transition(s, "PARALLEL_HIST")  # enter A via A.hist, K via K.hist
    assert s.value == {"on": {"A": {"C": "D"}, "K": {"M": "N"}}}


def test_parallel_per_region_deep_history():
    """PARALLEL_DEEP targets A.deep_hist and K.deep_hist simultaneously.

    Deep history restores the exact atomic state in each region.
    """
    machine = make_parallel_history()
    s = _reach_ACEKMO(machine)  # A=C.E, K=M.O
    s = machine.transition(s, "POWER")  # off; A_deep={E}, K_deep={O}
    s = machine.transition(s, "PARALLEL_DEEP")
    assert s.value == {"on": {"A": {"C": "E"}, "K": {"M": "O"}}}


def test_parallel_history_no_recorded_uses_region_initial():
    """When no history has been recorded for a region, re-entry uses that
    region's initial state."""
    machine = make_parallel_history()
    state = machine.initial_state  # off, no history recorded
    state = machine.transition(state, "PARALLEL_HIST")
    assert state.value == {"on": {"A": "B", "K": "L"}}
