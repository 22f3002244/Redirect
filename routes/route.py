import ast
import hashlib
import os
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Blueprint, current_app, jsonify, render_template, request, session
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google import genai
from werkzeug.utils import secure_filename

from models.db import GenerationCache, Project, db

load_dotenv()

main = Blueprint("main", __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=[])

ALLOWED_EXTENSIONS = {"sql", "prisma", "js", "ts", "py", "java", "json"}
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_AI_INPUT_SIZE = 200_000
PROJECT_TTL = timedelta(hours=24)
CACHE_TTL = timedelta(days=7)
SESSION_GENERATION_LIMIT = 20
SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
SUPPORTED_AUTH_MODES = {
    "Session",
    "Token",
    "OAuth (Google/GitHub login)",
    "API Keys",
}
SUPPORTED_OUTPUT_MODES = {"endpoint", "crud", "tests"}
SAMPLE_SCHEMA = """CREATE TABLE users (
    id INT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL
);

CREATE TABLE posts (
    id INT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);"""


class GeminiError(RuntimeError):
    """Raised when Gemini cannot complete a requested operation."""


def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("AI generation is not configured on this server.")
    return genai.Client(api_key=api_key)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_tables_deterministically(file_content, file_extension):
    """Extract common SQL and Prisma model names without an AI call."""
    if file_extension == "sql":
        matches = re.findall(
            r"\bCREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+[`\"']?([A-Za-z_][\w$]*)",
            file_content,
            flags=re.IGNORECASE,
        )
    elif file_extension == "prisma":
        matches = re.findall(r"^\s*model\s+([A-Za-z_][\w$]*)", file_content, flags=re.MULTILINE)
    else:
        matches = []
    return list(dict.fromkeys(matches))


def extract_tables_with_gemini(file_content, file_extension):
    prompt = (
        f"Analyze this {file_extension.upper()} schema/model code and return ONLY table names "
        "separated by commas. Return an empty string if none are found.\n\n"
        f"Code:\n{file_content}"
    )
    try:
        response = get_gemini_client().models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), contents=prompt
        )
        return [name.strip() for name in response.text.split(",") if name.strip()]
    except Exception as exc:
        current_app.logger.warning(
            "Gemini table extraction failed: %s", exc.__class__.__name__, exc_info=True
        )
        raise GeminiError("The AI service could not extract tables. Please try again.") from exc


def extract_tables(file_content, file_extension):
    tables = extract_tables_deterministically(file_content, file_extension)
    return tables or extract_tables_with_gemini(file_content, file_extension)


def schema_for_table(file_content, file_extension, table_name):
    """Keep AI prompts small by sending the selected table and nearby relations."""
    if file_extension == "sql":
        blocks = re.findall(
            r"\bCREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+[`\"']?[\w$]+.*?(?:;|$)",
            file_content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        selected = [
            block for block in blocks
            if re.search(rf"\b{re.escape(table_name)}\b", block, flags=re.IGNORECASE)
        ]
        related = [
            block for block in blocks
            if re.search(rf"\bREFERENCES\s+[`\"']?{re.escape(table_name)}\b", block, flags=re.IGNORECASE)
        ]
        context = "\n\n".join(dict.fromkeys(selected + related))
        return context or file_content
    if file_extension == "prisma":
        match = re.search(
            rf"^\s*model\s+{re.escape(table_name)}\b.*?(?=^\s*model\s+|\Z)",
            file_content,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        return match.group(0).strip() if match else file_content
    return file_content


def generate_api_code_with_gemini(
    table_name, method, auth_mode, language, file_content, output_mode="endpoint"
):
    if len(file_content) > MAX_AI_INPUT_SIZE:
        raise GeminiError(
            "This schema is too large to process on the free-tier server. "
            "Please upload a schema smaller than 200,000 characters."
        )
    mode_instructions = {
        "endpoint": "Generate one endpoint function for the requested HTTP method.",
        "crud": "Generate a complete CRUD module for this table with functions for GET, POST, PUT, PATCH, and DELETE.",
        "tests": "Generate the endpoint function followed by focused tests for it using the framework's standard test tooling.",
    }[output_mode]
    prompt = f"""You are an expert backend developer.
{mode_instructions}
Table: {table_name}
HTTP Method: {method}
Authentication: {auth_mode}
Language/Framework: {language}

Database Schema:
{file_content}

Return ONLY the raw function code, without markdown fences, route decorators, docstrings, or explanations.
Comment out imports. Assume the database session is configured as SessionLocal() or Session().
Implement authentication, CRUD behavior, error handling, JSON responses with success/message/data,
appropriate status codes, and close database connections in a finally block."""
    try:
        response = get_gemini_client().models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"), contents=prompt
        )
        code = response.text.strip()
        if code.startswith("```"):
            lines = code.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            code = "\n".join(lines).strip()
        return code
    except Exception as exc:
        current_app.logger.warning(
            "Gemini code generation failed: %s", exc.__class__.__name__, exc_info=True
        )
        raise GeminiError("The AI service could not generate code. Please try again.") from exc


def validate_python_code(code):
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def purge_expired_projects():
    cutoff = datetime.utcnow() - PROJECT_TTL
    Project.query.filter(Project.created_at < cutoff).delete(synchronize_session=False)
    db.session.commit()


def purge_expired_cache():
    try:
        if "generation_cache" not in inspect(db.engine).get_table_names():
            current_app.logger.warning("Generation cache table is missing; skipping cache cleanup")
            return
        cutoff = datetime.utcnow() - CACHE_TTL
        GenerationCache.query.filter(GenerationCache.created_at < cutoff).delete(
            synchronize_session=False
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning("Cache cleanup skipped because the cache table is unavailable", exc_info=True)


def csrf_is_valid():
    return (
        current_app.config.get("TESTING")
        or request.headers.get("X-CSRF-Token") == session.get("csrf_token")
    )


def csrf_error():
    if not csrf_is_valid():
        return jsonify({"success": False, "error": "Invalid security token"}), 403
    return None


def session_project(project_id=None):
    current_id = session.get("current_project_id")
    if project_id and current_id != project_id:
        return None
    if not current_id:
        return None
    return Project.query.filter_by(project_id=current_id).first()


@main.route("/")
def home():
    session.setdefault("csrf_token", os.urandom(24).hex())
    return render_template("home.html")


@main.route("/generate")
def generator():
    project_id = request.args.get("project_id")
    project = session_project(project_id)
    extraction_error = None
    schema_preview = ""
    if project:
        session.setdefault("csrf_token", os.urandom(24).hex())
        session["current_project_id"] = project.project_id
        schema_preview = project.file_content[:5000]
        try:
            if project.extracted_tables is None:
                project.extracted_tables = extract_tables(project.file_content, project.file_extension)
                db.session.commit()
            tables = project.extracted_tables or []
        except GeminiError as exc:
            tables = []
            extraction_error = str(exc)
    else:
        tables = []
        project_id = None
    return render_template(
        "generator.html",
        tables=tables,
        project_id=project_id,
        extraction_error=extraction_error,
        schema_preview=schema_preview,
    )


@main.route("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "database": "ok"}), 200
    except Exception:
        db.session.rollback()
        current_app.logger.warning("Health check database query failed", exc_info=True)
        return jsonify({"status": "error", "database": "unavailable"}), 503


@main.route("/api/generate-code", methods=["POST"])
@limiter.limit("10 per minute")
def generate_code():
    error = csrf_error()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    table_name = data.get("table_name")
    method = data.get("method")
    auth_mode = data.get("auth_mode")
    language = data.get("language")
    output_mode = data.get("output_mode", "endpoint")
    project = session_project()

    if not all([table_name, method, auth_mode, language]):
        return jsonify({"success": False, "error": "Missing required parameters"}), 400
    if method not in SUPPORTED_METHODS or auth_mode not in SUPPORTED_AUTH_MODES:
        return jsonify({"success": False, "error": "Invalid method or authentication mode"}), 400
    if output_mode not in SUPPORTED_OUTPUT_MODES:
        return jsonify({"success": False, "error": "Invalid output mode"}), 400
    if not project:
        return jsonify({"success": False, "error": "Project not found or session expired"}), 404
    known_tables = project.extracted_tables or extract_tables_deterministically(
        project.file_content, project.file_extension
    )
    if known_tables and not any(table.lower() == table_name.lower() for table in known_tables):
        return jsonify({"success": False, "error": "Selected table was not found in the schema"}), 400
    generation_count = session.get("generation_count", 0)
    if generation_count >= SESSION_GENERATION_LIMIT:
        return jsonify({
            "success": False,
            "error": "Session generation limit reached. Upload a new schema to continue.",
        }), 429

    schema_context = schema_for_table(project.file_content, project.file_extension, table_name)
    cache_key = hashlib.sha256(
        "|".join([
            schema_context, table_name, method, auth_mode, language, output_mode
        ]).encode("utf-8")
    ).hexdigest()
    cache_available = "generation_cache" in inspect(db.engine).get_table_names()
    cached = (
        GenerationCache.query.filter_by(cache_key=cache_key).first()
        if cache_available
        else None
    )
    if cached:
        return jsonify({
            "success": True,
            "code": cached.code,
            "language": cached.language,
            "output_mode": output_mode,
            "syntax_valid": cached.syntax_valid,
            "cached": True,
        }), 200

    try:
        code = generate_api_code_with_gemini(
            table_name, method, auth_mode, language, schema_context, output_mode
        )
    except GeminiError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502
    session["generation_count"] = generation_count + 1

    syntax_valid = validate_python_code(code) if language in {"Flask", "Django", "FastAPI"} else None
    try:
        if not cache_available:
            current_app.logger.warning("Generation cache table is missing; returning uncached result")
            return jsonify({
                "success": True,
                "code": code,
                "language": language,
                "output_mode": output_mode,
                "syntax_valid": syntax_valid,
                "cached": False,
            }), 200
        db.session.add(GenerationCache(
            cache_key=cache_key,
            code=code,
            language=language,
            syntax_valid=syntax_valid,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({
        "success": True,
        "code": code,
        "language": language,
        "output_mode": output_mode,
        "syntax_valid": syntax_valid,
        "cached": False,
    }), 200


@main.route("/api/upload", methods=["POST"])
@limiter.limit("10 per hour")
def upload_file():
    error = csrf_error()
    if error:
        return error
    try:
        purge_expired_projects()
        purge_expired_cache()
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "error": "No file selected"}), 400
        if not allowed_file(file.filename):
            return jsonify({"success": False, "error": "File type not allowed"}), 400

        content = file.read()
        if len(content) > MAX_FILE_SIZE:
            return jsonify({"success": False, "error": "File size exceeds 5MB limit"}), 400
        try:
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"success": False, "error": "File must be UTF-8 encoded"}), 400

        filename = secure_filename(file.filename)
        extension = filename.rsplit(".", 1)[1].lower()
        old_project = session_project()
        if old_project:
            db.session.delete(old_project)
        project = Project(filename=filename, file_content=content_str, file_extension=extension)
        db.session.add(project)
        db.session.commit()
        session["current_project_id"] = project.project_id
        session["generation_count"] = 0
        return jsonify({
            "success": True,
            "project_id": project.project_id,
            "filename": project.filename,
            "message": "File uploaded successfully",
        }), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@main.route("/api/sample-upload", methods=["POST"])
@limiter.limit("10 per hour")
def sample_upload():
    error = csrf_error()
    if error:
        return error
    try:
        purge_expired_projects()
        purge_expired_cache()
        old_project = session_project()
        if old_project:
            db.session.delete(old_project)
        project = Project(
            filename="sample.sql",
            file_content=SAMPLE_SCHEMA,
            file_extension="sql",
            extracted_tables=["users", "posts"],
        )
        db.session.add(project)
        db.session.commit()
        session["current_project_id"] = project.project_id
        session["generation_count"] = 0
        return jsonify({
            "success": True,
            "project_id": project.project_id,
            "filename": project.filename,
            "message": "Sample schema loaded",
        }), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@main.route("/api/cleanup", methods=["POST"])
def cleanup_project():
    error = csrf_error()
    if error:
        return error
    project = session_project()
    if project:
        db.session.delete(project)
        db.session.commit()
    session.pop("current_project_id", None)
    return jsonify({"success": True, "message": "Cleanup successful"}), 200
