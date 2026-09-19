from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    filename = db.Column(db.String(255), nullable=False)
    file_content = db.Column(db.Text, nullable=False)
    file_extension = db.Column(db.String(10), nullable=False)
    extracted_tables = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'project_id': self.project_id,
            'filename': self.filename,
            'file_extension': self.file_extension,
            'extracted_tables': self.extracted_tables or [],
            'created_at': self.created_at.isoformat()
        }


class GenerationCache(db.Model):
    __tablename__ = "generation_cache"
    id = db.Column(db.Integer, primary_key=True)
    cache_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(100), nullable=False)
    syntax_valid = db.Column(db.Boolean, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
