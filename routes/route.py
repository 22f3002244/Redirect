import ast
import os
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Blueprint, jsonify, render_template, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from google import genai
from werkzeug.utils import secure_filename

from models.db import Project, db

load_dotenv()

main = Blueprint("main", __name__)
limiter = Limiter(key_func=get_remote_address, default_limits=[])

ALLOWED_EXTENSIONS = {"sql", "prisma", "js", "ts", "py", "java", "json"}
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_AI_INPUT_SIZE = 200_000
PROJECT_TTL = timedelta(hours=24)
SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
SUPPORTED_AUTH_MODES = {
    "Session",
    "Token",
    "OAuth (Google/GitHub login)",
    "API Keys",
}


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
            model="gemini-2.5-flash", contents=prompt
        )
        return [name.strip() for name in response.text.split(",") if name.strip()]
    except Exception as exc:
        raise GeminiError("The AI service could not extract tables. Please try again.") from exc


def extract_tables(file_content, file_extension):
    tables = extract_tables_deterministically(file_content, file_extension)
    return tables or extract_tables_with_gemini(file_content, file_extension)


def generate_api_code_with_gemini(table_name, method, auth_mode, language, file_content):
    if len(file_content) > MAX_AI_INPUT_SIZE:
        raise GeminiError(
            "This schema is too large to process on the free-tier server. "
            "Please upload a schema smaller than 200,000 characters."
        )
    prompt = f"""You are an expert backend developer. Generate a production-ready API endpoint function.
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
            model="gemini-2.5-flash", contents=prompt
        )
        code = response.text.strip()
        if code.startswith("```"):
            lines = code.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            code = "\n".join(lines).strip()
        return code
    except Exception as exc:
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


def session_project(project_id=None):
    current_id = session.get("current_project_id")
    if project_id and current_id != project_id:
        return None
    if not current_id:
        return None
    return Project.query.filter_by(project_id=current_id).first()


@main.route("/")
def home():
    return render_template("home.html")


@main.route("/generate")
def generator():
    project_id = request.args.get("project_id")
    project = session_project(project_id)
    if project:
        session["current_project_id"] = project.project_id
        try:
            if project.extracted_tables is None:
                project.extracted_tables = extract_tables(project.file_content, project.file_extension)
                db.session.commit()
            tables = project.extracted_tables or []
        except GeminiError:
            tables = []
    else:
        tables = []
        project_id = None
    return render_template("generator.html", tables=tables, project_id=project_id)


@main.route("/api/generate-code", methods=["POST"])
@limiter.limit("10 per minute")
def generate_code():
    data = request.get_json(silent=True) or {}
    table_name = data.get("table_name")
    method = data.get("method")
    auth_mode = data.get("auth_mode")
    language = data.get("language")
    project = session_project()

    if not all([table_name, method, auth_mode, language]):
        return jsonify({"success": False, "error": "Missing required parameters"}), 400
    if method not in SUPPORTED_METHODS or auth_mode not in SUPPORTED_AUTH_MODES:
        return jsonify({"success": False, "error": "Invalid method or authentication mode"}), 400
    if not project:
        return jsonify({"success": False, "error": "Project not found or session expired"}), 404

    try:
        code = generate_api_code_with_gemini(
            table_name, method, auth_mode, language, project.file_content
        )
    except GeminiError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502

    return jsonify({
        "success": True,
        "code": code,
        "language": language,
        "syntax_valid": validate_python_code(code) if language in {"Flask", "Django", "FastAPI"} else None,
    }), 200


@main.route("/api/upload", methods=["POST"])
@limiter.limit("10 per hour")
def upload_file():
    try:
        purge_expired_projects()
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
        return jsonify({
            "success": True,
            "project_id": project.project_id,
            "filename": project.filename,
            "message": "File uploaded successfully",
        }), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@main.route("/api/cleanup", methods=["POST"])
def cleanup_project():
    project = session_project()
    if project:
        db.session.delete(project)
        db.session.commit()
    session.pop("current_project_id", None)
    return jsonify({"success": True, "message": "Cleanup successful"}), 200
