# Claude Code Skill: Issue Tracker

This skill enables Claude to interact with `.issuetracker/` data directly via file read/write. No server required.

---

## Detection

When a user asks about issues, projects, or anything tracker-related, check for `.issuetracker/` in the current working directory:

```bash
ls .issuetracker/
```

If `.issuetracker/` does **not** exist, offer to initialize it:

> "I don't see a `.issuetracker/` directory here. Would you like me to initialize one?"

If the user confirms, create the scaffold:

```
.issuetracker/
  config.json
  issues/
  projects/
  assets/
```

Initial `config.json`:

```json
{
  "name": "My Project",
  "nextIssueId": 1,
  "nextProjectId": 1,
  "reviewers": ["PM", "Dev Lead", "Security"]
}
```

---

## Data Schema

### config.json

```
.issuetracker/config.json
```

```json
{
  "name": "string — display name for this tracker",
  "nextIssueId": "int — next ID to assign when creating an issue",
  "nextProjectId": "int — next ID to assign when creating a project",
  "reviewers": ["string — reviewer names, e.g. PM, Dev Lead, Security"]
}
```

### issues/{id}.json

```
.issuetracker/issues/{id:03d}.json
```

Zero-padded to 3 digits: `001.json`, `012.json`, `100.json`.

```json
{
  "id": "int",
  "title": "string",
  "description": "string",
  "status": "open | in_progress | done | closed",
  "priority": "high | medium | low",
  "labels": ["string"],
  "projectId": "int | null",
  "cycle": "int | null",
  "personas": ["string"],
  "files": ["string — relative file paths relevant to this issue"],
  "blockedBy": ["int — IDs of issues that must be resolved first"],
  "reviews": {
    "{reviewer_name}": {
      "verdict": "approve | defer | reject | null",
      "notes": "string"
    }
  },
  "userVote": {
    "verdict": "approve | defer | reject | null",
    "notes": "string"
  },
  "createdAt": "ISO 8601 timestamp",
  "updatedAt": "ISO 8601 timestamp"
}
```

### projects/{id}.json

```
.issuetracker/projects/{id:03d}.json
```

```json
{
  "id": "int",
  "name": "string",
  "description": "string",
  "status": "active | completed | archived",
  "createdAt": "ISO 8601 timestamp"
}
```

---

## Operations

### ID Management

Before creating an issue or project, read `config.json` to get the next ID. After writing the new file, increment the appropriate counter and write `config.json` back.

Always use **atomic writes**: write to a temp file in the same directory, then rename it over the target:

```python
import os, json, tempfile

def atomic_write(path: str, data: dict) -> None:
    dir_ = os.path.dirname(path)
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump(data, f, indent=2)
        tmp = f.name
    os.replace(tmp, path)
```

### CRUD — Issues

**List issues**

Read all files matching `.issuetracker/issues/*.json`. Return as a list sorted by `id`.

Optional filters: `status`, `priority`, `projectId`, `labels`.

**Get issue**

Read `.issuetracker/issues/{id:03d}.json`.

**Create issue**

1. Read `config.json`, get `nextIssueId` as `new_id`.
2. Build issue object with all required fields; set `createdAt` and `updatedAt` to current UTC ISO 8601.
3. Initialize `reviews` from `config.json` reviewers, each with `{"verdict": null, "notes": ""}`.
4. Initialize `userVote` as `{"verdict": null, "notes": ""}`.
5. Atomic-write to `.issuetracker/issues/{new_id:03d}.json`.
6. Increment `nextIssueId` in `config.json`, atomic-write it back.

**Update issue**

1. Read existing issue file.
2. Merge provided fields.
3. Set `updatedAt` to current UTC ISO 8601.
4. Atomic-write back.

**Delete issue**

1. Remove `.issuetracker/issues/{id:03d}.json`.
2. Scan all other issue files; remove `id` from any `blockedBy` arrays and atomic-write those files.
3. Remove `.issuetracker/assets/{id}/` if it exists.

### CRUD — Projects

**List projects**

Read all files matching `.issuetracker/projects/*.json`. Return sorted by `id`.

**Get project**

Read `.issuetracker/projects/{id:03d}.json`.

**Create project**

1. Read `config.json`, get `nextProjectId` as `new_id`.
2. Build project object; set `createdAt` to current UTC ISO 8601.
3. Atomic-write to `.issuetracker/projects/{new_id:03d}.json`.
4. Increment `nextProjectId` in `config.json`, atomic-write it back.

**Update project**

Read, merge fields, atomic-write back.

**Delete project**

Remove `.issuetracker/projects/{id:03d}.json`.

### Dependency Validation (blockedBy)

Before adding entries to `blockedBy` on issue `T`, check that none of the proposed blockers would create a cycle. Use DFS: starting from each proposed blocker `B`, follow `blockedBy` edges; if you reach `T`, reject with an explanation.

```
Cycle check: T is blocked by B
  Walk: B → B's blockers → their blockers → ...
  If T appears in the walk → CYCLE DETECTED, refuse the update
```

### Quick Wins Query

Return issues where:
- Every reviewer in `config.json` has `verdict == "approve"` in `reviews`
- `priority` is `"high"` or `"medium"`
- `status` is not `"done"` and not `"closed"`

---

## File Naming Reference

| Type    | Pattern                              | Example           |
|---------|--------------------------------------|-------------------|
| Issue   | `.issuetracker/issues/{id:03d}.json` | `issues/007.json` |
| Project | `.issuetracker/projects/{id:03d}.json` | `projects/002.json` |
| Assets  | `.issuetracker/assets/{issue_id}/`   | `assets/007/`     |
| Config  | `.issuetracker/config.json`          | —                 |

---

## Example Interactions

### 1. Create an issue

**User:** "Add an issue: the login button is broken on mobile, high priority, label it bug."

**Claude:**
1. Read `config.json` → `nextIssueId: 4`.
2. Write `.issuetracker/issues/004.json`:

```json
{
  "id": 4,
  "title": "Login button broken on mobile",
  "description": "The login button is broken on mobile.",
  "status": "open",
  "priority": "high",
  "labels": ["bug"],
  "projectId": null,
  "cycle": null,
  "personas": [],
  "files": [],
  "blockedBy": [],
  "reviews": {
    "PM": {"verdict": null, "notes": ""},
    "Dev Lead": {"verdict": null, "notes": ""},
    "Security": {"verdict": null, "notes": ""}
  },
  "userVote": {"verdict": null, "notes": ""},
  "createdAt": "2026-03-12T00:00:00Z",
  "updatedAt": "2026-03-12T00:00:00Z"
}
```

3. Update `config.json` → `nextIssueId: 5`.
4. Reply: "Created issue #4: Login button broken on mobile (high, bug)."

---

### 2. Query blockers for an issue

**User:** "What is blocking issue #7?"

**Claude:**
1. Read `.issuetracker/issues/007.json`.
2. Read `blockedBy` → `[3, 5]`.
3. Read `issues/003.json` and `issues/005.json`.
4. Reply:

> "Issue #7 is blocked by:
> - #3 — Refactor auth module (status: in_progress)
> - #5 — Fix session timeout (status: open)"

---

### 3. Mark an issue as done

**User:** "Mark issue #12 as done."

**Claude:**
1. Read `.issuetracker/issues/012.json`.
2. Set `status: "done"`, update `updatedAt`.
3. Atomic-write back.
4. Reply: "Issue #12 marked as done."

---

### 4. Close all issues in a project

**User:** "Close all open issues in project #2."

**Claude:**
1. Read all issue files; filter where `projectId == 2` and `status` is not `"closed"`.
2. For each matched issue, set `status: "closed"`, update `updatedAt`, atomic-write.
3. Reply: "Closed 6 issues in project #2: #8, #9, #11, #13, #14, #15."

---

## Automatic Behavior

### Suggesting status updates

When Claude fixes a bug or implements a feature during a coding session, and a tracked issue appears to match the work done, Claude should **suggest** updating the issue:

> "This looks like it resolves issue #4 (Login button broken on mobile). Would you like me to mark it as done?"

**Do NOT auto-close or auto-update issues without explicit user confirmation.**

### Commit-linked issue detection

When creating git commits, scan the commit message for issue references like `#N` (e.g., `fix login validation (#4)`). If a referenced issue exists in `.issuetracker/issues/`, suggest updating its status:

> "Commit references issue #4. Current status is `open`. Would you like me to mark it as `done`?"

This applies to:
- Commit messages containing `#N`, `fixes #N`, `closes #N`, `resolves #N`
- Multiple references in one commit (e.g., `#4, #7`)

Always confirm before making changes — never auto-update.

---

## Error Cases

| Situation | Response |
|-----------|----------|
| `.issuetracker/` not found | Offer to initialize the scaffold |
| Issue file not found | "Issue #{id} does not exist." |
| `blockedBy` would create a cycle | Explain the cycle path, refuse the update |
| `status` value not in allowed set | "Status must be one of: open, in_progress, done, closed." |
| `priority` value not in allowed set | "Priority must be one of: high, medium, low." |
