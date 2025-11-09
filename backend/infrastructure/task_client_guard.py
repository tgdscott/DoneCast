"""Guard test to ensure only tasks_client.py imports task dispatch libraries.

This test scans all Python files in the backend directory and fails if any file
(other than tasks_client.py itself) imports httpx, requests, google.cloud.tasks,
or multiprocessing for task dispatch purposes.

Note: This test allows imports in test files and allows multiprocessing imports
for non-dispatch purposes (e.g., Process class usage for parallelism).
"""
import ast
import os
from pathlib import Path
from typing import List, Set

import pytest


# Modules that are forbidden to import for task dispatch
# Note: httpx and requests are used for external APIs, so we only flag them
# in specific contexts (task-related directories). google.cloud.tasks is
# strictly forbidden outside of tasks_client.py.
FORBIDDEN_IMPORTS_STRICT = {
    "google.cloud.tasks",  # Always forbidden (except tasks_client.py)
}

FORBIDDEN_IMPORTS_CONTEXTUAL = {
    "httpx",  # Flagged only in task-related directories
    "requests",  # Flagged only in task-related directories
    "multiprocessing",  # Flagged only in task-related directories
}

# Directories where httpx/requests/multiprocessing imports are suspicious
# (indicating potential task dispatch usage)
TASK_RELATED_DIRS = {
    "api/services/episodes",
    "api/routers",
    "worker/tasks",
}

# Files that are allowed to import these modules
ALLOWED_FILES = {
    "backend/infrastructure/tasks_client.py",  # The only allowed dispatch path
    "backend/infrastructure/task_client_guard.py",  # The guard test itself
}

# Directories to exclude from scanning
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".pytest_cache",
    "venv",
    "env",
    ".venv",
}

# File patterns to exclude
EXCLUDE_PATTERNS = {
    "test_",
    "_test.py",
    "conftest.py",
}


class ImportVisitor(ast.NodeVisitor):
    """AST visitor to collect import statements."""

    def __init__(self):
        self.imports: Set[str] = set()

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])

    def visit_ImportFrom(self, node):
        if node.module:
            module_name = node.module.split(".")[0]
            self.imports.add(module_name)
            # Also check for full module paths
            if "." in node.module:
                self.imports.add(node.module)


def is_in_task_related_dir(file_path: Path, backend_root: Path) -> bool:
    """Check if file is in a task-related directory."""
    try:
        rel_path = file_path.relative_to(backend_root)
        rel_path_str = str(rel_path).replace("\\", "/")
        # Check if any task-related directory is in the path
        for task_dir in TASK_RELATED_DIRS:
            if task_dir in rel_path_str:
                return True
        return False
    except ValueError:
        return False


def scan_file(file_path: Path, backend_root: Path) -> List[str]:
    """Scan a Python file for forbidden imports.

    Returns:
        List of forbidden import names found in the file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        # Skip files with syntax errors (may be in development)
        return []

    visitor = ImportVisitor()
    visitor.visit(tree)

    found = []
    in_task_dir = is_in_task_related_dir(file_path, backend_root)
    
    # Check strict forbidden imports (always flag)
    for forbidden in FORBIDDEN_IMPORTS_STRICT:
        for imp in visitor.imports:
            if imp == forbidden or imp.startswith(forbidden.split(".")[0]):
                found.append(forbidden)
                break
    
    # Check contextual forbidden imports (only flag in task-related directories)
    if in_task_dir:
        for forbidden in FORBIDDEN_IMPORTS_CONTEXTUAL:
            for imp in visitor.imports:
                if imp == forbidden or imp.startswith(forbidden.split(".")[0]):
                    # Skip multiprocessing in test files
                    if forbidden == "multiprocessing":
                        if any(
                            pattern in file_path.name.lower()
                            for pattern in EXCLUDE_PATTERNS
                        ):
                            continue
                    found.append(forbidden)
                    break

    return list(set(found))  # Deduplicate


def should_scan_file(file_path: Path, backend_root: Path) -> bool:
    """Determine if a file should be scanned."""
    # Convert to relative path from backend root
    try:
        rel_path = file_path.relative_to(backend_root)
        rel_path_str = str(rel_path).replace("\\", "/")
    except ValueError:
        return False

    # Skip if in excluded directory
    for part in rel_path.parts:
        if part in EXCLUDE_DIRS:
            return False

    # Skip if matches exclude pattern
    if any(pattern in file_path.name for pattern in EXCLUDE_PATTERNS):
        return False

    # Skip if it's an allowed file
    if rel_path_str in ALLOWED_FILES:
        return False

    # Only scan Python files
    return file_path.suffix == ".py"


def collect_python_files(backend_root: Path) -> List[Path]:
    """Collect all Python files to scan."""
    python_files = []
    for root, dirs, files in os.walk(backend_root):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                if should_scan_file(file_path, backend_root):
                    python_files.append(file_path)

    return python_files


def test_no_unauthorized_task_imports():
    """Fail if any file except tasks_client.py imports task dispatch libraries.

    This test ensures that all task dispatch goes through tasks_client.py.
    """
    # Find backend root (parent of infrastructure/)
    current_file = Path(__file__).resolve()
    backend_root = current_file.parent.parent

    violations = []
    python_files = collect_python_files(backend_root)

    for file_path in python_files:
        forbidden = scan_file(file_path, backend_root)
        if forbidden:
            rel_path = file_path.relative_to(backend_root)
            violations.append((str(rel_path), forbidden))

    if violations:
        error_msg = "Found unauthorized task dispatch imports:\n\n"
        for file_path, imports in violations:
            error_msg += f"  {file_path}: {', '.join(imports)}\n"
        error_msg += "\nAll task dispatch must go through infrastructure.tasks_client.enqueue_http_task()\n"
        error_msg += "Do not import httpx, requests, google.cloud.tasks, or multiprocessing for task dispatch."
        pytest.fail(error_msg)


# Make the test discoverable and runnable directly
if __name__ == "__main__":
    # Run the test manually
    test_no_unauthorized_task_imports()

