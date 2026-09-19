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
- **Focused prompts**: SQL and Prisma requests include the selected table and related tables
- **Free response cache**: Repeated generations are served from a bounded in-memory cache
- **Downloadable output**: Save generated endpoints directly as framework-appropriate files
- **Health monitoring**: Check application and database readiness at `/health`
- **Free sample demo**: Try the built-in sample schema without preparing a file

## Project Structure

```
22f3002244-redirect/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── models/
│   └── db.py              # Database models
├── routes/
│   └── route.py           # API routes
├── templates/
│   ├── home.html          # Landing page
│   └── generator.html     # Code generation interface
└── test/
    └── sample.sql         # Sample SQL file
```

## Installation

### Prerequisites
- Python 3.9 or higher
- pip

### Setup

1. Clone and navigate to directory:
```bash
git clone <repository-url>
cd 22f3002244-redirect
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

Use **Try Sample Schema** on the home page to test the complete flow immediately with a
small `users` and `posts` schema.

For SQL and Prisma files, Redirect first extracts table names locally and sends only the
selected table context to Gemini. Repeating the same generation request during the
running server process uses the local cache and does not call Gemini again. The cache is
intentionally bounded and is cleared when the service restarts.

The sample schema is available at [`test/sample.sql`](test/sample.sql). The free Render
deployment may take several seconds to wake from a cold start. Configure `SECRET_KEY`,
`DATABASE_URL`, and `GEMINI_API_KEY` as Render environment variables before testing the
end-to-end flow.

## API Endpoints

**Upload Schema**
```
POST /api/upload
Content-Type: multipart/form-data
```

**Generate Code**
```
POST /api/generate-code
Content-Type: application/json

Body:
{
  "table_name": "users",
  "method": "GET",
  "auth_mode": "Token (JWT)",
  "language": "FastAPI"
}
```

The active project is associated with the current browser session; `project_id` is not
required in the generation request.

**Cleanup**
```
POST /api/cleanup
```

**Health check**
```
GET /health
```

Database schema changes are managed with Flask-Migrate. Deployments run
`flask --app app db upgrade` before starting the web process.

Uploaded projects belong to the current browser session and expire automatically after
24 hours. Switching tabs does not delete the project. AI failures return HTTP 502 instead
of being embedded in generated source code.
Generated responses are cached for up to seven days, and each session has a 20-generation
AI limit to protect free-tier quota.

## Technologies

- Backend: Python Flask
- Frontend: HTML, CSS, JavaScript
- AI: Google Gemini API
- Styling: Bootstrap 5.3.2
- Testing: pytest and GitHub Actions
- Performance: deterministic extraction, focused AI prompts, bounded in-memory caching

## Contributing

**Database connection feature is not available.** Contributions welcome for:
- Direct database connectivity
- Additional frameworks
- Testing and documentation

---

**Build on solid ground, not quicksand.**
