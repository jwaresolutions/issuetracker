# Generic Issue Tracker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable, local-first issue tracker with a FastAPI backend, single-file HTML frontend, and Claude Code skill for direct file interaction.

**Architecture:** FastAPI server reads/writes individual JSON files in per-project `.issuetracker/` folders. Single `index.html` with embedded CSS/JS provides the UI. A Claude skill enables CLI-based issue management without the server.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, vanilla HTML/CSS/JS, pytest

---

## Chunk 1: Project Setup & Data Layer

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `tracker.config.json`
- Create: `.gitignore`
- Create: `.issuetracker/config.json`
- Create: `.issuetracker/issues/` (empty dir)
- Create: `.issuetracker/projects/` (empty dir)
- Create: `.issuetracker/assets/` (empty dir)

- [ ] **Step 1: Create requirements.txt**

```
fastapi>=0.115.0
uvicorn>=0.30.0
pytest>=8.0.0
httpx>=0.27.0
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
tracker.config.json
```

- [ ] **Step 3: Create tracker.config.json (default config)**

```json
{
  "rootPath": null
}
```

Note: `null` means "use default" (one directory above this repo). This file is gitignored since it contains local paths.

- [ ] **Step 4: Create .issuetracker/ scaffold for self-tracking**

Create `.issuetracker/config.json`:
```json
{
  "name": "Issue Tracker",
  "nextIssueId": 1,
  "nextProjectId": 1,
  "reviewers": ["PM", "Dev Lead", "Security"]
}
```

Create empty directories: `.issuetracker/issues/`, `.issuetracker/projects/`, `.issuetracker/assets/`. Add a `.gitkeep` in each empty directory.

- [ ] **Step 5: Install dependencies**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
Expected: All packages install successfully.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore .issuetracker/
git commit -m "chore: project scaffolding with dependencies and self-tracking"
```

---

### Task 2: Data layer — file I/O helpers

**Files:**
- Create: `data.py`
- Create: `tests/test_data.py`

The data layer handles all reads/writes to `.issuetracker/` folders. It is the single module responsible for file I/O, ID management, atomic writes, and validation. The server and skill both depend on this layer.

- [ ] **Step 1: Write failing test — read_config**

Create `tests/__init__.py` (empty) and `tests/test_data.py`:

```python
import json
import pytest
from pathlib import Path


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal .issuetracker scaffold in a temp directory."""
    tracker = tmp_path / ".issuetracker"
    tracker.mkdir()
    (tracker / "issues").mkdir()
    (tracker / "projects").mkdir()
    (tracker / "assets").mkdir()
    config = {
        "name": "Test Project",
        "nextIssueId": 1,
        "nextProjectId": 1,
        "reviewers": ["PM", "Dev Lead", "Security"],
    }
    (tracker / "config.json").write_text(json.dumps(config, indent=2))
    return tmp_path


def test_read_config(workspace):
    from data import read_config

    config = read_config(workspace)
    assert config["name"] == "Test Project"
    assert config["nextIssueId"] == 1
    assert config["reviewers"] == ["PM", "Dev Lead", "Security"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py::test_read_config -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data'`

- [ ] **Step 3: Implement read_config and write_config**

Create `data.py`:

```python
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
from pathlib import Path
from datetime import datetime, timezone


def _tracker_path(workspace: Path) -> Path:
    return workspace / ".issuetracker"


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically: write to temp file, then rename."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
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


def read_config(workspace: Path) -> dict:
    """Read .issuetracker/config.json for a workspace."""
    path = _tracker_path(workspace) / "config.json"
    return json.loads(path.read_text())


def write_config(workspace: Path, config: dict) -> None:
    """Write .issuetracker/config.json atomically."""
    path = _tracker_path(workspace) / "config.json"
    _atomic_write(path, config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py::test_read_config -v`
Expected: PASS

- [ ] **Step 5: Write failing test — create_issue**

Add to `tests/test_data.py`:

```python
def test_create_issue(workspace):
    from data import create_issue, read_config

    issue_data = {
        "title": "Test issue",
        "description": "A test issue",
        "status": "open",
        "priority": "high",
        "labels": ["bug"],
        "projectId": None,
        "cycle": None,
        "personas": [],
        "files": [],
        "blockedBy": [],
        "reviews": {},
        "userVote": {"verdict": None, "notes": ""},
    }
    issue = create_issue(workspace, issue_data)
    assert issue["id"] == 1
    assert issue["title"] == "Test issue"
    assert "createdAt" in issue
    assert "updatedAt" in issue

    # Verify config was updated
    config = read_config(workspace)
    assert config["nextIssueId"] == 2

    # Verify file exists
    issue_file = workspace / ".issuetracker" / "issues" / "001.json"
    assert issue_file.exists()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py::test_create_issue -v`
Expected: FAIL with `ImportError: cannot import name 'create_issue'`

- [ ] **Step 7: Implement create_issue**

Add to `data.py`:

```python
def _issue_path(workspace: Path, issue_id: int) -> Path:
    return _tracker_path(workspace) / "issues" / f"{issue_id:03d}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_issue(workspace: Path, data: dict) -> dict:
    """Create a new issue. Auto-assigns ID from config."""
    _ensure_dir(_tracker_path(workspace) / "issues")
    config = read_config(workspace)
    issue_id = config["nextIssueId"]
    config["nextIssueId"] = issue_id + 1
    write_config(workspace, config)

    issue = {
        "id": issue_id,
        **data,
        "createdAt": _now_iso(),
        "updatedAt": _now_iso(),
    }
    _atomic_write(_issue_path(workspace, issue_id), issue)
    return issue
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py::test_create_issue -v`
Expected: PASS

- [ ] **Step 9: Write failing tests — list_issues, get_issue, update_issue, delete_issue**

Add to `tests/test_data.py`:

```python
def test_list_issues(workspace):
    from data import create_issue, list_issues

    create_issue(workspace, {
        "title": "First", "description": "", "status": "open",
        "priority": "high", "labels": [], "projectId": None,
        "cycle": None, "personas": [], "files": [], "blockedBy": [],
        "reviews": {}, "userVote": {"verdict": None, "notes": ""},
    })
    create_issue(workspace, {
        "title": "Second", "description": "", "status": "open",
        "priority": "low", "labels": [], "projectId": None,
        "cycle": None, "personas": [], "files": [], "blockedBy": [],
        "reviews": {}, "userVote": {"verdict": None, "notes": ""},
    })
    issues, warnings = list_issues(workspace)
    assert len(issues) == 2
    assert issues[0]["title"] == "First"
    assert issues[1]["title"] == "Second"
    assert len(warnings) == 0


def test_get_issue(workspace):
    from data import create_issue, get_issue

    created = create_issue(workspace, {
        "title": "Get me", "description": "", "status": "open",
        "priority": "medium", "labels": [], "projectId": None,
        "cycle": None, "personas": [], "files": [], "blockedBy": [],
        "reviews": {}, "userVote": {"verdict": None, "notes": ""},
    })
    issue = get_issue(workspace, created["id"])
    assert issue["title"] == "Get me"


def test_get_issue_not_found(workspace):
    from data import get_issue

    assert get_issue(workspace, 999) is None


def test_update_issue(workspace):
    from data import create_issue, update_issue, get_issue

    created = create_issue(workspace, {
        "title": "Original", "description": "", "status": "open",
        "priority": "high", "labels": [], "projectId": None,
        "cycle": None, "personas": [], "files": [], "blockedBy": [],
        "reviews": {}, "userVote": {"verdict": None, "notes": ""},
    })
    updated = update_issue(workspace, created["id"], {"title": "Updated", "status": "done"})
    assert updated["title"] == "Updated"
    assert updated["status"] == "done"

    reread = get_issue(workspace, created["id"])
    assert reread["title"] == "Updated"


def test_delete_issue(workspace):
    from data import create_issue, delete_issue, get_issue

    created = create_issue(workspace, {
        "title": "Delete me", "description": "", "status": "open",
        "priority": "low", "labels": [], "projectId": None,
        "cycle": None, "personas": [], "files": [], "blockedBy": [],
        "reviews": {}, "userVote": {"verdict": None, "notes": ""},
    })
    delete_issue(workspace, created["id"])
    assert get_issue(workspace, created["id"]) is None
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v -k "list_issues or get_issue or update_issue or delete_issue"`
Expected: FAIL — functions not importable

- [ ] **Step 11: Implement list_issues, get_issue, update_issue, delete_issue**

Add to `data.py`:

```python
def list_issues(workspace: Path) -> tuple[list[dict], list[str]]:
    """List all issues in a workspace, sorted by ID. Returns (issues, warnings)."""
    issues_dir = _tracker_path(workspace) / "issues"
    _ensure_dir(issues_dir)
    issues = []
    warnings = []
    for f in sorted(issues_dir.glob("*.json")):
        try:
            issues.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, KeyError) as e:
            warnings.append(f"Failed to load {f.name}: {e}")
    return issues, warnings


def get_issue(workspace: Path, issue_id: int) -> dict | None:
    """Get a single issue by ID, or None if not found."""
    path = _issue_path(workspace, issue_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def update_issue(workspace: Path, issue_id: int, updates: dict) -> dict | None:
    """Update an issue. Returns updated issue or None if not found."""
    issue = get_issue(workspace, issue_id)
    if issue is None:
        return None
    issue.update(updates)
    issue["updatedAt"] = _now_iso()
    _atomic_write(_issue_path(workspace, issue_id), issue)
    return issue


def delete_issue(workspace: Path, issue_id: int) -> bool:
    """Delete an issue and its assets. Cleans up blockedBy references. Returns True if deleted."""
    path = _issue_path(workspace, issue_id)
    if not path.exists():
        return False
    path.unlink()

    # Remove assets folder
    assets_dir = _tracker_path(workspace) / "assets" / f"{issue_id:03d}"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)

    # Clean up blockedBy references in other issues
    for issue in list_issues(workspace)[0]:
        if issue_id in issue.get("blockedBy", []):
            issue["blockedBy"].remove(issue_id)
            _atomic_write(_issue_path(workspace, issue["id"]), issue)

    return True


def _ensure_dir(path: Path) -> None:
    """Auto-recreate missing subdirectories."""
    path.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v`
Expected: All PASS

- [ ] **Step 13: Write failing tests — circular dependency prevention**

Add to `tests/test_data.py`:

```python
def test_circular_dependency_rejected(workspace):
    from data import create_issue, update_issue, CircularDependencyError

    issue_data = {
        "title": "", "description": "", "status": "open",
        "priority": "medium", "labels": [], "projectId": None,
        "cycle": None, "personas": [], "files": [],
        "blockedBy": [], "reviews": {},
        "userVote": {"verdict": None, "notes": ""},
    }
    a = create_issue(workspace, {**issue_data, "title": "A"})
    b = create_issue(workspace, {**issue_data, "title": "B", "blockedBy": [a["id"]]})

    with pytest.raises(CircularDependencyError):
        update_issue(workspace, a["id"], {"blockedBy": [b["id"]]})


def test_orphaned_dependency_cleanup(workspace):
    from data import create_issue, delete_issue, get_issue

    issue_data = {
        "title": "", "description": "", "status": "open",
        "priority": "medium", "labels": [], "projectId": None,
        "cycle": None, "personas": [], "files": [],
        "blockedBy": [], "reviews": {},
        "userVote": {"verdict": None, "notes": ""},
    }
    a = create_issue(workspace, {**issue_data, "title": "Blocker"})
    b = create_issue(workspace, {**issue_data, "title": "Blocked", "blockedBy": [a["id"]]})

    delete_issue(workspace, a["id"])
    updated_b = get_issue(workspace, b["id"])
    assert a["id"] not in updated_b["blockedBy"]
```

- [ ] **Step 14: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v -k "circular or orphaned"`
Expected: FAIL — circular dependency test fails (no validation yet)

- [ ] **Step 15: Implement circular dependency detection**

Add to `data.py`:

```python
class CircularDependencyError(Exception):
    pass


def _has_cycle(workspace: Path, issue_id: int, blocked_by: list[int]) -> bool:
    """Check if adding blocked_by to issue_id would create a cycle."""
    visited = set()

    def dfs(current_id: int) -> bool:
        if current_id == issue_id:
            return True
        if current_id in visited:
            return False
        visited.add(current_id)
        current = get_issue(workspace, current_id)
        if current is None:
            return False
        for dep_id in current.get("blockedBy", []):
            if dfs(dep_id):
                return True
        return False

    for dep_id in blocked_by:
        if dep_id == issue_id:
            return True
        if dfs(dep_id):
            return True
    return False
```

**Replace** the `update_issue` function from Step 11 with this version that includes cycle detection:

```python
def update_issue(workspace: Path, issue_id: int, updates: dict) -> dict | None:
    """Update an issue. Returns updated issue, None if not found. Raises CircularDependencyError."""
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
```

- [ ] **Step 16: Run all tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v`
Expected: All PASS

- [ ] **Step 17: Write failing tests — project CRUD**

Add to `tests/test_data.py`:

```python
def test_create_project(workspace):
    from data import create_project, read_config

    project = create_project(workspace, {
        "name": "Phase 1",
        "description": "First phase",
        "status": "active",
    })
    assert project["id"] == 1
    assert project["name"] == "Phase 1"
    assert "createdAt" in project

    config = read_config(workspace)
    assert config["nextProjectId"] == 2

    project_file = workspace / ".issuetracker" / "projects" / "001.json"
    assert project_file.exists()


def test_list_projects(workspace):
    from data import create_project, list_projects

    create_project(workspace, {"name": "A", "description": "", "status": "active"})
    create_project(workspace, {"name": "B", "description": "", "status": "active"})
    projects = list_projects(workspace)
    assert len(projects) == 2


def test_update_project(workspace):
    from data import create_project, update_project

    p = create_project(workspace, {"name": "Old", "description": "", "status": "active"})
    updated = update_project(workspace, p["id"], {"name": "New"})
    assert updated["name"] == "New"


def test_delete_project(workspace):
    from data import create_project, delete_project, get_project

    p = create_project(workspace, {"name": "Gone", "description": "", "status": "active"})
    delete_project(workspace, p["id"])
    assert get_project(workspace, p["id"]) is None
```

- [ ] **Step 18: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v -k "project"`
Expected: FAIL — functions not importable

- [ ] **Step 19: Implement project CRUD**

Add to `data.py`:

```python
def _project_path(workspace: Path, project_id: int) -> Path:
    return _tracker_path(workspace) / "projects" / f"{project_id:03d}.json"


def create_project(workspace: Path, data: dict) -> dict:
    """Create a new project. Auto-assigns ID from config."""
    _ensure_dir(_tracker_path(workspace) / "projects")
    config = read_config(workspace)
    project_id = config["nextProjectId"]
    config["nextProjectId"] = project_id + 1
    write_config(workspace, config)

    project = {
        "id": project_id,
        **data,
        "createdAt": _now_iso(),
    }
    _atomic_write(_project_path(workspace, project_id), project)
    return project


def list_projects(workspace: Path) -> list[dict]:
    """List all projects in a workspace, sorted by ID."""
    projects_dir = _tracker_path(workspace) / "projects"
    _ensure_dir(projects_dir)
    projects = []
    for f in sorted(projects_dir.glob("*.json")):
        try:
            projects.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, KeyError):
            pass
    return projects


def get_project(workspace: Path, project_id: int) -> dict | None:
    """Get a single project by ID, or None if not found."""
    path = _project_path(workspace, project_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def update_project(workspace: Path, project_id: int, updates: dict) -> dict | None:
    """Update a project. Returns updated project or None if not found."""
    project = get_project(workspace, project_id)
    if project is None:
        return None
    project.update(updates)
    _atomic_write(_project_path(workspace, project_id), project)
    return project


def delete_project(workspace: Path, project_id: int) -> bool:
    """Delete a project. Returns True if deleted."""
    path = _project_path(workspace, project_id)
    if not path.exists():
        return False
    path.unlink()
    return True
```

- [ ] **Step 20: Run all tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v`
Expected: All PASS

- [ ] **Step 21: Write failing test — workspace initialization**

Add to `tests/test_data.py`:

```python
def test_init_workspace(tmp_path):
    from data import init_workspace, read_config

    project_dir = tmp_path / "my-project"
    project_dir.mkdir()

    init_workspace(project_dir, "My Project")

    config = read_config(project_dir)
    assert config["name"] == "My Project"
    assert config["nextIssueId"] == 1
    assert (project_dir / ".issuetracker" / "issues").is_dir()
    assert (project_dir / ".issuetracker" / "projects").is_dir()
    assert (project_dir / ".issuetracker" / "assets").is_dir()


def test_list_workspaces(tmp_path):
    from data import init_workspace, list_workspaces

    (tmp_path / "project-a").mkdir()
    (tmp_path / "project-b").mkdir()
    init_workspace(tmp_path / "project-a", "Project A")
    # project-b has no .issuetracker

    workspaces = list_workspaces(tmp_path)
    names = {w["name"] for w in workspaces}
    assert "project-a" in names
    assert "project-b" in names

    ws_a = next(w for w in workspaces if w["name"] == "project-a")
    ws_b = next(w for w in workspaces if w["name"] == "project-b")
    assert ws_a["hasTracker"] is True
    assert ws_b["hasTracker"] is False
```

- [ ] **Step 22: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v -k "init_workspace or list_workspaces"`
Expected: FAIL

- [ ] **Step 23: Implement init_workspace and list_workspaces**

Add to `data.py`:

```python
def init_workspace(workspace: Path, name: str) -> dict:
    """Initialize a .issuetracker scaffold in a workspace directory."""
    tracker = _tracker_path(workspace)
    tracker.mkdir(exist_ok=True)
    (tracker / "issues").mkdir(exist_ok=True)
    (tracker / "projects").mkdir(exist_ok=True)
    (tracker / "assets").mkdir(exist_ok=True)

    config = {
        "name": name,
        "nextIssueId": 1,
        "nextProjectId": 1,
        "reviewers": ["PM", "Dev Lead", "Security"],
    }
    _atomic_write(tracker / "config.json", config)
    return config


def list_workspaces(root_path: Path) -> list[dict]:
    """List all subdirectories in root_path with hasTracker boolean."""
    workspaces = []
    for entry in sorted(root_path.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            has_tracker = (entry / ".issuetracker" / "config.json").exists()
            workspaces.append({
                "name": entry.name,
                "hasTracker": has_tracker,
            })
    return workspaces
```

- [ ] **Step 24: Run all tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py -v`
Expected: All PASS

- [ ] **Step 25: Write failing test — malformed JSON handling**

Add to `tests/test_data.py`:

```python
def test_malformed_issue_skipped(workspace):
    from data import list_issues

    # Write a valid issue
    issue_file = workspace / ".issuetracker" / "issues" / "001.json"
    issue_file.write_text(json.dumps({"id": 1, "title": "Valid"}))

    # Write a malformed issue
    bad_file = workspace / ".issuetracker" / "issues" / "002.json"
    bad_file.write_text("{bad json")

    issues, warnings = list_issues(workspace)
    assert len(issues) == 1
    assert issues[0]["title"] == "Valid"
    assert len(warnings) == 1
    assert "002.json" in warnings[0]
```

- [ ] **Step 26: Run test to verify it passes (already handled in list_issues)**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_data.py::test_malformed_issue_skipped -v`
Expected: PASS (the try/except in list_issues already handles this)

- [ ] **Step 27: Commit**

```bash
git add data.py tests/
git commit -m "feat: data layer with full CRUD, dependency validation, and workspace management"
```

---

## Chunk 2: FastAPI Server

### Task 3: Server — configuration and workspace endpoints

**Files:**
- Create: `server.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing test — GET /api/config**

Create `tests/test_api.py`:

```python
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture
def root_dir(tmp_path):
    """Create a root directory with one initialized workspace."""
    project = tmp_path / "test-project"
    project.mkdir()
    tracker = project / ".issuetracker"
    tracker.mkdir()
    (tracker / "issues").mkdir()
    (tracker / "projects").mkdir()
    (tracker / "assets").mkdir()
    config = {
        "name": "Test Project",
        "nextIssueId": 1,
        "nextProjectId": 1,
        "reviewers": ["PM", "Dev Lead", "Security"],
    }
    (tracker / "config.json").write_text(json.dumps(config, indent=2))
    return tmp_path


@pytest.fixture
def client(root_dir):
    from server import create_app

    app = create_app(root_path=root_dir)
    return TestClient(app)


def test_get_config(client, root_dir):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["rootPath"] == str(root_dir)


def test_put_config(client, tmp_path):
    new_root = tmp_path / "other"
    new_root.mkdir()
    resp = client.put("/api/config", json={"rootPath": str(new_root)})
    assert resp.status_code == 200

    resp = client.get("/api/config")
    assert resp.json()["rootPath"] == str(new_root)


def test_put_config_invalid_path(client):
    resp = client.put("/api/config", json={"rootPath": "/nonexistent/path"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_api.py -v -k "config"`
Expected: FAIL — `cannot import name 'create_app' from 'server'`

- [ ] **Step 3: Implement server skeleton with config endpoints**

Create `server.py`:

```python
"""Issue Tracker — FastAPI server.

Serves the frontend and provides a REST API for managing
issues, projects, and workspaces via .issuetracker/ folders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import data


class ConfigUpdate(BaseModel):
    rootPath: str


def create_app(root_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Issue Tracker")

    # Mutable state for root path
    state = {"root_path": root_path or _default_root_path()}

    @app.get("/api/config")
    def get_config():
        return {"rootPath": str(state["root_path"])}

    @app.put("/api/config")
    def put_config(config: ConfigUpdate):
        path = Path(config.rootPath)
        if not path.is_dir():
            raise HTTPException(400, f"Path does not exist: {config.rootPath}")
        state["root_path"] = path
        return {"rootPath": str(path)}

    return app


def _default_root_path() -> Path:
    """Default root: one directory above this repo."""
    return Path(__file__).resolve().parent.parent


def _get_root_path() -> Path:
    """Read root path from config file or return default."""
    config_file = Path(__file__).resolve().parent / "tracker.config.json"
    if config_file.exists():
        config = json.loads(config_file.read_text())
        if config.get("rootPath"):
            return Path(config["rootPath"])
    return _default_root_path()


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Issue Tracker Server")
    parser.add_argument("--root", type=str, help="Root path for project directories")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    args = parser.parse_args()

    root = Path(args.root) if args.root else _get_root_path()
    if not root.is_dir():
        print(f"Error: root path does not exist: {root}")
        exit(1)

    app = create_app(root_path=root)
    uvicorn.run(app, host="127.0.0.1", port=args.port)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_api.py -v -k "config"`
Expected: All PASS

- [ ] **Step 5: Write failing tests — workspace endpoints**

Add to `tests/test_api.py`:

```python
def test_list_workspaces(client):
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200
    workspaces = resp.json()
    names = [w["name"] for w in workspaces]
    assert "test-project" in names


def test_init_workspace(client, root_dir):
    (root_dir / "new-project").mkdir()
    resp = client.post("/api/workspaces/new-project/init")
    assert resp.status_code == 200
    assert (root_dir / "new-project" / ".issuetracker" / "config.json").exists()


def test_init_workspace_not_found(client):
    resp = client.post("/api/workspaces/nonexistent/init")
    assert resp.status_code == 404
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_api.py -v -k "workspace"`
Expected: FAIL

- [ ] **Step 7: Implement workspace endpoints**

Add to `create_app` in `server.py`:

```python
    def _resolve_workspace(name: str) -> Path:
        ws = state["root_path"] / name
        if not ws.is_dir():
            raise HTTPException(404, f"Workspace not found: {name}")
        return ws

    def _require_tracker(workspace: Path) -> None:
        if not (workspace / ".issuetracker" / "config.json").exists():
            raise HTTPException(400, f"Workspace not initialized: {workspace.name}")

    @app.get("/api/workspaces")
    def list_workspaces():
        return data.list_workspaces(state["root_path"])

    @app.post("/api/workspaces/{name}/init")
    def init_workspace(name: str):
        ws = state["root_path"] / name
        if not ws.is_dir():
            raise HTTPException(404, f"Directory not found: {name}")
        config = data.init_workspace(ws, name)
        return config
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_api.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add server.py tests/test_api.py
git commit -m "feat: server skeleton with config and workspace endpoints"
```

---

### Task 4: Server — issue endpoints

**Files:**
- Modify: `server.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests — issue CRUD endpoints**

Add to `tests/test_api.py`:

```python
def _issue_payload(**overrides):
    base = {
        "title": "Test issue",
        "description": "A test",
        "status": "open",
        "priority": "high",
        "labels": ["bug"],
        "projectId": None,
        "cycle": None,
        "personas": [],
        "files": [],
        "blockedBy": [],
        "reviews": {},
        "userVote": {"verdict": None, "notes": ""},
    }
    base.update(overrides)
    return base


def test_create_issue(client):
    resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    assert resp.status_code == 200
    assert resp.json()["id"] == 1
    assert resp.json()["title"] == "Test issue"


def test_list_issues(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="A"))
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="B"))
    resp = client.get("/api/workspaces/test-project/issues")
    assert resp.status_code == 200
    assert len(resp.json()["issues"]) == 2
    assert resp.json()["warnings"] == []


def test_list_issues_filtered(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="A", status="open", priority="high"))
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="B", status="done", priority="low"))
    # Filter by status
    resp = client.get("/api/workspaces/test-project/issues?status=open")
    assert len(resp.json()["issues"]) == 1
    assert resp.json()["issues"][0]["title"] == "A"
    # Filter by priority
    resp = client.get("/api/workspaces/test-project/issues?priority=low")
    assert len(resp.json()["issues"]) == 1
    assert resp.json()["issues"][0]["title"] == "B"


def test_get_issue(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    resp = client.get("/api/workspaces/test-project/issues/1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test issue"


def test_get_issue_not_found(client):
    resp = client.get("/api/workspaces/test-project/issues/999")
    assert resp.status_code == 404


def test_update_issue(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    resp = client.put("/api/workspaces/test-project/issues/1", json={"title": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"


def test_delete_issue(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    resp = client.delete("/api/workspaces/test-project/issues/1")
    assert resp.status_code == 200
    resp = client.get("/api/workspaces/test-project/issues/1")
    assert resp.status_code == 404


def test_update_vote(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    resp = client.put("/api/workspaces/test-project/issues/1/vote", json={
        "verdict": "approve", "notes": "Looks good"
    })
    assert resp.status_code == 200
    issue = client.get("/api/workspaces/test-project/issues/1").json()
    assert issue["userVote"]["verdict"] == "approve"


def test_update_review(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    resp = client.put("/api/workspaces/test-project/issues/1/reviews", json={
        "reviewer": "PM", "verdict": "approve", "notes": "Ship it"
    })
    assert resp.status_code == 200
    issue = client.get("/api/workspaces/test-project/issues/1").json()
    assert issue["reviews"]["PM"]["verdict"] == "approve"
    assert issue["reviews"]["PM"]["notes"] == "Ship it"


def test_update_review_preserves_others(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    client.put("/api/workspaces/test-project/issues/1/reviews", json={
        "reviewer": "PM", "verdict": "approve", "notes": "Yes"
    })
    client.put("/api/workspaces/test-project/issues/1/reviews", json={
        "reviewer": "Dev Lead", "verdict": "defer", "notes": "Later"
    })
    issue = client.get("/api/workspaces/test-project/issues/1").json()
    assert issue["reviews"]["PM"]["verdict"] == "approve"
    assert issue["reviews"]["Dev Lead"]["verdict"] == "defer"


def test_circular_dependency_rejected(client):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="A"))
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="B", blockedBy=[1]))
    resp = client.put("/api/workspaces/test-project/issues/1", json={"blockedBy": [2]})
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_api.py -v -k "issue"`
Expected: FAIL — endpoints don't exist

- [ ] **Step 3: Implement issue endpoints**

Add to `create_app` in `server.py`:

```python
    @app.get("/api/workspaces/{name}/issues")
    def list_issues(
        name: str,
        status: str | None = None,
        priority: str | None = None,
        label: str | None = None,
        projectId: int | None = None,
    ):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issues, warnings = data.list_issues(ws)
        if status:
            issues = [i for i in issues if i.get("status") == status]
        if priority:
            issues = [i for i in issues if i.get("priority") == priority]
        if label:
            issues = [i for i in issues if label in i.get("labels", [])]
        if projectId is not None:
            issues = [i for i in issues if i.get("projectId") == projectId]
        return {"issues": issues, "warnings": warnings}

    @app.post("/api/workspaces/{name}/issues")
    def create_issue(name: str, issue_data: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        return data.create_issue(ws, issue_data)

    @app.get("/api/workspaces/{name}/issues/{issue_id}")
    def get_issue(name: str, issue_id: int):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issue = data.get_issue(ws, issue_id)
        if issue is None:
            raise HTTPException(404, f"Issue {issue_id} not found")
        return issue

    @app.put("/api/workspaces/{name}/issues/{issue_id}")
    def update_issue(name: str, issue_id: int, updates: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        try:
            issue = data.update_issue(ws, issue_id, updates)
        except data.CircularDependencyError as e:
            raise HTTPException(409, str(e))
        if issue is None:
            raise HTTPException(404, f"Issue {issue_id} not found")
        return issue

    @app.delete("/api/workspaces/{name}/issues/{issue_id}")
    def delete_issue(name: str, issue_id: int):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        if not data.delete_issue(ws, issue_id):
            raise HTTPException(404, f"Issue {issue_id} not found")
        return {"deleted": issue_id}

    @app.put("/api/workspaces/{name}/issues/{issue_id}/vote")
    def update_vote(name: str, issue_id: int, vote: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issue = data.update_issue(ws, issue_id, {"userVote": vote})
        if issue is None:
            raise HTTPException(404, f"Issue {issue_id} not found")
        return issue

    @app.put("/api/workspaces/{name}/issues/{issue_id}/reviews")
    def update_review(name: str, issue_id: int, review: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issue = data.get_issue(ws, issue_id)
        if issue is None:
            raise HTTPException(404, f"Issue {issue_id} not found")
        reviews = issue.get("reviews", {})
        reviewer_name = review["reviewer"]
        reviews[reviewer_name] = {
            "verdict": review["verdict"],
            "notes": review.get("notes", ""),
        }
        return data.update_issue(ws, issue_id, {"reviews": reviews})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_api.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_api.py
git commit -m "feat: issue CRUD endpoints with vote, review, and dependency validation"
```

---

### Task 5: Server — project endpoints and static file serving

**Files:**
- Modify: `server.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests — project endpoints**

Add to `tests/test_api.py`:

```python
def test_create_project(client):
    resp = client.post("/api/workspaces/test-project/projects", json={
        "name": "Phase 1", "description": "First phase", "status": "active"
    })
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_list_projects(client):
    client.post("/api/workspaces/test-project/projects", json={
        "name": "A", "description": "", "status": "active"
    })
    resp = client.get("/api/workspaces/test-project/projects")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_project(client):
    client.post("/api/workspaces/test-project/projects", json={
        "name": "Old", "description": "", "status": "active"
    })
    resp = client.put("/api/workspaces/test-project/projects/1", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_delete_project(client):
    client.post("/api/workspaces/test-project/projects", json={
        "name": "Gone", "description": "", "status": "active"
    })
    resp = client.delete("/api/workspaces/test-project/projects/1")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/test_api.py -v -k "project"`
Expected: FAIL

- [ ] **Step 3: Implement project endpoints and static serving**

Add to `create_app` in `server.py`:

```python
    @app.get("/api/workspaces/{name}/projects")
    def list_projects(name: str):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        return data.list_projects(ws)

    @app.post("/api/workspaces/{name}/projects")
    def create_project(name: str, project_data: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        return data.create_project(ws, project_data)

    @app.put("/api/workspaces/{name}/projects/{project_id}")
    def update_project(name: str, project_id: int, updates: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        project = data.update_project(ws, project_id, updates)
        if project is None:
            raise HTTPException(404, f"Project {project_id} not found")
        return project

    @app.delete("/api/workspaces/{name}/projects/{project_id}")
    def delete_project(name: str, project_id: int):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        if not data.delete_project(ws, project_id):
            raise HTTPException(404, f"Project {project_id} not found")
        return {"deleted": project_id}

    @app.get("/")
    def serve_frontend():
        index = Path(__file__).resolve().parent / "index.html"
        if not index.exists():
            return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
        return FileResponse(index)
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_api.py
git commit -m "feat: project endpoints and static file serving"
```

---

## Chunk 3: Frontend

### Task 6: Frontend — HTML structure, CSS, and workspace selection

**Files:**
- Create: `index.html`

This is a single HTML file with embedded CSS and JS. Due to the size, we build it incrementally. **JS code organization:** group code into clearly commented sections using the pattern `// ─── Section Name ───` (matching the existing UX tracker style). Sections: State & Config, API Helpers, Workspace Logic, Table Logic, Filter Logic, Modal Logic, Stats Logic, Quick Wins Logic, Error Handling, Init.

- [ ] **Step 1: Create index.html with HTML skeleton and CSS theme**

Create `index.html` with the `<!DOCTYPE html>`, `<head>`, and full `<style>` block. CSS variables and design language must match the existing UX tracker:
- `--bg: #0d1117`, `--bg-surface: #161b22`, `--bg-elevated: #1f2937`, `--bg-hover: #21262d`
- `--border: #30363d`, `--text: #e6edf3`, `--text-muted: #8b949e`, `--accent: #58a6ff`
- `--green: #3fb950`, `--amber: #d29922`, `--red: #f85149`, `--gray: #6e7681`
- Monospace font: `'SF Mono', 'Fira Code', 'Cascadia Code', monospace`

Include CSS for: header, stats grid, filters, toggle buttons, table, badges, expand rows, modals, quick wins, error banners. Add the HTML `<body>` with empty container divs for each section (header, stats, filters, table, quick wins).

- [ ] **Step 2: Add header bar with workspace dropdown**

Add the header HTML with logo ("Issue Tracker"), workspace `<select>` dropdown, and settings gear icon. Add JS to:
- Fetch `GET /api/workspaces` on page load and populate the dropdown
- Show a green dot indicator next to workspaces that have `hasTracker: true`
- On workspace select: if `hasTracker` is true, fetch issues/projects; if false, show "Initialize Tracker" button that calls `POST /api/workspaces/{name}/init`

- [ ] **Step 3: Add stats bar and filters bar**

Add stats bar HTML with 6 stat cards (Total, Open, In Progress, Done, Blocked, High Priority). Add `renderStats()` function that counts from the loaded issues array.

Add filters bar with:
- Status toggle buttons (All / Open / In Progress / Done / Closed) — multi-select
- Priority toggle buttons (All / High / Medium / Low) — multi-select
- Project dropdown (populated from loaded projects)
- Label filter dropdown (dynamically populated from all issue labels, multi-select)
- Search input
- "Hide voted" checkbox

Multi-select behavior: clicking a toggle turns it on/off independently. "All" resets to showing everything. Active filters stored as Sets in JS state.

- [ ] **Step 4: Verify workspace selection and layout**

Run: `cd /Users/justinmalone/projects/issuetracker && source .venv/bin/activate && python server.py`
Open: `http://127.0.0.1:8000`
Verify: Workspace dropdown lists projects, selecting one loads or shows init prompt. Stats and filters render with correct layout.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: frontend shell with workspace selector, stats, and filters"
```

---

### Task 7: Frontend — issues table with expandable rows

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Add basic issues table rendering**

Add the `<table>` HTML with `<thead>` columns: ID, Priority, Status, Project, Labels, Issue title. Add a `renderTable()` function that reads the loaded issues array and renders `<tbody>` rows. Each row shows badge-styled priority and status, label chips, and the issue title. Wire up `renderTable()` to be called after workspace data loads.

- [ ] **Step 2: Add expandable row detail**

Make each row clickable to expand/collapse a detail panel below it. The expanded row shows:
- Reviewer verdict cards — dynamically rendered from the workspace config's `reviewers` array (fetch from `.issuetracker/config.json` via the API). Each card shows reviewer name, verdict badge (approve/defer/block), and notes.
- Your Vote card with Approve/Defer/Reject buttons and notes textarea. Vote buttons call `PUT /api/workspaces/{name}/issues/{id}/vote`.
- Linked files as clickable chips
- Blocked-by section — blocking issue IDs shown as badges (red if the blocker's status is not `done`/`closed`, green if resolved)
- Cycle and meta info (createdAt, updatedAt)

- [ ] **Step 3: Add multi-select filter logic**

Wire the filter toggles from Task 6 to actually filter the table. `getFiltered()` function applies all active filters (status Set, priority Set, project, labels, search term, hide-voted checkbox) and returns matching issues. `renderTable()` calls `getFiltered()` instead of using the raw issues array.

- [ ] **Step 4: Add sortable columns**

Add click handlers to `<th>` elements with `data-col` attributes. Clicking toggles asc/desc. `getFiltered()` applies sort after filtering. Sort indicators (↑/↓) shown on active column header.

- [ ] **Step 5: Add search filtering**

Wire the search input to filter issues where title or description contains the search term (case-insensitive). Debounce input by 150ms to avoid excessive re-renders.

- [ ] **Step 6: Verify table rendering and filtering**

Run server, then create test issues:
```bash
curl -X POST http://127.0.0.1:8000/api/workspaces/issuetracker/issues \
  -H "Content-Type: application/json" \
  -d '{"title":"Test high priority bug","description":"Something broken","status":"open","priority":"high","labels":["bug"],"projectId":null,"cycle":1,"personas":[],"files":["server.py"],"blockedBy":[],"reviews":{},"userVote":{"verdict":null,"notes":""}}'

curl -X POST http://127.0.0.1:8000/api/workspaces/issuetracker/issues \
  -H "Content-Type: application/json" \
  -d '{"title":"Low priority enhancement","description":"Nice to have","status":"open","priority":"low","labels":["enhancement"],"projectId":null,"cycle":1,"personas":[],"files":[],"blockedBy":[1],"reviews":{},"userVote":{"verdict":null,"notes":""}}'
```

Open `http://127.0.0.1:8000` and verify:
- Issues appear in the table with correct badges
- Expanding a row shows reviewer cards and vote buttons
- Multi-select filters work (can select both High and Medium, excluding Low)
- Sorting works on all columns
- Search filters by title/description
- Blocked-by badge shows red (blocker is still open)

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "feat: issues table with expandable rows, multi-select filters, and sorting"
```

---

### Task 8: Frontend — CRUD modals

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Add issue create/edit modal**

Add modal with fields: title, description (textarea), status (dropdown), priority (dropdown), project (dropdown populated from API), labels (tag input — type and press Enter to add), cycle (number input), personas (tag input), files (tag input), blockedBy (searchable multi-select showing other issues by ID and title), reviewer verdicts (one section per reviewer from config).

The modal is used for both create (empty fields) and edit (pre-filled). On submit, it calls POST or PUT to the appropriate endpoint.

- [ ] **Step 2: Add project create/edit modal**

Simpler modal: name, description, status (dropdown: active/completed/archived).

- [ ] **Step 3: Add delete confirmation dialog**

"Are you sure?" dialog with issue/project title shown. On confirm, calls DELETE endpoint.

- [ ] **Step 4: Add "New Issue" and "New Project" buttons to the header area**

- [ ] **Step 5: Add edit and delete buttons to each table row**

Edit button (pencil icon) opens pre-filled modal. Delete button (trash icon) opens confirmation.

- [ ] **Step 6: Verify CRUD flow**

Run server, verify:
- Create a new issue via modal → appears in table
- Edit an issue → changes reflected
- Delete an issue → removed from table
- Create/edit/delete projects via modals
- blockedBy multi-select works correctly

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "feat: CRUD modals for issues and projects"
```

---

### Task 9: Frontend — Quick Wins, settings, and error banners

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Add Quick Wins section**

Below the main table, render a "Quick Wins" section showing issues where all reviewers have verdict `approve` and priority is `high` or `medium`. Display as cards with ID, title, priority badge, and category.

- [ ] **Step 2: Add settings modal**

Gear icon in header opens a modal to view/change the root path. Calls `PUT /api/config` on save.

- [ ] **Step 3: Add error banners with recovery prompts**

When the API returns warnings (malformed issues) or errors (missing config, etc.), display a banner at the top of the page with:
- Error message
- One or more "Copy prompt" buttons that copy pre-built Claude recovery prompts to clipboard
- Dismiss button

Implement these specific recovery prompt scenarios (from the spec):

1. **Malformed issue JSON** (triggered when `warnings` array in list response is non-empty):
   - "Fix the malformed JSON in `{workspace}/.issuetracker/issues/{id}.json` — here is the current content: `{raw}`. Repair it to match the issue schema"
   - "Delete `{workspace}/.issuetracker/issues/{id}.json` and clean up any references to issue #{id} in other issues' `blockedBy` arrays"

2. **Missing subdirectory** (triggered when server auto-recreates a dir):
   - "Recreate the missing `{dir}` directory in `{workspace}/.issuetracker/` and regenerate any folders referenced by existing issues"
   - "Clean up all references in `{workspace}/.issuetracker/issues/*.json` that point to the missing `{dir}` directory"

3. **Missing config.json** (triggered when workspace init fails or config is corrupt):
   - "Rebuild `{workspace}/.issuetracker/config.json` by scanning existing `issues/` and `projects/` folders to determine correct `nextIssueId`, `nextProjectId`, and reviewer list"

4. **Corrupt or missing project file** (triggered when a projectId references a missing project):
   - "Recreate `{workspace}/.issuetracker/projects/{id}.json` based on issues that reference projectId {id}"
   - "Reassign all issues referencing projectId {id} to a different project or remove their project association"

5. **Root path does not exist** (triggered when GET /api/config returns an invalid path):
   - "The configured projects root `{path}` does not exist. Update the root path in Issue Tracker settings or create the directory"

Each prompt button uses `navigator.clipboard.writeText()` to copy. The `{workspace}`, `{id}`, `{dir}`, `{path}`, and `{raw}` placeholders are filled with actual values from the error context.

- [ ] **Step 4: Verify Quick Wins, settings, and error handling**

Run server, verify:
- Quick Wins shows correct issues
- Settings modal updates root path
- Error banner appears for malformed data

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: quick wins section, settings modal, and error recovery banners"
```

---

## Chunk 4: Claude Skill & Polish

### Task 10: Claude Code skill

**Files:**
- Create: `skill/issuetracker.md`

- [ ] **Step 1: Write the skill definition**

Create `skill/issuetracker.md` — a Claude Code skill that:
- Detects `.issuetracker/` in the current working directory
- Provides instructions for full CRUD on issues and projects by reading/writing JSON files directly
- Includes the data schema for issues and projects (with all field types and allowed values)
- Includes instructions for ID management (read config.json, increment, write back)
- Includes instructions for **atomic writes** (write to temp file in same directory, then `os.replace()` to target — prevents corruption on interruption)
- Includes instructions for dependency validation (check for cycles before adding blockedBy)
- Includes instructions for cleanup on delete (remove blockedBy references, remove assets folder)
- Includes the Quick Wins heuristic (all reviewers approved + priority high or medium)
- Documents example interactions

- [ ] **Step 2: Commit**

```bash
git add skill/
git commit -m "feat: Claude Code skill for direct .issuetracker file interaction"
```

---

### Task 11: Data migration — import existing UX tracker data

**Files:**
- Create: `scripts/import_ux_tracker.py`

- [ ] **Step 1: Write import script**

Create a Python script that reads the embedded JavaScript data from `frontend/public/ux-tracker.html` in the Jware-Trader-X repo and converts each issue into the `.issuetracker/issues/{id}.json` format. Maps fields:
- `id` → `id`
- `issue` → `title`
- `severity` → `priority` (HIGH→high, MEDIUM→medium, LOW→low)
- `status` → `status` (IMPLEMENTED→done, DEFERRED→open, REJECTED→closed)
- `category` → `labels` (as single-item array)
- `cycle` → `cycle`
- `personas` → `personas`
- `files` → `files`
- `pm`/`pmNotes` → `reviews.PM`
- `dev`/`devNotes` → `reviews.Dev Lead`
- `security`/`secNotes` → `reviews.Security`

**Unmapped fields — set defaults:**
- `blockedBy` → `[]`
- `userVote` → `{"verdict": null, "notes": ""}` (the UX tracker stores user votes in localStorage, not in the HTML data — they cannot be imported)
- `description` → `""` (the UX tracker has no separate description field)

**Parsing approach:** The script extracts the `const issues = [...]` JavaScript array from within the `<script>` tag using regex, then parses it as JSON (after minor cleanup like converting single quotes, removing trailing commas). If parsing fails, print a clear error with the line that failed.

Usage: `python scripts/import_ux_tracker.py /path/to/ux-tracker.html /path/to/project`

- [ ] **Step 2: Run the import on Jware-Trader-X**

Run: `cd /Users/justinmalone/projects/issuetracker && python scripts/import_ux_tracker.py /Users/justinmalone/projects/Jware-Trader-X/frontend/public/ux-tracker.html /Users/justinmalone/projects/Jware-Trader-X`
Verify: `.issuetracker/` folder created in Jware-Trader-X with all issues imported.

- [ ] **Step 3: Commit import script**

```bash
git add scripts/
git commit -m "feat: import script for existing UX tracker data"
```

---

### Task 12: Final integration test and self-tracking setup

**Files:**
- Modify: `.issuetracker/` (add initial issues for the tracker itself)

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/justinmalone/projects/issuetracker && python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 2: Start server and verify end-to-end**

Run: `cd /Users/justinmalone/projects/issuetracker && python server.py`
Open: `http://127.0.0.1:8000`
Verify:
- Workspace dropdown shows projects
- Selecting `issuetracker` shows its own tracker
- Can create, edit, delete issues and projects
- Filters, sorting, search all work
- Quick Wins section renders correctly
- Expandable rows show reviewer cards and voting
- Settings modal changes root path
- Error banners appear for bad data

- [ ] **Step 3: Verify imported Jware-Trader-X data**

In the browser, select the `Jware-Trader-X` workspace from the dropdown. Verify:
- All imported issues appear in the table with correct titles, priorities, and statuses
- Reviewer verdicts (PM, Dev Lead, Security) display correctly in expanded rows
- Labels, personas, files, and cycle data are present
- Filtering by status/priority works on imported data

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: final integration verification"
```
