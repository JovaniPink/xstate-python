from __future__ import annotations

import asyncio
import inspect
from contextlib import suppress
from typing import Any


def _has_pytest_asyncio(config: Any) -> bool:
    pluginmanager = config.pluginmanager
    return pluginmanager.hasplugin("asyncio") or pluginmanager.hasplugin(
        "pytest_asyncio"
    )


def pytest_addoption(parser: Any) -> None:
    with suppress(ValueError):
        parser.addini("asyncio_mode", "pytest-asyncio compatibility mode")


def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    """Run async tests when pytest-asyncio is unavailable in the local env."""

    if _has_pytest_asyncio(pyfuncitem.config):
        return None

    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    fixture_names = pyfuncitem._fixtureinfo.argnames
    kwargs = {name: pyfuncitem.funcargs[name] for name in fixture_names}
    asyncio.run(test_func(**kwargs))
    return True
