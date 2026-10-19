"""Every third-party package the `adscout` package imports is a declared runtime dependency."""

import ast
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "adscout"


def imported_top_level_modules(source: Path) -> set[str]:
    modules: set[str] = set()
    for path in source.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return modules


def normalized(name: str) -> str:
    # PEP 503 name normalization.
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_dependencies() -> set[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = (
        re.split(r"[\s<>=!~;\[]", spec, maxsplit=1)[0] for spec in data["project"]["dependencies"]
    )
    return {normalized(name) for name in names}


def undeclared_imports(source: Path, declared: set[str]) -> list[str]:
    distributions = metadata.packages_distributions()
    third_party = {
        module
        for module in imported_top_level_modules(source)
        if module not in sys.stdlib_module_names and module != "adscout"
    }
    missing = []
    for module in sorted(third_party):
        owners = {normalized(name) for name in distributions.get(module, [module])}
        if not owners & declared:
            missing.append(module)
    return missing


def imported_modules(source: Path) -> set[str]:
    """Full dotted names of every absolute import, for the forbidden-module check."""
    modules: set[str] = set()
    for path in source.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module)
    return modules


# Adding a runtime dependency is a design decision (PROJECT.md §4): update this set with it.
RUNTIME_DEPENDENCIES = {"anthropic", "httpx2", "langgraph", "pydantic", "pyyaml"}

# Phase 2 design decision 24: LangGraph orchestrates plain typed functions; every model call
# goes through our adapter on the anthropic SDK. These would bypass it or send telemetry.
FORBIDDEN_MODULES = (
    "claude_agent_sdk",
    "crewai",
    "langchain_anthropic",
    "langgraph.checkpoint",
    "langgraph.prebuilt",
    "langsmith",
)


def forbidden_imports(source: Path) -> list[str]:
    return sorted(
        module
        for module in imported_modules(source)
        if any(module == name or module.startswith(f"{name}.") for name in FORBIDDEN_MODULES)
    )


def test_every_third_party_import_is_declared() -> None:
    assert undeclared_imports(SRC, declared_dependencies()) == []


def test_runtime_dependencies_are_the_decided_set() -> None:
    assert declared_dependencies() == RUNTIME_DEPENDENCIES


def test_no_forbidden_framework_is_imported() -> None:
    assert forbidden_imports(SRC) == []


def test_a_forbidden_import_is_reported(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        "from langgraph.graph import StateGraph\n"
        "from langgraph.prebuilt import create_react_agent\n"
        "import langsmith\n",
        encoding="utf-8",
    )
    assert forbidden_imports(tmp_path) == ["langgraph.prebuilt", "langsmith"]


def test_an_undeclared_import_is_reported(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("import yaml\nimport json\n", encoding="utf-8")
    assert undeclared_imports(tmp_path, declared={"pydantic"}) == ["yaml"]
    assert undeclared_imports(tmp_path, declared={"pyyaml"}) == []
