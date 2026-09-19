import os
from io import BytesIO

import pytest

os.environ["FLASK_ENV"] = "testing"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app
from models.db import db


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.session.remove()
        db.drop_all()


def upload(client, filename="schema.sql", content=b"CREATE TABLE users (id INT);"):
    return client.post(
        "/api/upload",
        data={"file": (BytesIO(content), filename)},
        content_type="multipart/form-data",
    )
