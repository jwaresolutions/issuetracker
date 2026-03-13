"""Issue Tracker — FastAPI server.

Serves the frontend and provides a REST API for managing
issues, projects, and workspaces via .issuetracker/ folders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import data

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ConfigUpdate(BaseModel):
    rootPath: str


# ---------------------------------------------------------------------------
# Helpers outside create_app
# ---------------------------------------------------------------------------

def _default_root_path() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_root_path() -> Path:
    config_file = Path(__file__).resolve().parent / "tracker.config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                cfg = json.load(f)
            if "rootPath" in cfg:
                return Path(cfg["rootPath"])
        except (json.JSONDecodeError, OSError):
            pass
    return _default_root_path()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(root_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Issue Tracker")

    state: dict = {
        "root_path": root_path if root_path is not None else _get_root_path()
    }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_workspace(name: str) -> Path:
        ws = state["root_path"] / name
        if not ws.is_dir():
            raise HTTPException(status_code=404, detail=f"Workspace '{name}' not found")
        return ws

    def _require_tracker(workspace: Path) -> None:
        if not (workspace / ".issuetracker" / "config.json").exists():
            raise HTTPException(
                status_code=400,
                detail=f"Workspace '{workspace.name}' is not initialized (missing .issuetracker/config.json)",
            )

    # ------------------------------------------------------------------
    # Config endpoints
    # ------------------------------------------------------------------

    @app.get("/api/config")
    def get_config():
        return {"rootPath": str(state["root_path"])}

    @app.put("/api/config")
    def put_config(body: ConfigUpdate):
        new_path = Path(body.rootPath)
        if not new_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {body.rootPath}")
        state["root_path"] = new_path
        return {"rootPath": str(state["root_path"])}

    # ------------------------------------------------------------------
    # Workspace endpoints
    # ------------------------------------------------------------------

    @app.get("/api/workspaces")
    def list_workspaces():
        return data.list_workspaces(state["root_path"])

    @app.post("/api/workspaces/{name}/init")
    def init_workspace(name: str):
        ws = _resolve_workspace(name)
        config = data.init_workspace(ws, name)
        return config

    @app.get("/api/workspaces/{name}/config")
    def get_workspace_config(name: str):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        return data.read_config(ws)

    @app.put("/api/workspaces/{name}/config")
    def put_workspace_config(name: str, body: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        config = data.read_config(ws)
        config.update(body)
        data.write_config(ws, config)
        return config

    # ------------------------------------------------------------------
    # Issue endpoints
    # ------------------------------------------------------------------

    @app.get("/api/workspaces/{name}/issues")
    def list_issues(
        name: str,
        status: str | None = Query(default=None),
        priority: str | None = Query(default=None),
        label: str | None = Query(default=None),
        projectId: str | None = Query(default=None),
    ):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issues, warnings = data.list_issues(ws)

        if status is not None:
            issues = [i for i in issues if i.get("status") == status]
        if priority is not None:
            issues = [i for i in issues if i.get("priority") == priority]
        if label is not None:
            issues = [i for i in issues if label in i.get("labels", [])]
        if projectId is not None:
            issues = [i for i in issues if str(i.get("projectId", "")) == projectId]

        return {"issues": issues, "warnings": warnings}

    @app.post("/api/workspaces/{name}/issues")
    def create_issue(name: str, body: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issue = data.create_issue(ws, body)
        return issue

    @app.get("/api/workspaces/{name}/issues/{issue_id}")
    def get_issue(name: str, issue_id: int):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issue = data.get_issue(ws, issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        return issue

    @app.put("/api/workspaces/{name}/issues/{issue_id}")
    def update_issue(name: str, issue_id: int, body: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        try:
            issue = data.update_issue(ws, issue_id, body)
        except data.CircularDependencyError as e:
            raise HTTPException(status_code=409, detail=str(e))
        if issue is None:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        return issue

    @app.delete("/api/workspaces/{name}/issues/{issue_id}")
    def delete_issue(name: str, issue_id: int):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        deleted = data.delete_issue(ws, issue_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        return {"deleted": True}

    @app.put("/api/workspaces/{name}/issues/{issue_id}/vote")
    def update_vote(name: str, issue_id: int, body: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issue = data.get_issue(ws, issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        # Accept either {"verdict":..,"notes":..} or {"userVote":{..}}
        if "userVote" in body:
            user_vote = body["userVote"]
        else:
            user_vote = {"verdict": body.get("verdict"), "notes": body.get("notes", "")}
        issue = data.update_issue(ws, issue_id, {"userVote": user_vote})
        return issue

    @app.put("/api/workspaces/{name}/issues/{issue_id}/reviews")
    def update_review(name: str, issue_id: int, body: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        issue = data.get_issue(ws, issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

        reviewer = body.get("reviewer")
        verdict = body.get("verdict")
        notes = body.get("notes", "")

        existing_reviews = issue.get("reviews", {})
        existing_reviews[reviewer] = {"verdict": verdict, "notes": notes}

        issue = data.update_issue(ws, issue_id, {"reviews": existing_reviews})
        return issue

    # ------------------------------------------------------------------
    # Project endpoints
    # ------------------------------------------------------------------

    @app.get("/api/workspaces/{name}/projects")
    def list_projects(name: str):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        projects, warnings = data.list_projects(ws)
        return {"projects": projects, "warnings": warnings}

    @app.post("/api/workspaces/{name}/projects")
    def create_project(name: str, body: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        project = data.create_project(ws, body)
        return project

    @app.put("/api/workspaces/{name}/projects/{project_id}")
    def update_project(name: str, project_id: int, body: dict):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        project = data.update_project(ws, project_id, body)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return project

    @app.delete("/api/workspaces/{name}/projects/{project_id}")
    def delete_project(name: str, project_id: int):
        ws = _resolve_workspace(name)
        _require_tracker(ws)
        deleted = data.delete_project(ws, project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        return {"deleted": True}

    # ------------------------------------------------------------------
    # Static serving
    # ------------------------------------------------------------------

    @app.get("/")
    def serve_index():
        index = Path(__file__).resolve().parent / "index.html"
        if not index.exists():
            return HTMLResponse("<h1>404 — index.html not found</h1>", status_code=404)
        return FileResponse(str(index))

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

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
