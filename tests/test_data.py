import json
import os
import tempfile
from pathlib import Path

import pytest

from data import (
    CircularDependencyError,
    create_issue,
    create_project,
    delete_issue,
    delete_project,
    get_issue,
    get_project,
    init_workspace,
    list_issues,
    list_projects,
    list_workspaces,
    read_config,
    update_issue,
    update_project,
    write_config,
)


@pytest.fixture
def workspace(tmp_path):
    """Create a temp dir with a minimal .issuetracker/ scaffold."""
    tracker = tmp_path / ".issuetracker"
    tracker.mkdir()
    (tracker / "issues").mkdir()
    (tracker / "projects").mkdir()
    (tracker / "assets").mkdir()
    config = {
        "name": "test-workspace",
        "nextIssueId": 1,
        "nextProjectId": 1,
    }
    (tracker / "config.json").write_text(json.dumps(config))
    return tmp_path


def test_read_config(workspace):
    config = read_config(workspace)
    assert config["name"] == "test-workspace"
    assert config["nextIssueId"] == 1


def test_create_issue(workspace):
    issue = create_issue(workspace, {"title": "First issue", "status": "open"})
    assert issue["id"] == "001"
    assert issue["title"] == "First issue"
    issue_file = workspace / ".issuetracker" / "issues" / "001.json"
    assert issue_file.exists()
    config = read_config(workspace)
    assert config["nextIssueId"] == 2


def test_list_issues(workspace):
    create_issue(workspace, {"title": "Issue A", "status": "open"})
    create_issue(workspace, {"title": "Issue B", "status": "open"})
    issues, warnings = list_issues(workspace)
    assert len(issues) == 2
    assert warnings == []
    ids = [i["id"] for i in issues]
    assert "001" in ids
    assert "002" in ids


def test_get_issue(workspace):
    create_issue(workspace, {"title": "Get me", "status": "open"})
    issue = get_issue(workspace, "001")
    assert issue is not None
    assert issue["title"] == "Get me"


def test_get_issue_not_found(workspace):
    result = get_issue(workspace, "999")
    assert result is None


def test_update_issue(workspace):
    create_issue(workspace, {"title": "Old title", "status": "open"})
    updated = update_issue(workspace, "001", {"title": "New title", "status": "closed"})
    assert updated["title"] == "New title"
    assert updated["status"] == "closed"
    re_read = get_issue(workspace, "001")
    assert re_read["title"] == "New title"
    assert re_read["status"] == "closed"


def test_delete_issue(workspace):
    create_issue(workspace, {"title": "To delete", "status": "open"})
    assert get_issue(workspace, "001") is not None
    delete_issue(workspace, "001")
    assert get_issue(workspace, "001") is None


def test_circular_dependency_rejected(workspace):
    a = create_issue(workspace, {"title": "Issue A", "status": "open"})
    b = create_issue(workspace, {"title": "Issue B", "status": "open", "blockedBy": [a["id"]]})
    with pytest.raises(CircularDependencyError):
        update_issue(workspace, a["id"], {"blockedBy": [b["id"]]})


def test_orphaned_dependency_cleanup(workspace):
    a = create_issue(workspace, {"title": "Issue A", "status": "open"})
    b = create_issue(workspace, {"title": "Issue B", "status": "open", "blockedBy": [a["id"]]})
    delete_issue(workspace, a["id"])
    b_after = get_issue(workspace, b["id"])
    assert a["id"] not in b_after.get("blockedBy", [])


def test_create_project(workspace):
    project = create_project(workspace, {"name": "Project Alpha", "status": "active"})
    assert project["id"] == "001"
    assert project["name"] == "Project Alpha"
    project_file = workspace / ".issuetracker" / "projects" / "001.json"
    assert project_file.exists()
    config = read_config(workspace)
    assert config["nextProjectId"] == 2


def test_list_projects(workspace):
    create_project(workspace, {"name": "P1", "status": "active"})
    create_project(workspace, {"name": "P2", "status": "active"})
    projects, warnings = list_projects(workspace)
    assert len(projects) == 2
    assert warnings == []


def test_update_project(workspace):
    create_project(workspace, {"name": "Old Name", "status": "active"})
    updated = update_project(workspace, "001", {"name": "New Name"})
    assert updated["name"] == "New Name"
    re_read = get_project(workspace, "001")
    assert re_read["name"] == "New Name"


def test_delete_project(workspace):
    create_project(workspace, {"name": "Temp Project", "status": "active"})
    assert get_project(workspace, "001") is not None
    delete_project(workspace, "001")
    assert get_project(workspace, "001") is None


def test_init_workspace(tmp_path):
    target = tmp_path / "new-ws"
    target.mkdir()
    init_workspace(target, "My Workspace")
    config = read_config(target)
    assert config["name"] == "My Workspace"
    assert config["nextIssueId"] == 1
    assert config["nextProjectId"] == 1
    assert (target / ".issuetracker" / "issues").exists()
    assert (target / ".issuetracker" / "projects").exists()
    assert (target / ".issuetracker" / "assets").exists()


def test_list_workspaces(tmp_path):
    ws1 = tmp_path / "workspace1"
    ws1.mkdir()
    init_workspace(ws1, "Workspace 1")

    ws2 = tmp_path / "workspace2"
    ws2.mkdir()
    # No tracker in ws2

    hidden = tmp_path / ".hidden"
    hidden.mkdir()

    result = list_workspaces(tmp_path)
    names = {r["name"] for r in result}
    assert "workspace1" in names
    assert "workspace2" in names
    assert ".hidden" not in names

    by_name = {r["name"]: r for r in result}
    assert by_name["workspace1"]["hasTracker"] is True
    assert by_name["workspace2"]["hasTracker"] is False


def test_malformed_issue_skipped(workspace):
    create_issue(workspace, {"title": "Valid issue", "status": "open"})
    malformed_path = workspace / ".issuetracker" / "issues" / "002.json"
    malformed_path.write_text("{ this is not valid json }")
    issues, warnings = list_issues(workspace)
    assert len(issues) == 1
    assert len(warnings) == 1
    assert "002.json" in warnings[0]
