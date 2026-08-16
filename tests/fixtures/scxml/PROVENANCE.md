# SCXML Fixture Provenance

The `.scxml` and `.json` files in the child directories are an unmodified, focused subset of the
SCXML Test Framework fixtures used by this project's configured conformance tests.

- Source: `https://gitlab.com/scion-scxml/test-framework.git`
- Source commit: `b46a10a1c3a3b1ca5c5cb4bb44ddb5c785611f41`
- Source paths: `test/<group>/<case>.scxml` and `test/<group>/<case>.json`
- License: Apache License 2.0; see `LICENSE.txt` in this directory.

Only the cases enumerated in `tests/test_scxml.py` are vendored. The JavaScript runner, package
manifest, lockfile, and unused fixtures are intentionally excluded so Python tests do not inherit
the third-party Node dependency graph.
