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
4. **Copy** and integrate into your project
5. **Build** your actual features on this foundation

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
  "language": "FastAPI",
  "project_id": "unique-project-id"
}
```

**Cleanup**
```
POST /api/cleanup
```

## Technologies

- Backend: Python Flask
- Frontend: HTML, CSS, JavaScript
- AI: Google Gemini API
- Styling: Bootstrap 5.3.2

## Contributing

**Database connection feature is not available.** Contributions welcome for:
- Direct database connectivity
- Additional frameworks
- Testing and documentation

---

**Build on solid ground, not quicksand.**
