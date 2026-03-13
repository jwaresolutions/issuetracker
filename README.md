# Issue Tracker

A file-based issue tracking system for software projects. Store all issues and projects as individual JSON files in a `.issuetracker/` folder, manage them through a clean browser UI, and integrate with Claude Code or Kiro CLI for AI-assisted issue management.

## Features

- **Full CRUD via Browser** — Create, read, update, and delete issues and projects with a dark GitHub-themed UI
- **Multi-Reviewer Verdicts** — PM, Dev Lead, Security, and custom reviewers can approve/reject issues with notes
- **User Voting** — Users vote on issues separately from reviewer verdicts
- **Dependency Tracking** — Mark issues blocked by other issues with automatic circular dependency detection
- **Smart Filtering** — Filter by status, priority, labels, project, and cycle with multi-select support
- **Quick Wins** — Dedicated section showing all approved issues with high/medium priority
- **Project-Scoped Labels** — Create and autocomplete labels per project
- **Bulk Status Updates** — Update multiple issues at once with checkboxes
- **Workspace Support** — Manage multiple independent issue trackers from one server
- **Zero Dependencies Frontend** — Single HTML file, no build step or external JavaScript libraries
- **Atomic Writes** — All file operations are atomic; safe to edit files directly while server runs
- **Error Recovery** — User-friendly prompts guide recovery from missing or corrupt data

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, uvicorn
- **Frontend**: Single HTML file with vanilla JS and GitHub-inspired dark CSS
- **Data**: Individual JSON files per issue/project (no database required)
- **Testing**: pytest + httpx (43 test cases)

## Project Structure

```
issuetracker/
├── server.py                    # FastAPI backend with REST API
├── data.py                      # Data layer (CRUD, atomic writes, validation)
├── index.html                   # Single-file frontend (no build step)
├── start.sh                     # Launch script
├── requirements.txt             # Python dependencies
├── tracker.config.json          # Server config (gitignored after setup)
├── tracker.config.example.json  # Config template
├── skill/
│   └── issuetracker.md         # Claude Code / Kiro CLI skill
├── scripts/
│   └── import_ux_tracker.py    # Utility to migrate from other trackers
└── tests/
    ├── test_api.py             # API endpoint tests
    └── test_data.py            # Data layer tests
```

## Getting Started

### Prerequisites

- Python 3.12+
- pip or venv

### Installation

1. Clone the repository
```bash
git clone https://github.com/jwaresolutions/issuetracker.git
cd issuetracker
```

2. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Configure the server
```bash
cp tracker.config.example.json tracker.config.json
# Edit tracker.config.json and set rootPath to your projects directory
```

5. Start the server
```bash
./start.sh
# Or: python server.py --port 3232
```

6. Open http://127.0.0.1:3232 in your browser

## Configuration

Create a `tracker.config.json` file in the project root:

```json
{
  "rootPath": "/path/to/your/projects",
  "port": 3232
}
```

- **rootPath**: Directory containing your project folders (each becomes a workspace)
- **port**: HTTP port for the server (default: 3232)

If `rootPath` is null, defaults to the parent directory of the issuetracker folder.

## How It Works

### Workspaces

A **workspace** is any directory under your root path. When you initialize a workspace, issuetracker creates a `.issuetracker/` folder inside it:

```
my-project/
├── src/
├── tests/
└── .issuetracker/          # Created by issuetracker
    ├── config.json         # Workspace config
    ├── issues/             # Individual issue files
    ├── projects/           # Individual project files
    └── assets/             # Uploaded files (future use)
```

### Data Format

Issues and projects are stored as individual JSON files with zero custom serialization.

**Issue** (`.issuetracker/issues/001.json`):
```json
{
  "id": 1,
  "title": "Fix login bug",
  "status": "open",
  "priority": "high",
  "labels": ["bug", "auth"],
  "projectId": 1,
  "createdAt": "2025-03-12T10:30:00+00:00",
  "updatedAt": "2025-03-12T10:30:00+00:00",
  "description": "Users cannot log in with SSO",
  "blockedBy": [],
  "reviews": {
    "PM": { "verdict": "approved", "notes": "High priority" },
    "Dev Lead": { "verdict": "approved", "notes": "" },
    "Security": { "verdict": "pending", "notes": "" }
  },
  "userVote": { "verdict": "approved", "notes": "" }
}
```

**Project** (`.issuetracker/projects/001.json`):
```json
{
  "id": 1,
  "name": "Authentication",
  "description": "Single sign-on integration",
  "labels": ["bug", "feature", "security"],
  "createdAt": "2025-03-12T10:30:00+00:00",
  "updatedAt": "2025-03-12T10:30:00+00:00"
}
```

### Atomic Writes

All file operations use atomic writes (temp file + rename). You can safely edit `.issuetracker/` files directly while the server is running—no data corruption risk.

### Dependency Validation

When you set `blockedBy` on an issue, issuetracker automatically detects circular dependencies:

```
Issue A blocked by Issue B
Issue B blocked by Issue C
Issue C blocked by Issue A  ← Circular! Rejected.
```

The API returns `409 Conflict` with a clear error message.

## REST API

### Workspaces

```
GET    /api/workspaces                       # List all workspaces
POST   /api/workspaces/{name}/init           # Initialize a workspace
GET    /api/config                           # Get server config
PUT    /api/config                           # Update server config
```

### Issues

```
GET    /api/workspaces/{name}/issues         # List issues (supports filters)
POST   /api/workspaces/{name}/issues         # Create issue
GET    /api/workspaces/{name}/issues/{id}    # Get issue
PUT    /api/workspaces/{name}/issues/{id}    # Update issue
DELETE /api/workspaces/{name}/issues/{id}    # Delete issue
PUT    /api/workspaces/{name}/issues/{id}/reviews  # Update reviewer verdict
PUT    /api/workspaces/{name}/issues/{id}/vote     # Update user vote
```

**Query Parameters for listing issues:**
- `status=open|closed` — Filter by status
- `priority=high|medium|low` — Filter by priority
- `label=bug` — Filter by label
- `projectId=1` — Filter by project

### Projects

```
GET    /api/workspaces/{name}/projects       # List projects
POST   /api/workspaces/{name}/projects       # Create project
PUT    /api/workspaces/{name}/projects/{id}  # Update project
DELETE /api/workspaces/{name}/projects/{id}  # Delete project
```

## Frontend

The frontend is a single HTML file (`index.html`) with:
- Dark GitHub-inspired theme
- Sidebar navigation by status
- Issue list with filtering and bulk actions
- Detail view with reviewer verdicts and user voting
- Dependency graph display
- Quick Wins section (all reviewers approved + high/medium priority)
- Zero external JavaScript dependencies

### Browser Support

Modern browsers (Chrome, Firefox, Safari, Edge) with ES6+ support.

## Testing

Run the full test suite:

```bash
pytest tests/
```

Run specific test file:

```bash
pytest tests/test_api.py -v
pytest tests/test_data.py -v
```

The project includes 43 tests covering:
- CRUD operations for issues and projects
- Circular dependency detection
- Atomic writes and file corruption recovery
- API endpoint behavior
- Filter and query logic

## Initialize a New Project

To add issuetracker to an existing project, paste this prompt into Claude Code or Kiro CLI:

```
I want to add issue tracking to this project using the issuetracker system.

Please:
1. Initialize a `.issuetracker/` directory with config.json, issues/, projects/, and assets/ subdirectories
2. Set the project name in config.json to [PROJECT_NAME]
3. Copy the Claude Code skill from https://raw.githubusercontent.com/jwaresolutions/issuetracker/main/skill/issuetracker.md to .claude/skills/issuetracker.md
4. Confirm the setup is working by listing issues (should be empty)

Then show me the URL to access the issue tracker.
```

## AI Assistant Integration

### Claude Code Skill

The issuetracker skill enables Claude Code to manage issues directly via file read/write operations. No server setup needed.

**Location**: `.claude/skills/issuetracker.md`

**Download**:
```bash
curl -o .claude/skills/issuetracker.md \
  https://raw.githubusercontent.com/jwaresolutions/issuetracker/main/skill/issuetracker.md
```

**Usage in Claude Code**:
```
/issuetracker list issues
/issuetracker create issue --title "Fix bug" --priority high
/issuetracker close issue 1
```

### Kiro CLI Skill

For Kiro CLI integration, copy the skill to your project:

```bash
mkdir -p .kiro/skills/issuetracker
curl -o .kiro/skills/issuetracker/SKILL.md \
  https://raw.githubusercontent.com/jwaresolutions/issuetracker/main/skill/issuetracker.md
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Type Checking

```bash
mypy server.py data.py
```

### Code Style

Follow PEP 8. The codebase uses:
- Type hints throughout
- Docstring module headers
- Atomic write patterns for all file I/O

### Adding Features

1. Update `data.py` for new data operations
2. Update `server.py` for new API endpoints
3. Update `index.html` for UI changes
4. Add tests to `tests/test_api.py` or `tests/test_data.py`
5. Run full test suite before committing

## Troubleshooting

### Port Already in Use

```bash
python server.py --port 3233
```

### Workspace Not Found

Ensure the directory exists under your configured `rootPath` and contains a `.issuetracker/` folder.

### Circular Dependency Error

You cannot create a dependency chain where Issue A → B → C → A. Remove one of the blocking relationships.

### Data Corruption Recovery

If an issue file is corrupted, the UI shows an error with the filename and suggests deleting the file. Corrupt files are never overwritten automatically.

## Architecture

- **Data layer** (`data.py`): Handles all file I/O, CRUD, and validation
- **API layer** (`server.py`): FastAPI endpoints with error handling
- **Frontend** (`index.html`): Single-file SPA with no build step
- **Tests** (`tests/`): Comprehensive coverage of data layer and API

The separation ensures:
- Frontend can be deployed anywhere (static file)
- API is stateless (safe to restart)
- Data layer is testable in isolation
- No external dependencies in the frontend

## License

MIT

## Contributing

Issues and pull requests welcome. Please include tests for new features.

---

**Questions?** Open an issue on GitHub or check the docs directory.
