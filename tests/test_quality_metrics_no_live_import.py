"""Import-isolation guard for the ``quality_metrics`` package.

Proves — statically where possible, with a runtime confirmation — that the pure
advisory quality scorer (``quality_metrics/advisory_quality_scorer.py``,
ALLOC-003D) is import-isolated and broker-free: it imports **no** allocation/
broker/live module and references **no** runtime path (never
``allocation_history.json``). This is the standing tripwire that keeps the scorer
a non-live, side-effect-free, recommendation-only layer; reading real allocation
history or wiring any downstream export is a separate HUMAN_GATED step which must
consciously update this guard.

Hermeticity: imports only the stdlib (``ast``, ``importlib``, ``sys``,
``pathlib``, ``unittest``). Runs with
``python -S -m unittest tests.test_quality_metrics_no_live_import``.
"""
from __future__ import annotations

import ast
import importlib
import sys
import unittest
from pathlib import Path

_PACKAGE = "quality_metrics"
_PACKAGE_DIR = Path(__file__).resolve().parent.parent / _PACKAGE

_ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "dataclasses",
    "typing",
    "math",
    _PACKAGE,
}

_FORBIDDEN_IMPORT_ROOTS = {
    "ib_insync", "ibapi", "ib", "ib_gateway",
    "core", "workflow", "utils", "config", "tools",
    "dotenv", "wrangler", "cloudflare",
    "os", "io", "socket", "subprocess", "requests", "urllib", "http",
    "numpy", "pandas",
}

_FORBIDDEN_STRING_TOKENS = (
    "ib_insync", "ibapi", "placeorder", ".env", "result_snapshot",
    "allocation_history", "public/data", "public\\data", "data/system",
    "data\\system", "data/history", "wrangler", "cloudflare", "os.environ",
    "secret", "password", "koopbot", "verkoopbot", "scheduler",
)


def _module_files() -> list[Path]:
    return sorted(_PACKAGE_DIR.glob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                roots.add(_PACKAGE)
            elif node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _non_docstring_strings(tree: ast.Module) -> list[str]:
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    out: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            out.append(node.value)
    return out


class QualityMetricsNoLiveImportTest(unittest.TestCase):
    def test_package_has_modules(self) -> None:
        names = {f.name for f in _module_files()}
        self.assertIn("__init__.py", names)
        self.assertIn("advisory_quality_scorer.py", names)

    def test_imports_are_pure_stdlib_allowlist(self) -> None:
        for path in _module_files():
            roots = _import_roots(_parse(path))
            unexpected = roots - _ALLOWED_IMPORT_ROOTS
            self.assertEqual(unexpected, set(),
                             f"{path.name} imports outside the allowlist: {unexpected}")

    def test_no_forbidden_import_roots(self) -> None:
        for path in _module_files():
            roots = _import_roots(_parse(path))
            offending = roots & _FORBIDDEN_IMPORT_ROOTS
            self.assertEqual(offending, set(),
                             f"{path.name} imports forbidden module(s): {offending}")

    def test_no_forbidden_runtime_or_secret_strings(self) -> None:
        for path in _module_files():
            for literal in _non_docstring_strings(_parse(path)):
                low = literal.lower()
                for token in _FORBIDDEN_STRING_TOKENS:
                    self.assertNotIn(token, low,
                                     f"{path.name} string literal references {token!r}: {literal!r}")

    def test_fresh_import_pulls_no_forbidden_module(self) -> None:
        for name in [m for m in sys.modules if m == _PACKAGE or m.startswith(_PACKAGE + ".")]:
            del sys.modules[name]
        before = set(sys.modules)
        importlib.import_module("quality_metrics.advisory_quality_scorer")
        added = set(sys.modules) - before
        for name in added:
            root = name.split(".")[0]
            self.assertNotIn(root, _FORBIDDEN_IMPORT_ROOTS, f"importing the package pulled in {name!r}")
            self.assertNotIn("ib_insync", name)

    def test_module_is_importable_and_callable(self) -> None:
        from quality_metrics.advisory_quality_scorer import score_outcome, turnover_warning
        self.assertTrue(callable(score_outcome))
        self.assertTrue(callable(turnover_warning))


if __name__ == "__main__":
    unittest.main()
