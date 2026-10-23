"""Keep the pywebview API bridge aligned with every method used by the SPA."""
import ast
from pathlib import Path


def test_api_exposes_import_commit_and_settings_methods():
    source = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    api = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Api")
    methods = {node.name for node in api.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {
        "import_certificate",
        "commit_imported_certificate",
        "get_settings",
        "save_settings",
    } <= methods
