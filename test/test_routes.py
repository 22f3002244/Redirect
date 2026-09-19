from unittest.mock import patch

from routes.route import GeminiError, schema_for_table

from conftest import upload


def test_upload_rejects_bad_extension(client):
    response = upload(client, "schema.txt")
    assert response.status_code == 400
    assert response.get_json()["error"] == "File type not allowed"


def test_upload_rejects_non_utf8(client):
    response = upload(client, content=b"\xff\xfe")
    assert response.status_code == 400
    assert response.get_json()["error"] == "File must be UTF-8 encoded"


def test_upload_rejects_files_over_5_mb(client):
    response = upload(client, content=b"x" * (5 * 1024 * 1024 + 1))
    assert response.status_code == 400
    assert response.get_json()["error"] == "File size exceeds 5MB limit"


def test_generation_requires_the_session_project(client):
    response = client.post(
        "/api/generate-code",
        json={
            "table_name": "users",
            "method": "GET",
            "auth_mode": "Token",
            "language": "FastAPI",
        },
    )
    assert response.status_code == 404


def test_project_read_endpoint_is_not_exposed(client):
    response = client.get("/api/project/unknown")
    assert response.status_code == 404


def test_gemini_failure_is_a_gateway_error(client):
    assert upload(client).status_code == 201
    with patch("routes.route.generate_api_code_with_gemini", side_effect=GeminiError("AI unavailable")):
        response = client.post(
            "/api/generate-code",
            json={
                "table_name": "users",
                "method": "GET",
                "auth_mode": "Token",
                "language": "FastAPI",
            },
        )
    assert response.status_code == 502
    assert response.get_json()["success"] is False


def test_sql_tables_are_extracted_without_gemini(client):
    assert upload(client).status_code == 201
    with patch("routes.route.get_gemini_client") as gemini:
        response = client.get("/generate")
    assert response.status_code == 200
    gemini.assert_not_called()


def test_sql_prompt_context_is_limited_to_selected_and_related_tables():
    schema = """
    CREATE TABLE users (id INT PRIMARY KEY);
    CREATE TABLE posts (id INT, user_id INT, FOREIGN KEY (user_id) REFERENCES users(id));
    CREATE TABLE audit_log (id INT, message TEXT);
    """
    context = schema_for_table(schema, "sql", "users")
    assert "CREATE TABLE users" in context
    assert "CREATE TABLE posts" in context
    assert "audit_log" not in context


def test_health_endpoint_checks_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}


def test_generated_code_is_persisted_in_cache(client):
    assert upload(client).status_code == 201
    with patch(
        "routes.route.generate_api_code_with_gemini",
        return_value="def endpoint():\n    return {'ok': True}",
    ) as generate:
        payload = {
            "table_name": "users",
            "method": "GET",
            "auth_mode": "Token",
            "language": "FastAPI",
        }
        first = client.post("/api/generate-code", json=payload)
        second = client.post("/api/generate-code", json=payload)
    assert first.get_json()["cached"] is False
    assert second.get_json()["cached"] is True
    generate.assert_called_once()


def test_sample_upload_creates_a_project(client):
    response = client.post("/api/sample-upload")
    assert response.status_code == 201
    assert response.get_json()["filename"] == "sample.sql"


def test_generation_rejects_unknown_table(client):
    assert upload(client).status_code == 201
    response = client.post(
        "/api/generate-code",
        json={
            "table_name": "unknown",
            "method": "GET",
            "auth_mode": "Token",
            "language": "FastAPI",
        },
    )
    assert response.status_code == 400


def test_sample_upload_tolerates_missing_generation_cache_table(client):
    from models.db import GenerationCache, db

    with client.application.app_context():
        GenerationCache.__table__.drop(db.engine)
    response = client.post("/api/sample-upload")
    assert response.status_code == 201


def test_cache_cleanup_tolerates_database_schema_errors(client):
    from routes.route import purge_expired_cache
    from sqlalchemy.exc import SQLAlchemyError

    with client.application.app_context():
        with patch("routes.route.inspect") as inspect_mock:
            inspect_mock.return_value.get_table_names.return_value = ["generation_cache"]
            with patch("routes.route.GenerationCache.query") as query:
                query.filter.side_effect = SQLAlchemyError("missing table")
                purge_expired_cache()


def test_gemini_model_can_be_configured(client, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    with patch("routes.route.get_gemini_client") as get_client:
        get_client.return_value.models.generate_content.return_value.text = "users"
        from routes.route import extract_tables_with_gemini

        extract_tables_with_gemini("schema", "sql")
        get_client.return_value.models.generate_content.assert_called_once()
        assert get_client.return_value.models.generate_content.call_args.kwargs["model"] == "test-model"
