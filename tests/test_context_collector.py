# tests/test_context_collector.py
"""
Tests for the project context collector.

Tests language/framework/tool detection, directory tree building,
import graph extraction, and the full context pipeline.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from aicodereviewer.context_collector import (
    collect_project_context,
    detect_frameworks,
    ProjectContext,
    _detect_languages,
    _detect_tools,
    _build_dir_tree,
    _build_import_graph,
    _detect_naming,
    _count_files,
)


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def python_project(tmp_path):
    """Create a minimal Python project structure."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "requirements.txt").write_text("requests\nflask\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        "from flask import Flask\n"
        "from . import config\n"
        "app = Flask(__name__)\n"
    )
    (src / "config.py").write_text(
        "import os\n"
        "DEBUG = os.getenv('DEBUG', False)\n"
    )
    (src / "utils.py").write_text(
        "def helper_function():\n"
        "    return 42\n"
    )
    return tmp_path


@pytest.fixture
def js_project(tmp_path):
    """Create a minimal JavaScript project structure."""
    (tmp_path / "package.json").write_text(
        '{"name": "demo", "dependencies": {"react": "^18.0.0", "next": "^14.0.0"}}'
    )
    (tmp_path / ".eslintrc.json").write_text("{}")
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.js").write_text(
        'import React from "react";\n'
        'const App = () => <div>Hello</div>;\n'
    )
    return tmp_path


# ── Language detection ────────────────────────────────────────────────────

class TestDetectLanguages:
    def test_python_detected(self, python_project):
        langs = _detect_languages(python_project)
        assert "Python" in langs

    def test_javascript_detected(self, js_project):
        langs = _detect_languages(js_project)
        assert "JavaScript" in langs

    def test_empty_dir(self, tmp_path):
        langs = _detect_languages(tmp_path)
        assert langs == []


# ── Framework detection ───────────────────────────────────────────────────

class TestDetectFrameworks:
    def test_flask_detected_from_import(self, python_project):
        scanned = [str(python_project / "src" / "app.py")]
        fws = detect_frameworks(python_project, scanned)
        assert "flask" in fws

    def test_react_detected_from_package_json(self, js_project):
        fws = detect_frameworks(js_project)
        assert "react" in fws

    def test_nextjs_detected(self, js_project):
        fws = detect_frameworks(js_project)
        assert "next.js" in fws

    def test_empty_dir(self, tmp_path):
        fws = detect_frameworks(tmp_path)
        assert fws == []


# ── Tool detection ────────────────────────────────────────────────────────

class TestDetectTools:
    def test_eslint_detected(self, js_project):
        tools = _detect_tools(js_project)
        assert "eslint" in tools

    def test_pyproject_tool_sections(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.black]\nline-length = 88\n[tool.ruff]\nselect = ['E']\n"
        )
        tools = _detect_tools(tmp_path)
        assert "black" in tools
        assert "ruff" in tools


# ── Directory tree ────────────────────────────────────────────────────────

class TestBuildDirTree:
    def test_basic_tree(self, python_project):
        tree = _build_dir_tree(python_project, max_depth=2)
        assert "src/" in tree
        assert "app.py" in tree

    def test_skips_pycache(self, tmp_path):
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.cpython-311.pyc").write_bytes(b"")
        (tmp_path / "real.py").write_text("x = 1")
        tree = _build_dir_tree(tmp_path, max_depth=1)
        assert "__pycache__" not in tree
        assert "real.py" in tree


# ── Import graph ──────────────────────────────────────────────────────────

class TestBuildImportGraph:
    def test_python_imports(self, python_project):
        files = [
            str(python_project / "src" / "app.py"),
            str(python_project / "src" / "config.py"),
        ]
        edges = _build_import_graph(files, python_project)
        # app.py imports flask and config
        sources = {src for src, _ in edges}
        assert any("app.py" in s for s in sources)


# ── Naming convention ─────────────────────────────────────────────────────

class TestDetectNaming:
    def test_snake_case(self, python_project):
        files = [
            str(python_project / "src" / "utils.py"),
            str(python_project / "src" / "config.py"),
        ]
        naming = _detect_naming(files)
        assert "snake_case" in naming

    def test_camel_case(self, tmp_path):
        (tmp_path / "code.js").write_text(
            "function getUserName() {}\n"
            "let firstName = 'Alice';\n"
            "let lastName = 'Bob';\n"
            "function getAge() {}\n"
        )
        naming = _detect_naming([str(tmp_path / "code.js")])
        assert "camelCase" in naming


# ── File counting ─────────────────────────────────────────────────────────

class TestCountFiles:
    def test_counts(self, python_project):
        counts, total = _count_files(python_project)
        assert total >= 3  # at least pyproject.toml, requirements.txt, 3 .py files
        assert ".py" in counts
        assert ".toml" in counts or ".txt" in counts


# ── Full pipeline ─────────────────────────────────────────────────────────

class TestCollectProjectContext:
    def test_full_context(self, python_project):
        scanned = [str(python_project / "src" / f) for f in ("app.py", "config.py", "utils.py")]
        ctx = collect_project_context(str(python_project), scanned)
        assert "Python" in ctx.languages
        assert "flask" in ctx.frameworks
        assert ctx.total_files > 0

    def test_prompt_string(self, python_project):
        ctx = collect_project_context(str(python_project))
        prompt = ctx.to_prompt_string(max_tokens=500)
        assert "PROJECT CONTEXT:" in prompt
        assert "Python" in prompt

    def test_nonexistent_path(self):
        ctx = collect_project_context("/nonexistent/path/12345")
        assert ctx.languages == []
        assert ctx.frameworks == []

    def test_truncation(self, python_project):
        ctx = collect_project_context(str(python_project))
        short = ctx.to_prompt_string(max_tokens=10)
        # 10 tokens ≈ 40 chars; should be truncated
        assert len(short) <= 100 or "truncated" in short
