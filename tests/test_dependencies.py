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


def test_every_third_party_import_is_declared() -> None:
    assert undeclared_imports(SRC, declared_dependencies()) == []


def test_an_undeclared_import_is_reported(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("import yaml\nimport json\n", encoding="utf-8")
    assert undeclared_imports(tmp_path, declared={"pydantic"}) == ["yaml"]
    assert undeclared_imports(tmp_path, declared={"pyyaml"}) == []
