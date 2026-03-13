"""Data layer for .issuetracker file I/O.

Handles all reads/writes to .issuetracker/ folders including
config management, issue CRUD, project CRUD, ID allocation,
atomic writes, and dependency validation.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class CircularDependencyError(Exception):
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tracker_path(workspace: Path) -> Path:
    return workspace / ".issuetracker"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, data: dict) -> None:
    dir_ = path.parent
    _ensure_dir(dir_)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _issue_path(workspace: Path, issue_id: int) -> Path:
    return _tracker_path(workspace) / "issues" / f"{issue_id:03d}.json"


def _project_path(workspace: Path, project_id: int) -> Path:
    return _tracker_path(workspace) / "projects" / f"{project_id:03d}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_cycle(workspace: Path, issue_id: int, blocked_by: list) -> bool:
    """Return True if adding blocked_by edges to issue_id would create a cycle."""
    # Build adjacency: issue -> list of issues it is blocked by
    issues, _ = list_issues(workspace)
    graph: dict[int, list[int]] = {}
    for issue in issues:
        graph[issue["id"]] = list(issue.get("blockedBy", []))
    # Apply the proposed change
    graph[issue_id] = list(blocked_by)

    # DFS from issue_id — if we can reach issue_id again, there's a cycle
    visited: set[int] = set()
    stack = list(blocked_by)
    while stack:
        node = stack.pop()
        if node == issue_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph.get(node, []))
    return False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def read_config(workspace: Path) -> dict:
    path = _tracker_path(workspace) / "config.json"
    with open(path) as f:
        return json.load(f)


def write_config(workspace: Path, config: dict) -> None:
    path = _tracker_path(workspace) / "config.json"
    _atomic_write(path, config)


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

def create_issue(workspace: Path, data: dict) -> dict:
    config = read_config(workspace)
    next_id = config.get("nextIssueId", 1)
    issue_id = next_id

    issues_dir = _tracker_path(workspace) / "issues"
    _ensure_dir(issues_dir)

    now = _now_iso()
    issue = {
        "id": issue_id,
        "createdAt": now,
        "updatedAt": now,
        **data,
    }
    _atomic_write(_issue_path(workspace, issue_id), issue)

    config["nextIssueId"] = next_id + 1
    write_config(workspace, config)
    return issue


def list_issues(workspace: Path) -> tuple[list[dict], list[str]]:
    issues_dir = _tracker_path(workspace) / "issues"
    issues: list[dict] = []
    warnings: list[str] = []

    _ensure_dir(issues_dir)

    for p in sorted(issues_dir.glob("*.json")):
        try:
            with open(p) as f:
                issues.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            warnings.append(f"Failed to load {p.name}: {e}")

    return issues, warnings


def get_issue(workspace: Path, issue_id: int) -> dict | None:
    path = _issue_path(workspace, issue_id)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def update_issue(workspace: Path, issue_id: int, updates: dict) -> dict | None:
    issue = get_issue(workspace, issue_id)
    if issue is None:
        return None

    if "blockedBy" in updates:
        if _has_cycle(workspace, issue_id, updates["blockedBy"]):
            raise CircularDependencyError(
                f"Adding blockedBy {updates['blockedBy']} to issue {issue_id} would create a cycle"
            )

    issue.update(updates)
    issue["updatedAt"] = _now_iso()
    _atomic_write(_issue_path(workspace, issue_id), issue)
    return issue


def delete_issue(workspace: Path, issue_id: int) -> bool:
    path = _issue_path(workspace, issue_id)
    if not path.exists():
        return False
    path.unlink()

    # Delete assets folder for this issue if it exists
    assets_dir = _tracker_path(workspace) / "assets" / str(issue_id)
    if assets_dir.exists():
        shutil.rmtree(assets_dir)

    # Clean up blockedBy references in other issues
    all_issues, _ = list_issues(workspace)
    for issue in all_issues:
        blocked_by = issue.get("blockedBy", [])
        if issue_id in blocked_by:
            new_blocked_by = [b for b in blocked_by if b != issue_id]
            issue["blockedBy"] = new_blocked_by
            issue["updatedAt"] = _now_iso()
            _atomic_write(_issue_path(workspace, issue["id"]), issue)

    return True


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def create_project(workspace: Path, data: dict) -> dict:
    config = read_config(workspace)
    next_id = config.get("nextProjectId", 1)
    project_id = next_id

    projects_dir = _tracker_path(workspace) / "projects"
    _ensure_dir(projects_dir)

    now = _now_iso()
    project = {
        "id": project_id,
        "createdAt": now,
        "updatedAt": now,
        **data,
    }
    _atomic_write(_project_path(workspace, project_id), project)

    config["nextProjectId"] = next_id + 1
    write_config(workspace, config)
    return project


def list_projects(workspace: Path) -> tuple[list[dict], list[str]]:
    projects_dir = _tracker_path(workspace) / "projects"
    projects: list[dict] = []
    warnings: list[str] = []

    _ensure_dir(projects_dir)

    for p in sorted(projects_dir.glob("*.json")):
        try:
            with open(p) as f:
                projects.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            warnings.append(f"Failed to load {p.name}: {e}")

    return projects, warnings


def get_project(workspace: Path, project_id: int) -> dict | None:
    path = _project_path(workspace, project_id)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def update_project(workspace: Path, project_id: int, updates: dict) -> dict | None:
    project = get_project(workspace, project_id)
    if project is None:
        return None
    project.update(updates)
    project["updatedAt"] = _now_iso()
    _atomic_write(_project_path(workspace, project_id), project)
    return project


def delete_project(workspace: Path, project_id: int) -> bool:
    path = _project_path(workspace, project_id)
    if not path.exists():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Workspace management
# ---------------------------------------------------------------------------

def init_workspace(workspace: Path, name: str) -> dict:
    tracker = _tracker_path(workspace)
    _ensure_dir(tracker / "issues")
    _ensure_dir(tracker / "projects")
    _ensure_dir(tracker / "assets")

    config = {
        "name": name,
        "nextIssueId": 1,
        "nextProjectId": 1,
        "createdAt": _now_iso(),
    }
    _atomic_write(tracker / "config.json", config)
    return config


def list_workspaces(root_path: Path) -> list[dict]:
    result = []
    for entry in sorted(root_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        has_tracker = (entry / ".issuetracker").is_dir()
        result.append({"name": entry.name, "path": str(entry), "hasTracker": has_tracker})
    return result
