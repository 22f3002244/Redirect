# Redirect - REST API Code Generator

> Generate production-ready REST APIs from your database schema. Get a clean foundation and build your features on top.

**Stop rebuilding from scratch.** When AI-generated code gets messy and doesn't match your vision, you waste time fighting with tangled architecture instead of building features.

Redirect gives you clean, well-structured backend code upfront:
- **Save time**: Skip repetitive boilerplate. Get CRUD operations instantly.
- **Stay organized**: Start with proper code structure that scales as your project grows.
- **Build what matters**: Focus on your actual features, not setup.

## Overview

Transform database schemas into fully functional REST API code. Upload your schema, select your framework and authentication method, and generate production-ready endpoints.

## Features

- **Multi-Format Support**: `.sql`, `.prisma`, `.js`, `.ts`, `.py`, `.java`, `.json`
- **40+ Frameworks**: Flask, Django, FastAPI, Express, NestJS, Spring Boot, Gin, Rails, Laravel, and more
- **HTTP Methods**: GET, POST, PUT, PATCH, DELETE
- **Authentication**: Session (Cookie), Token (JWT), OAuth, API Keys
- **AI-Powered**: Clean, idiomatic code for your chosen framework
- **Focused prompts**: SQL and Prisma requests include the selected table and related tables only
- **Free response cache**: Repeated generations are served from a bounded database cache
- **Downloadable output**: Save generated endpoints directly as framework-appropriate files
- **Generation modes**: Create one endpoint, a full CRUD module, or an endpoint with tests
- **Health monitoring**: Check application and database readiness at `/health`
- **Free sample demo**: Try the built-in sample schema without preparing a file

## Project Structure

```
redirect/
├── app.py                  # Flask app factory, rate-limit 429 handler, security headers
├── requirements.txt        # Python dependencies (includes sqlglot for SQL parsing)
├── pytest.ini              # Zero-config test runner setup
├── models/
│   └── db.py              # Database models — Project stores owner_id for IDOR protection
├── routes/
│   └── route.py           # API routes with ownership checks, rate limiting, typed error codes
├── migrations/
│   └── versions/          # Alembic migration for owner_id column
├── templates/
│   ├── home.html          # Landing page
│   └── generator.html     # Code generation interface with explicit "Close Project" button
└── test/
    ├── conftest.py        # Pytest fixtures
    ├── test_routes.py     # 28 tests covering security, extraction, rate limits, CI
    └── sample.sql         # Sample SQL schema
```

## Installation

### Prerequisites
- Python 3.9 or higher
- pip

### Setup

1. Clone and navigate to directory:
```bash
git clone <repository-url>
cd redirect
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create `.env` file:
```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key
GEMINI_API_KEY=your-gemini-api-key
# Optional; defaults to gemini-2.5-flash
GEMINI_MODEL=gemini-2.5-flash
```

5. Run:
```bash
flask run
```

Access at `http://localhost:5000`

## Usage

1. **Upload** your database schema (max 5MB)
2. **Select** table, HTTP method, auth mode, and framework
3. **Generate** clean API code
4. **Copy or download** the generated endpoint
5. **Build** your actual features on this foundation

Choose an output mode before generating: **Single endpoint** keeps the original behaviour,
**Full CRUD module** generates all common operations, and **Endpoint + tests** includes a
test starter for the selected framework.

Use **Try Sample Schema** on the home page to test the complete flow immediately with a
small `users` and `posts` schema.

## How Table Extraction Works

For `.sql` files, table names are extracted **without any AI call** using
[sqlglot](https://github.com/tobymao/sqlglot), a pure-Python SQL parser that builds an
AST and walks it to find every `Table` node. This covers `CREATE TABLE`, `INSERT INTO`,
`SELECT … FROM`, and joined tables in a single deterministic pass.

```python
# routes/route.py — no AI involved
parsed = sqlglot.parse(sql_query)
tables = {t.name for stmt in parsed if stmt for t in stmt.find_all(Table) if t.name}
```

For `.prisma` files, a regex over `model` blocks is used instead. For all other file
types, Gemini is called as a **last-resort fallback** only when neither approach returns
results.

Only the context for the **selected table and its directly related tables** (via
`FOREIGN KEY` / `REFERENCES`) is sent to Gemini for code generation — the full schema
is never forwarded to the AI.

## API Endpoints

**Upload Schema**
```
POST /api/upload
Content-Type: multipart/form-data
Rate limited: 10 per hour
```

**Get Project Details**
```
GET /api/project/<project_id>
```
*IDOR-protected: the server compares `owner_id` against the session `user_id`. Returns
`HTTP 403 Forbidden` if the project belongs to a different user, `HTTP 404` if it
doesn't exist.*

**Delete Project**
```
DELETE /api/project/<project_id>
```
*IDOR-protected: same ownership check as GET. Returns `HTTP 403` for non-owners.*

**Generate Code**
```
POST /api/generate-code
Content-Type: application/json

{
  "table_name": "users",
  "method": "GET",
  "auth_mode": "Token",
  "language": "FastAPI",
  "output_mode": "endpoint"
}
```

Error responses always use proper HTTP status codes — AI errors are **never** written
into generated code as comments:

| Scenario | HTTP Status |
|---|---|
| Missing or invalid parameters | `400 Bad Request` |
| CSRF token mismatch | `403 Forbidden` |
| IDOR: project belongs to another user | `403 Forbidden` |
| Project not found / session expired | `404 Not Found` |
| Session generation limit (20) reached | `429 Too Many Requests` |
| Rate limit exceeded (5 req/min) | `429 Too Many Requests` |
| AI service unavailable | `503 Service Unavailable` |

The `429` rate-limit response is a structured JSON object — not an HTML page:
```json
{
  "success": false,
  "error": "Rate limit exceeded. Please try again later.",
  "detail": "5 per 1 minute"
}
```

The active project is tied to the current browser session; `project_id` is not required
in the request body.

**Close Project — explicit user action only**
```
POST /api/cleanup
POST /api/cleanup/<project_id>
```

Projects are deleted **only** when the user explicitly clicks **"Close Project"** in the
generator UI header. There are **no** `visibilitychange` or `beforeunload` event listeners
that call this endpoint — switching tabs or minimising the browser does not touch the
project. As a secondary safety net, uploaded projects also expire after **24 hours** via a
server-side TTL purge triggered on each new upload.

**Health check**
```
GET /health
```

Returns `{"status": "ok", "database": "ok"}` when the database is reachable, or
`{"status": "error", "database": "unavailable"}` with `HTTP 503` otherwise.

Database schema changes are managed with Flask-Migrate. Deployments run
`flask --app app db upgrade` before starting the web process.

## Security Notes

- **Session isolation**: every browser session gets a unique `user_id` stored in a
  server-signed cookie. Each uploaded project records that `user_id` as its `owner_id`.
- **IDOR prevention**: all project endpoints call `verify_project_owner()` which returns
  `HTTP 403` when `owner_id != session user_id`.
- **CSRF protection**: state-mutating routes check the `X-CSRF-Token` header against a
  per-session token embedded in a `<meta>` tag.
- **Security headers**: `X-Content-Type-Options`, `X-Frame-Options`, and
  `Referrer-Policy` are added to every response by an `after_request` hook.
- **AI error isolation**: Gemini failures raise a typed `GeminiError` internally and are
  surfaced to the client as `HTTP 503` — they are never written into generated code.

## Running Tests

```bash
pytest       # runs all 28 tests (uses pytest.ini automatically)
pytest -v    # verbose output with test names
```

The test suite covers:

| Area | Tests |
|---|---|
| File upload validation | bad extension, non-UTF-8, >5 MB |
| IDOR enforcement | 403 for non-owner, 200 for owner, 404 for unknown project |
| sqlglot extraction | standard CREATE TABLE, JOINs, subqueries, invalid SQL fallback |
| Rate limiting | 429 on the 6th request within a minute |
| AI gateway errors | 503 on GeminiError, error text not in generated code |
| Generation caching | second identical request served from cache |
| Schema context trimming | related tables included, unrelated tables excluded |
| Explicit cleanup | project deleted, session cleared |

GitHub Actions runs the full suite on every push via `.github/workflows/ci.yml`.

## Technologies

- **Backend**: Python Flask
- **Frontend**: HTML, CSS, JavaScript
- **AI**: Google Gemini API
- **Styling**: Bootstrap 5.3.2
- **SQL Parsing**: sqlglot — deterministic AST-based table extraction, no AI required
- **Testing**: pytest (28 tests) + GitHub Actions CI
- **Performance**: deterministic extraction, focused AI prompts, persistent database caching

## Contributing

**Database connection feature is not available.** Contributions welcome for:
- Direct database connectivity
- Additional frameworks
- Testing and documentation

---

**Build on solid ground, not quicksand.**
