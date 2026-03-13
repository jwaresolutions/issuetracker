"""Tests for the FastAPI server (server.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path

# Ensure project root is on sys.path so we can import server and data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data as data_module
from server import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue_payload(**overrides) -> dict:
    base = {
        "title": "Test issue",
        "description": "A test issue description",
        "status": "open",
        "priority": "medium",
        "labels": [],
        "blockedBy": [],
        "projectId": None,
        "userVote": None,
        "reviews": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Create a temp root with one initialized workspace called 'test-project'."""
    ws_dir = tmp_path / "test-project"
    ws_dir.mkdir()
    data_module.init_workspace(ws_dir, "test-project")
    return tmp_path


@pytest.fixture()
def client(tmp_root: Path) -> TestClient:
    app = create_app(root_path=tmp_root)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_get_config(client: TestClient, tmp_root: Path):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["rootPath"] == str(tmp_root)


def test_put_config(client: TestClient, tmp_path: Path):
    new_root = tmp_path / "new_root"
    new_root.mkdir()
    resp = client.put("/api/config", json={"rootPath": str(new_root)})
    assert resp.status_code == 200
    assert resp.json()["rootPath"] == str(new_root)


def test_put_config_invalid_path(client: TestClient):
    resp = client.put("/api/config", json={"rootPath": "/nonexistent/path/that/does/not/exist"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

def test_list_workspaces(client: TestClient):
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200
    names = [w["name"] for w in resp.json()]
    assert "test-project" in names


def test_init_workspace(client: TestClient, tmp_root: Path):
    new_ws = tmp_root / "new-workspace"
    new_ws.mkdir()
    resp = client.post("/api/workspaces/new-workspace/init")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "new-workspace"
    assert (new_ws / ".issuetracker" / "config.json").exists()


def test_init_workspace_not_found(client: TestClient):
    resp = client.post("/api/workspaces/does-not-exist/init")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

def test_create_issue(client: TestClient):
    resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["title"] == "Test issue"


def test_list_issues(client: TestClient):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    resp = client.get("/api/workspaces/test-project/issues")
    assert resp.status_code == 200
    body = resp.json()
    assert "issues" in body
    assert "warnings" in body
    assert len(body["issues"]) == 1
    assert body["warnings"] == []


def test_list_issues_filtered(client: TestClient):
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(status="open", priority="high"))
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(status="closed", priority="low"))
    client.post("/api/workspaces/test-project/issues", json=_issue_payload(status="open", priority="low"))

    resp = client.get("/api/workspaces/test-project/issues?status=open")
    assert resp.status_code == 200
    issues = resp.json()["issues"]
    assert all(i["status"] == "open" for i in issues)
    assert len(issues) == 2

    resp = client.get("/api/workspaces/test-project/issues?priority=high")
    assert resp.status_code == 200
    issues = resp.json()["issues"]
    assert all(i["priority"] == "high" for i in issues)
    assert len(issues) == 1

    resp = client.get("/api/workspaces/test-project/issues?status=open&priority=low")
    assert resp.status_code == 200
    issues = resp.json()["issues"]
    assert len(issues) == 1
    assert issues[0]["status"] == "open"
    assert issues[0]["priority"] == "low"


def test_get_issue(client: TestClient):
    create_resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    issue_id = create_resp.json()["id"]

    resp = client.get(f"/api/workspaces/test-project/issues/{issue_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == issue_id


def test_get_issue_not_found(client: TestClient):
    resp = client.get("/api/workspaces/test-project/issues/9999")
    assert resp.status_code == 404


def test_update_issue(client: TestClient):
    create_resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    issue_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/workspaces/test-project/issues/{issue_id}",
        json={"status": "in-progress", "title": "Updated title"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in-progress"
    assert body["title"] == "Updated title"


def test_delete_issue(client: TestClient):
    create_resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    issue_id = create_resp.json()["id"]

    resp = client.delete(f"/api/workspaces/test-project/issues/{issue_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    get_resp = client.get(f"/api/workspaces/test-project/issues/{issue_id}")
    assert get_resp.status_code == 404


def test_update_vote(client: TestClient):
    create_resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    issue_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/workspaces/test-project/issues/{issue_id}/vote",
        json={"userVote": "up"},
    )
    assert resp.status_code == 200
    assert resp.json()["userVote"] == "up"


def test_update_review(client: TestClient):
    create_resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    issue_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/workspaces/test-project/issues/{issue_id}/reviews",
        json={"reviewer": "PM", "verdict": "approve", "notes": "Looks good"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "PM" in body["reviews"]
    assert body["reviews"]["PM"]["verdict"] == "approve"
    assert body["reviews"]["PM"]["notes"] == "Looks good"


def test_update_review_preserves_others(client: TestClient):
    create_resp = client.post("/api/workspaces/test-project/issues", json=_issue_payload())
    issue_id = create_resp.json()["id"]

    # Add PM review
    client.put(
        f"/api/workspaces/test-project/issues/{issue_id}/reviews",
        json={"reviewer": "PM", "verdict": "approve", "notes": "PM approved"},
    )

    # Add Dev Lead review
    resp = client.put(
        f"/api/workspaces/test-project/issues/{issue_id}/reviews",
        json={"reviewer": "Dev Lead", "verdict": "request_changes", "notes": "Needs refactor"},
    )
    assert resp.status_code == 200
    reviews = resp.json()["reviews"]

    # Both reviewers should be present
    assert "PM" in reviews
    assert reviews["PM"]["verdict"] == "approve"
    assert "Dev Lead" in reviews
    assert reviews["Dev Lead"]["verdict"] == "request_changes"


def test_circular_dependency_rejected(client: TestClient):
    r1 = client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="Issue A"))
    r2 = client.post("/api/workspaces/test-project/issues", json=_issue_payload(title="Issue B"))
    id1 = r1.json()["id"]
    id2 = r2.json()["id"]

    # Issue 2 blocked by Issue 1
    client.put(
        f"/api/workspaces/test-project/issues/{id2}",
        json={"blockedBy": [id1]},
    )

    # Now try to make Issue 1 blocked by Issue 2 — circular
    resp = client.put(
        f"/api/workspaces/test-project/issues/{id1}",
        json={"blockedBy": [id2]},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def test_create_project(client: TestClient):
    resp = client.post(
        "/api/workspaces/test-project/projects",
        json={"name": "Alpha", "description": "First project"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["name"] == "Alpha"


def test_list_projects(client: TestClient):
    client.post(
        "/api/workspaces/test-project/projects",
        json={"name": "Alpha"},
    )
    resp = client.get("/api/workspaces/test-project/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert "projects" in body
    assert len(body["projects"]) == 1


def test_update_project(client: TestClient):
    create_resp = client.post(
        "/api/workspaces/test-project/projects",
        json={"name": "Alpha"},
    )
    project_id = create_resp.json()["id"]

    resp = client.put(
        f"/api/workspaces/test-project/projects/{project_id}",
        json={"name": "Alpha Updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alpha Updated"


def test_delete_project(client: TestClient):
    create_resp = client.post(
        "/api/workspaces/test-project/projects",
        json={"name": "Alpha"},
    )
    project_id = create_resp.json()["id"]

    resp = client.delete(f"/api/workspaces/test-project/projects/{project_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify it's gone — list should be empty
    list_resp = client.get("/api/workspaces/test-project/projects")
    assert list_resp.json()["projects"] == []
