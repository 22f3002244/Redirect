from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for, session
from models.db import db, Project
from werkzeug.utils import secure_filename
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

main = Blueprint("main", __name__)

# Configuration
ALLOWED_EXTENSIONS = {'sql', 'prisma', 'js', 'ts', 'py', 'java', 'json'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

# Initialize Gemini client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY missing. Please set it in your .env file.")

gemini_client = genai.Client(api_key=api_key)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_tables_with_gemini(file_content: str, file_extension: str) -> list:
    """Extract table names from various file formats using Gemini AI"""
    try:
        prompt = (
            f"Analyze the following {file_extension.upper()} database schema/model code and extract ONLY the table names.\n\n"
            "Rules:\n"
            "1. Return ONLY table names, separated by commas\n"
            "2. NO headers, NO markdown formatting, NO code blocks, NO explanations\n"
            "3. NO backticks, NO asterisks, NO numbering\n"
            "4. Just the raw table names separated by commas\n"
            "5. If no tables found, return empty string\n\n"
            f"Code:\n{file_content}"
        )

        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        # Parse response and clean up
        table_names_str = response.text.strip()
        
        if not table_names_str:
            return []
        
        # Split by comma and clean each table name
        tables = [name.strip() for name in table_names_str.split(',') if name.strip()]
        
        return tables

    except Exception as e:
        print(f"Error extracting tables with Gemini: {str(e)}")
        return []

def generate_api_code_with_gemini(table_name: str, method: str, auth_mode: str, language: str, file_content: str) -> str:
    """Generate API endpoint code using Gemini AI based on the database schema"""
    try:
        
        framework = language
        
        prompt = f"""You are an expert backend developer. Generate a complete, production-ready API endpoint code.

**Requirements:**
- Table: {table_name}
- HTTP Method: {method}
- Authentication: {auth_mode}
- Language/Framework: {framework}

**Database Schema:**
{file_content}

**Instructions:**
1. Generate ONLY the function code, NO explanations, NO markdown formatting, NO code block markers
2. Comment out all imports at the top
3. Do NOT include route decorators (@router.get, @app.route, etc.) - only the function definition
4. Assume database session is configured as 'SessionLocal()' or 'Session()'
5. Implement {auth_mode} authentication check within the function
6. Add proper error handling with try-except blocks
7. For {method} method, implement the appropriate CRUD operation for {table_name} table
8. Use {language} framework/language
9. Return JSON responses with 'success', 'message', and 'data' fields
10. Include appropriate HTTP status codes
11. Always close database connections in finally block
12. Do NOT include docstrings or comments explaining the code
13. Return ONLY the raw function code without any decorators that can be directly copied and used

Generate the complete endpoint code now:"""

        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        
        # Clean up response - remove markdown code blocks if present
        code = response.text.strip()
        
        # Remove markdown code fences if present
        if code.startswith('```'):
            lines = code.split('\n')
            # Remove first line (```language)
            lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            code = '\n'.join(lines)
        
        return code

    except Exception as e:
        return f"# Error generating code: {str(e)}\n# Please try again or check your API key configuration."

@main.route('/')
def home():
    return render_template("home.html")

@main.route('/generate')
def generator():
    """Render generator page with table names from uploaded file"""
    tables = []
    project_id = request.args.get('project_id')
    
    if project_id:
        # Get project from database
        project = Project.query.filter_by(project_id=project_id).first()
        
        if project:
            # Use Gemini to extract table names from any file type
            tables = extract_tables_with_gemini(project.file_content, project.file_extension)
            # Store project_id in session for cleanup tracking
            session['current_project_id'] = project_id
    
    return render_template("generator.html", tables=tables, project_id=project_id)

@main.route('/api/generate-code', methods=['POST'])
def generate_code():
    """Generate API code using Gemini AI"""
    try:
        data = request.get_json()
        
        table_name = data.get('table_name')
        method = data.get('method')
        auth_mode = data.get('auth_mode')
        language = data.get('language')
        project_id = data.get('project_id')
        
        # Validation
        if not all([table_name, method, auth_mode, language, project_id]):
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400
        
        # Get project to access file content
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({
                'success': False,
                'error': 'Project not found'
            }), 404
        
        # Generate code using Gemini
        generated_code = generate_api_code_with_gemini(
            table_name=table_name,
            method=method,
            auth_mode=auth_mode,
            language=language,
            file_content=project.file_content
        )
        
        return jsonify({
            'success': True,
            'code': generated_code,
            'language': language
        }), 200
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main.route('/api/upload', methods=['POST'])
def upload_file():
    """Handle file upload and create anonymous project"""
    try:
        # Clean up old project if exists in session
        old_project_id = session.get('current_project_id')
        if old_project_id:
            old_project = Project.query.filter_by(project_id=old_project_id).first()
            if old_project:
                db.session.delete(old_project)
                db.session.commit()
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed'}), 400
        
        # Read file content
        file_content = file.read()
        
        # Check file size
        if len(file_content) > MAX_FILE_SIZE:
            return jsonify({'success': False, 'error': 'File size exceeds 5MB limit'}), 400
        
        # Decode content
        try:
            content_str = file_content.decode('utf-8')
        except UnicodeDecodeError:
            return jsonify({'success': False, 'error': 'File must be UTF-8 encoded'}), 400
        
        # Get file extension
        filename = secure_filename(file.filename)
        file_extension = filename.rsplit('.', 1)[1].lower()
        
        # Create new project with anonymous ID
        project = Project(
            filename=filename,
            file_content=content_str,
            file_extension=file_extension
        )
        
        db.session.add(project)
        db.session.commit()
        
        # Store new project_id in session
        session['current_project_id'] = project.project_id
        
        return jsonify({
            'success': True,
            'project_id': project.project_id,
            'filename': project.filename,
            'message': 'File uploaded successfully'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/project/<project_id>', methods=['GET'])
def get_project(project_id):
    """Retrieve project data by anonymous project ID"""
    try:
        project = Project.query.filter_by(project_id=project_id).first()
        
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        
        return jsonify({
            'success': True,
            'project': {
                'project_id': project.project_id,
                'filename': project.filename,
                'file_content': project.file_content,
                'file_extension': project.file_extension,
                'created_at': project.created_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/cleanup', methods=['POST'])
def cleanup_project():
    """Clean up project when browser is closed or user leaves"""
    try:
        project_id = session.get('current_project_id')
        
        if project_id:
            project = Project.query.filter_by(project_id=project_id).first()
            if project:
                db.session.delete(project)
                db.session.commit()
            
            # Clear session
            session.pop('current_project_id', None)
        
        return jsonify({'success': True, 'message': 'Cleanup successful'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500