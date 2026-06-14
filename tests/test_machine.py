from xstate.machine import Machine


def make_lights():
    return Machine(
        {
            "id": "lights",
            "initial": "green",
            "states": {
                "green": {
                    "on": {"TIMER": "yellow"},
                    "entry": [{"type": "enterGreen"}],
                },
                "yellow": {"on": {"TIMER": "red"}},
                "red": {
                    "initial": "walk",
                    "states": {
                        "walk": {"on": {"COUNTDOWN": "wait"}},
                        "wait": {"on": {"COUNTDOWN": "stop"}},
                        "stop": {"on": {"TIMEOUT": "timeout"}},
                        "timeout": {"type": "final"},
                    },
                    "onDone": "green",
                },
            },
        }
    )


def test_machine():
    lights = make_lights()
    yellow = lights.transition(lights.initial_state, "TIMER")
    assert yellow.value == "yellow"

    red = lights.transition(yellow, "TIMER")
    assert red.value == {"red": "walk"}


def test_initial_state_is_green():
    lights = make_lights()
    assert lights.initial_state.value == "green"


def test_final_state_triggers_on_done():
    lights = make_lights()
    red_stop = lights.state_from({"red": "stop"})
    result = lights.transition(red_stop, "TIMEOUT")
    assert result.value == "green"
