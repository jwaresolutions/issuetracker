# Generic Issue Tracker — Design Spec

**Date:** 2026-03-12
**Status:** Approved

## Overview

A reusable, local-first issue and project tracker. The application code lives in a single repository (`issuetracker`), while each project stores its own data in a `.issuetracker/` folder that gets committed to that project's repo. This allows the same tracker UI to be pointed at any project by scanning a configurable root directory.

## Goals

- Replace the project-specific UX tracker with a generic, reusable tool
- Track issues, projects/milestones, and dependencies across any repository
- Full CRUD from the browser — no need to edit JSON by hand
- Retain reviewer verdicts (PM, Dev Lead, Security) and user voting from the existing UX tracker
- Zero-dependency frontend (single HTML file), minimal backend (FastAPI)
- Git-friendly data format (individual JSON files, clean diffs)

## Non-Goals

- Kanban/board views
- Multi-user collaboration or auth
- Assignee tracking
- Cloud hosting or remote sync

---

## Architecture

### Approach

Single-page HTML file with embedded CSS/JS, served by a FastAPI backend. The server handles project enumeration, file I/O, and exposes a REST API. No build step, no npm, no frontend framework.

### Repository Structure

```
issuetracker/
├── server.py              # FastAPI server (single file)
├── tracker.config.json    # Server config (root path override)
├── index.html             # Frontend (single file, embedded CSS/JS)
├── requirements.txt       # Python dependencies (fastapi, uvicorn)
├── tests/
│   └── test_api.py        # Backend tests
├── docs/
│   └── superpowers/specs/ # Design specs
└── .issuetracker/         # This project's own issue tracking data
```

### Per-Project Data Structure

Each project's `.issuetracker/` folder:

```
.issuetracker/
├── config.json            # Project-level metadata
├── issues/
│   ├── 001.json           # Individual issue files
│   ├── 002.json
│   └── ...
├── projects/
│   ├── 001.json           # Project/milestone definitions
│   └── ...
└── assets/                # Attachments, screenshots, etc.
    ├── 001/               # Assets linked to issue 001
    └── ...
```

The naming scheme (`001.json`, `002.json`, etc.) keeps files sorted and enables the `assets/{id}/` convention for linking additional files to any issue.

---

## Data Model

### config.json

```json
{
  "name": "Jware-Trader-X",
  "nextIssueId": 3,
  "nextProjectId": 2,
  "reviewers": ["PM", "Dev Lead", "Security"]
}
```

The `reviewers` array drives the UI dynamically — adding a new persona here automatically adds a new review card in the expanded row and a new section in the create/edit modal.

### issues/{id}.json

```json
{
  "id": 1,
  "title": "Login form lacks input validation",
  "description": "No client-side validation on email or password fields.",
  "status": "open",
  "priority": "high",
  "labels": ["frontend", "ux"],
  "projectId": 1,
  "cycle": 1,
  "personas": ["new-user"],
  "files": ["src/components/login.tsx"],
  "blockedBy": [3, 7],
  "reviews": {
    "PM": { "verdict": "approve", "notes": "High impact, low effort" },
    "Dev Lead": { "verdict": "approve", "notes": "~30 lines" },
    "Security": { "verdict": "approve", "notes": "" }
  },
  "userVote": { "verdict": null, "notes": "" },
  "createdAt": "2026-03-12T10:00:00Z",
  "updatedAt": "2026-03-12T10:00:00Z"
}
```

**Field details:**
- `id` — auto-incrementing integer, never reused after deletion
- `status` — one of: `open`, `in_progress`, `done`, `closed`
- `priority` — one of: `high`, `medium`, `low`
- `labels` — freeform string array
- `projectId` — references a project in `projects/`, nullable
- `cycle` — positive integer, nullable. Represents a review or development cycle number.
- `personas` — freeform string array. User personas affected by this issue (e.g., `["new-user", "power-user"]`).
- `files` — freeform string array. Source-code file paths related to this issue (not references to the `assets/` folder; assets are managed separately via the `assets/{id}/` directory).
- `blockedBy` — array of issue IDs that must be completed before this one can start
- `reviews` — keyed by reviewer persona name, dynamically driven by `config.json` reviewers array
- `userVote.verdict` — one of: `approve`, `defer`, `reject`, or `null`

### projects/{id}.json

```json
{
  "id": 1,
  "name": "Phase 1 — Core Trading",
  "description": "Core trading engine and broker integration",
  "status": "active",
  "createdAt": "2026-03-12T10:00:00Z"
}
```

**Project statuses:** `active`, `completed`, `archived`

---

## API Design

FastAPI server, single `server.py` file.

### Server Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/config` | Returns the root projects path |
| `PUT` | `/api/config` | Update the root projects path |

### Workspace Enumeration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/workspaces` | Scans root folder, returns all subdirectories with `hasTracker` boolean |
| `POST` | `/api/workspaces/{name}/init` | Creates `.issuetracker/` scaffold for a project |

### Issues

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/workspaces/{name}/issues` | List all issues (optional query params: status, priority, label, projectId) |
| `POST` | `/api/workspaces/{name}/issues` | Create issue (auto-increments ID) |
| `GET` | `/api/workspaces/{name}/issues/{id}` | Get single issue |
| `PUT` | `/api/workspaces/{name}/issues/{id}` | Update issue |
| `DELETE` | `/api/workspaces/{name}/issues/{id}` | Delete issue + its assets folder |
| `PUT` | `/api/workspaces/{name}/issues/{id}/vote` | Update user vote (body: `{ "verdict": "approve", "notes": "..." }`) |
| `PUT` | `/api/workspaces/{name}/issues/{id}/reviews` | Merge a single reviewer verdict (body: `{ "reviewer": "PM", "verdict": "approve", "notes": "..." }` — merges into the `reviews` object, does not replace other reviewers) |

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/workspaces/{name}/projects` | List projects |
| `POST` | `/api/workspaces/{name}/projects` | Create project |
| `PUT` | `/api/workspaces/{name}/projects/{id}` | Update project |
| `DELETE` | `/api/workspaces/{name}/projects/{id}` | Delete project |

### Static

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves `index.html` |

### Root Path Configuration

- Default: one directory above the issuetracker repo (e.g., if repo is at `/Users/me/projects/issuetracker`, default root is `/Users/me/projects/`)
- Override via `tracker.config.json` in repo root: `{ "rootPath": "/some/other/path" }`
- Override via CLI flag: `python server.py --root /some/other/path`
- Priority: CLI flag > config file > default

---

## UI Design

Single `index.html` with embedded CSS and JS. Dark GitHub-style theme matching the existing UX tracker aesthetic (dark background, monospace accents, colored badges, expandable rows).

### Layout

**Header bar:**
- Logo/title ("Issue Tracker")
- Workspace dropdown — lists all projects from root folder, shows indicator for which ones have `.issuetracker/` initialized. Selecting an uninitialized workspace shows an "Initialize Tracker" prompt.
- Settings gear — configure root path

**Stats bar:**
- Auto-generated stat cards matching current tracker style
- Counts: Total, Open, In Progress, Done, Blocked, High Priority

**Filters bar (multi-select on all groups):**
- Status toggle buttons (All / Open / In Progress / Done / Closed) — multiple can be active simultaneously
- Priority toggle buttons (All / High / Medium / Low) — multiple can be active simultaneously
- Project dropdown (milestones within the workspace)
- Label filter dropdown (dynamically populated, multi-select)
- Search input (text search across title and description)
- "Hide voted" checkbox

**Issues table:**
- Sortable columns: ID, Priority, Status, Project, Labels, Issue title
- Expandable rows showing:
  - Reviewer verdict cards — dynamically rendered from `config.json` reviewers array
  - Your Vote card (Approve / Defer / Reject buttons + notes textarea)
  - Linked files as chips
  - Blocked-by section — blocking issues shown as clickable badges (red if blocker is still open, green if resolved)
  - Cycle and meta info

**CRUD modals:**
- "New Issue" button opens modal: title, description (textarea), status, priority, project (dropdown), labels (tag input), cycle, personas, files, blockedBy (searchable multi-select of other issues), reviewer verdicts
- "New Project" button opens modal: name, description, status
- Edit button on each issue/project row opens pre-filled modal
- Delete with confirmation dialog

**Quick Wins section:**
- Carried over from current tracker — issues where all reviewers have verdict `approve` and priority is `high` or `medium`. This is the heuristic for "high-value, low-effort" — unanimous reviewer approval signals low risk/effort, and priority signals value.

---

## Error Handling & Recovery

### Auto-Recovery

| Scenario | Behavior |
|----------|----------|
| Missing subdirectory in `.issuetracker/` | Auto-recreate on access |
| Malformed issue JSON | Skip file, include warning in API response, UI shows "N issues failed to load" |
| Orphaned dependency (blocking issue deleted) | Auto-remove from all `blockedBy` arrays |
| Root path doesn't exist | Server starts, UI shows error banner with settings link |

### File Safety

- All file writes use atomic write (write to temp file, then rename) to prevent corruption
- No in-memory cache — server re-reads files on each request to stay in sync with manual edits or Claude changes
- IDs are never reused after deletion

### Circular Dependency Prevention

The API rejects updates that would create a dependency cycle. For example, if issue 1 blocks issue 2, attempting to add issue 1 to issue 2's `blockedBy` array returns an error.

### Pre-Built Claude Recovery Prompts

Every error scenario includes one or more copy-to-clipboard prompts in the UI error banner. These are context-aware, including actual paths, file names, and IDs.

**Missing subdirectory (e.g., `assets/` deleted):**
1. "Recreate the missing `{dir}` directory in `{workspace}/.issuetracker/` and regenerate any folders referenced by existing issues"
2. "Clean up all references in `{workspace}/.issuetracker/issues/*.json` that point to the missing `{dir}` directory"

**Malformed issue JSON:**
1. "Fix the malformed JSON in `{workspace}/.issuetracker/issues/{id}.json` — here is the current content: `{raw}`. Repair it to match the issue schema"
2. "Delete `{workspace}/.issuetracker/issues/{id}.json` and clean up any references to issue #{id} in other issues' `blockedBy` arrays"

**Orphaned dependencies:**
1. "Issue #{id} was deleted but is still referenced in `blockedBy` arrays. Clean up all references across `{workspace}/.issuetracker/issues/`"

**Missing config.json:**
1. "Rebuild `{workspace}/.issuetracker/config.json` by scanning existing `issues/` and `projects/` folders to determine correct `nextIssueId`, `nextProjectId`, and reviewer list"

**Corrupt or missing project file:**
1. "Recreate `{workspace}/.issuetracker/projects/{id}.json` based on issues that reference projectId {id}"
2. "Reassign all issues referencing projectId {id} to a different project or remove their project association"

**Root path does not exist:**
1. "The configured projects root `{path}` does not exist. Update the root path in Issue Tracker settings or create the directory"

---

## Testing Strategy

### Backend (pytest)

Tests use FastAPI's `TestClient` with temporary directories as the root path, with scaffolded `.issuetracker/` folders.

**Test cases:**
- CRUD operations for issues and projects
- ID auto-increment and stability after deletes
- Circular dependency rejection
- Malformed JSON handling (skips bad files, returns warnings)
- Missing subdirectory auto-recreation
- Orphaned dependency cleanup on issue delete
- Workspace initialization scaffold
- Root path validation (missing, invalid)
- Config read/write (root path override)
- Multi-filter query parameter combinations
- Vote endpoint (PUT .../vote) creates and updates user votes correctly
- Review endpoint (PUT .../reviews) merges single reviewer verdict without overwriting others

### Frontend

Manual verification — visual inspection that the UI renders correctly, filters work with multi-select, modals submit properly, and error banners display with recovery prompts. No e2e framework; this is a local dev tool.
