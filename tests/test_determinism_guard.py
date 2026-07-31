"""The determinism contract, enforced by reading the source.

T-3 catches non-determinism after the fact, once it has already leaked into a
trace. This test catches the ways it usually gets in, before a run happens at
all: an import of `time`, a stray `uuid4`, a `hash()` on something whose hash
is salted per process.

A lint rule covers the same imports (ruff TID251) and is the faster feedback
loop. This exists as well because it is precise where the lint rule is blunt —
it can allow `random` in exactly one module and nowhere else — and because a
lint rule lives in a config file that is one `# noqa` away from being silenced.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

GUARDED_PACKAGES = ("cassette/sim", "cassette/kv")

BANNED_MODULES = {
    "asyncio": "the core is single-threaded on purpose",
    "datetime": "use env.now()",
    "multiprocessing": "the core is single-threaded on purpose",
    "os": "no I/O in the core; it arrives through Env",
    "pathlib": "no I/O in the core; it arrives through Env",
    "random": "use env.random(), which draws from the seeded source",
    "secrets": "nothing in a simulation may be unpredictable",
    "socket": "there is no real network here",
    "subprocess": "no I/O in the core; it arrives through Env",
    "threading": "the core is single-threaded on purpose",
    "time": "use env.now()",
    "uuid": "identifiers are counters so that they replay",
}

BANNED_CALLS = {
    "hash": "str hashes are salted per process; PYTHONHASHSEED would change the run",
    "id": "object addresses differ between runs",
    "input": "no I/O in the core",
    "open": "no I/O in the core; it arrives through Env",
    "print": "the core reports through the Observer",
}

ALLOWED = {
    # The one module permitted to reach for randomness, so that every other
    # module cannot. Its whole job is to wrap this import in something seeded.
    ("cassette/sim/rng.py", "random"),
}

REPO_ROOT = Path(__file__).resolve().parent.parent


def guarded_sources() -> list[Path]:
    files: list[Path] = []
    for package in GUARDED_PACKAGES:
        files.extend(sorted((REPO_ROOT / package).rglob("*.py")))
    return files


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


def called_builtins(tree: ast.AST) -> list[tuple[str, int]]:
    return [
        (node.func.id, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


def test_the_guard_looks_at_something() -> None:
    assert len(guarded_sources()) >= 10


@pytest.mark.parametrize("path", guarded_sources(), ids=relative)
def test_no_banned_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for module, lineno in imported_modules(tree):
        if module not in BANNED_MODULES:
            continue
        if (relative(path), module) in ALLOWED:
            continue
        pytest.fail(
            f"{relative(path)}:{lineno} imports {module!r} — {BANNED_MODULES[module]}",
            pytrace=False,
        )


@pytest.mark.parametrize("path", guarded_sources(), ids=relative)
def test_no_banned_calls(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for name, lineno in called_builtins(tree):
        if name in BANNED_CALLS:
            pytest.fail(
                f"{relative(path)}:{lineno} calls {name}() — {BANNED_CALLS[name]}",
                pytrace=False,
            )


def test_the_guard_would_notice_a_violation() -> None:
    """A guard nobody has seen fail is a guard nobody knows works."""
    tree = ast.parse("import time\nfrom uuid import uuid4\nx = hash('a')\n")
    assert ("time", 1) in imported_modules(tree)
    assert ("uuid", 2) in imported_modules(tree)
    assert ("hash", 3) in called_builtins(tree)


def test_the_guard_ignores_relative_imports() -> None:
    tree = ast.parse("from . import os\n")
    assert imported_modules(tree) == []


def test_the_allowlist_stays_short() -> None:
    """Every entry here is a hole in the contract. Two would already be one too many."""
    assert len(ALLOWED) == 1


def test_the_allowlist_points_at_files_that_exist() -> None:
    for path, _ in ALLOWED:
        assert (REPO_ROOT / path).is_file()
