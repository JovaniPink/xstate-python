"""Integration tests: User Session Manager state machine.

A real-world style authentication + session management machine inspired by
canonical XState v4 patterns (https://xstatebyexample.com/authentication/).

Features exercised across the full suite:
  - Compound states  (authenticated → active / idle_session / screen_locked)
  - Context + assign (user, error, attempts counter)
  - Guards / conds   (savedToken, canRetry / lockout threshold, pin check)
  - Multi-transition event arrays with priority ordering (FAILURE)
  - Targetless guard blocks (wrong-pin UNLOCK — no transition fired)
  - Logical and physical separation of context update from guard evaluation

Machine topology
----------------

    idle ──LOGIN──► authenticating ──SUCCESS──► authenticated
                          │                         │
                     FAILURE[×3]              active ◄──RESUME── idle_session
                     ┌────┴─────┐                  │               │
               lockedOut   authError            TIMEOUT        LONG_TIMEOUT
                   │            │                  │               │
              ADMIN_UNLOCK    RETRY            idle_session    screen_locked
                   │            │                              │
                  idle    authenticating               UNLOCK(pin) ──► active
                                                       (wrong pin: no-op)

    authenticated also handles:
        LOGOUT          → idle
        SESSION_EXPIRED → idle
"""

from xstate import Machine, assign

MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_session_machine(saved_token: bool = False):
    """Build the session machine.  saved_token controls AUTO_LOGIN eligibility."""
    return Machine(
        {
            "id": "session",
            "initial": "idle",
            "context": {
                "user": None,
                "error": None,
                "attempts": 0,
                "savedToken": saved_token,
            },
            "states": {
                # ---- unauthenticated states --------------------------------
                "idle": {
                    "on": {
                        "LOGIN": "authenticating",
                        "AUTO_LOGIN": {
                            "target": "authenticated",
                            "cond": lambda ctx, _: ctx.get("savedToken", False),
                        },
                    }
                },
                "authenticating": {
                    "on": {
                        "SUCCESS": {
                            "target": "authenticated",
                            "actions": [
                                assign(
                                    {
                                        "user": lambda ctx, ev: ev.data.get("user"),
                                        "error": None,
                                        "attempts": 0,
                                    }
                                )
                            ],
                        },
                        # Array: first matching guard wins.
                        # Guard is evaluated against context BEFORE assigns run.
                        "FAILURE": [
                            {
                                "target": "lockedOut",
                                "cond": lambda ctx, _: (
                                    ctx.get("attempts", 0) + 1 >= MAX_ATTEMPTS
                                ),
                                "actions": [
                                    assign(
                                        {
                                            "attempts": lambda ctx, _: ctx.get(
                                                "attempts", 0
                                            )
                                            + 1,
                                            "error": "Account locked",
                                        }
                                    )
                                ],
                            },
                            {
                                "target": "authError",
                                "actions": [
                                    assign(
                                        {
                                            "attempts": lambda ctx, _: ctx.get(
                                                "attempts", 0
                                            )
                                            + 1,
                                            "error": "Invalid credentials",
                                        }
                                    )
                                ],
                            },
                        ],
                    }
                },
                # ---- authenticated compound state -------------------------
                "authenticated": {
                    "initial": "active",
                    "on": {
                        "LOGOUT": {
                            "target": "idle",
                            "actions": [
                                assign({"user": None, "error": None, "attempts": 0})
                            ],
                        },
                        "SESSION_EXPIRED": "idle",
                    },
                    "states": {
                        "active": {
                            "on": {
                                "GO_IDLE": "idle_session",
                                "TIMEOUT": "idle_session",
                            }
                        },
                        "idle_session": {
                            "on": {
                                "RESUME": "active",
                                "LONG_TIMEOUT": "screen_locked",
                            }
                        },
                        "screen_locked": {
                            "on": {
                                # Correct PIN → active; wrong PIN → no-op (guard fails)
                                "UNLOCK": [
                                    {
                                        "target": "active",
                                        "cond": lambda ctx, ev: ev.data.get("pin")
                                        == "1234",
                                    }
                                ]
                            }
                        },
                    },
                },
                # ---- error / lockout states -------------------------------
                "authError": {
                    "on": {
                        "RETRY": "authenticating",
                        "RESET": {
                            "target": "idle",
                            "actions": [assign({"attempts": 0, "error": None})],
                        },
                    }
                },
                "lockedOut": {
                    "on": {
                        "ADMIN_UNLOCK": {
                            "target": "idle",
                            "actions": [assign({"attempts": 0, "error": None})],
                        }
                    }
                },
            },
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login_succeed(machine, user="alice"):
    """Shortcut: idle → authenticating → authenticated.active."""
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    state = machine.transition(state, {"type": "SUCCESS", "user": user})
    return state


def _fail_once(machine, state):
    """Fire a single FAILURE event and return the new state."""
    return machine.transition(state, "FAILURE")


# ---------------------------------------------------------------------------
# Basic state identity
# ---------------------------------------------------------------------------


def test_initial_state_is_idle():
    machine = make_session_machine()
    assert machine.initial_state.value == "idle"


def test_initial_context():
    machine = make_session_machine()
    ctx = machine.initial_state.context
    assert ctx["user"] is None
    assert ctx["error"] is None
    assert ctx["attempts"] == 0


# ---------------------------------------------------------------------------
# Happy-path login flow
# ---------------------------------------------------------------------------


def test_login_reaches_authenticating():
    machine = make_session_machine()
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    assert state.value == "authenticating"


def test_success_enters_authenticated_active():
    machine = make_session_machine()
    state = _login_succeed(machine)
    assert state.value == {"authenticated": "active"}


def test_success_sets_user_in_context():
    machine = make_session_machine()
    state = _login_succeed(machine, user="alice")
    assert state.context["user"] == "alice"


def test_success_clears_error_and_attempts():
    """After a successful login, error and attempts are reset even if there
    had been prior failures."""
    machine = make_session_machine()
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    state = _fail_once(machine, state)  # attempts → 1, state → authError
    state = machine.transition(state, "RETRY")  # back to authenticating
    state = machine.transition(state, {"type": "SUCCESS", "user": "bob"})
    assert state.context["attempts"] == 0
    assert state.context["error"] is None
    assert state.context["user"] == "bob"


# ---------------------------------------------------------------------------
# Failure / retry flow
# ---------------------------------------------------------------------------


def test_first_failure_goes_to_auth_error():
    machine = make_session_machine()
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    state = _fail_once(machine, state)
    assert state.value == "authError"


def test_failure_increments_attempts():
    machine = make_session_machine()
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    state = _fail_once(machine, state)
    assert state.context["attempts"] == 1
    assert state.context["error"] == "Invalid credentials"


def test_retry_returns_to_authenticating():
    machine = make_session_machine()
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    state = _fail_once(machine, state)
    state = machine.transition(state, "RETRY")
    assert state.value == "authenticating"


def test_reset_from_auth_error_clears_context():
    machine = make_session_machine()
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    state = _fail_once(machine, state)
    assert state.context["attempts"] == 1
    state = machine.transition(state, "RESET")
    assert state.value == "idle"
    assert state.context["attempts"] == 0
    assert state.context["error"] is None


# ---------------------------------------------------------------------------
# Lockout after MAX_ATTEMPTS failures
# ---------------------------------------------------------------------------


def _exhaust_attempts(machine):
    """Drive the machine to lockedOut via MAX_ATTEMPTS failures."""
    state = machine.initial_state
    state = machine.transition(state, "LOGIN")
    for _ in range(MAX_ATTEMPTS - 1):
        state = _fail_once(machine, state)  # → authError
        state = machine.transition(state, "RETRY")  # → authenticating
    state = _fail_once(machine, state)  # final failure → lockedOut
    return state


def test_lockout_after_max_attempts():
    machine = make_session_machine()
    state = _exhaust_attempts(machine)
    assert state.value == "lockedOut"


def test_lockout_sets_error_and_attempts():
    machine = make_session_machine()
    state = _exhaust_attempts(machine)
    assert state.context["attempts"] == MAX_ATTEMPTS
    assert "locked" in state.context["error"].lower()


def test_admin_unlock_resets_to_idle():
    machine = make_session_machine()
    state = _exhaust_attempts(machine)
    state = machine.transition(state, "ADMIN_UNLOCK")
    assert state.value == "idle"
    assert state.context["attempts"] == 0
    assert state.context["error"] is None


# ---------------------------------------------------------------------------
# AUTO_LOGIN guard
# ---------------------------------------------------------------------------


def test_auto_login_blocked_without_saved_token():
    """AUTO_LOGIN is a no-op when savedToken is False."""
    machine = make_session_machine(saved_token=False)
    state = machine.initial_state
    state = machine.transition(state, "AUTO_LOGIN")
    assert state.value == "idle"


def test_auto_login_fires_with_saved_token():
    """AUTO_LOGIN skips authenticating when savedToken is True."""
    machine = make_session_machine(saved_token=True)
    state = machine.initial_state
    state = machine.transition(state, "AUTO_LOGIN")
    assert state.value == {"authenticated": "active"}


# ---------------------------------------------------------------------------
# Session lifecycle inside `authenticated`
# ---------------------------------------------------------------------------


def test_logout_from_active_returns_to_idle():
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "LOGOUT")
    assert state.value == "idle"


def test_logout_clears_user():
    machine = make_session_machine()
    state = _login_succeed(machine, user="alice")
    assert state.context["user"] == "alice"
    state = machine.transition(state, "LOGOUT")
    assert state.context["user"] is None


def test_session_expired_returns_to_idle():
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "SESSION_EXPIRED")
    assert state.value == "idle"


def test_timeout_enters_idle_session():
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "TIMEOUT")
    assert state.value == {"authenticated": "idle_session"}


def test_go_idle_enters_idle_session():
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "GO_IDLE")
    assert state.value == {"authenticated": "idle_session"}


def test_resume_from_idle_session():
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "TIMEOUT")
    state = machine.transition(state, "RESUME")
    assert state.value == {"authenticated": "active"}


def test_long_timeout_enters_screen_locked():
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "GO_IDLE")
    state = machine.transition(state, "LONG_TIMEOUT")
    assert state.value == {"authenticated": "screen_locked"}


# ---------------------------------------------------------------------------
# Screen-lock PIN guard
# ---------------------------------------------------------------------------


def test_unlock_correct_pin_returns_to_active():
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "GO_IDLE")
    state = machine.transition(state, "LONG_TIMEOUT")
    assert state.value == {"authenticated": "screen_locked"}
    state = machine.transition(state, {"type": "UNLOCK", "pin": "1234"})
    assert state.value == {"authenticated": "active"}


def test_unlock_wrong_pin_stays_locked():
    """Guard fails on wrong PIN — machine stays in screen_locked."""
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "GO_IDLE")
    state = machine.transition(state, "LONG_TIMEOUT")
    state = machine.transition(state, {"type": "UNLOCK", "pin": "0000"})
    assert state.value == {"authenticated": "screen_locked"}


def test_unlock_wrong_pin_then_correct_pin():
    """Multiple wrong PINs followed by the correct one should succeed."""
    machine = make_session_machine()
    state = _login_succeed(machine)
    state = machine.transition(state, "GO_IDLE")
    state = machine.transition(state, "LONG_TIMEOUT")
    # Two wrong attempts
    state = machine.transition(state, {"type": "UNLOCK", "pin": "9999"})
    state = machine.transition(state, {"type": "UNLOCK", "pin": "1111"})
    assert state.value == {"authenticated": "screen_locked"}
    # Correct PIN
    state = machine.transition(state, {"type": "UNLOCK", "pin": "1234"})
    assert state.value == {"authenticated": "active"}


# ---------------------------------------------------------------------------
# Context is preserved across nested transitions
# ---------------------------------------------------------------------------


def test_user_preserved_through_screen_lock_unlock():
    machine = make_session_machine()
    state = _login_succeed(machine, user="dave")
    state = machine.transition(state, "GO_IDLE")
    state = machine.transition(state, "LONG_TIMEOUT")
    state = machine.transition(state, {"type": "UNLOCK", "pin": "1234"})
    assert state.context["user"] == "dave"
