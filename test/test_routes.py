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
    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert "temporarily unavailable" in response.get_json()["error"]


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


def test_invalid_output_mode_is_rejected(client):
    assert upload(client).status_code == 201
    response = client.post(
        "/api/generate-code",
        json={
            "table_name": "users",
            "method": "GET",
            "auth_mode": "Token",
            "language": "FastAPI",
            "output_mode": "unknown",
        },
    )
    assert response.status_code == 400


def test_output_mode_is_sent_to_generator(client):
    assert upload(client).status_code == 201
    with patch(
        "routes.route.generate_api_code_with_gemini",
        return_value="def endpoint():\n    return {'ok': True}",
    ) as generate:
        response = client.post(
            "/api/generate-code",
            json={
                "table_name": "users",
                "method": "GET",
                "auth_mode": "Token",
                "language": "FastAPI",
                "output_mode": "tests",
            },
        )
    assert response.status_code == 200
    assert response.get_json()["output_mode"] == "tests"
    assert generate.call_args.args[-1] == "tests"


def test_ownership_verification_forbidden(client):
    upload_resp = upload(client)
    assert upload_resp.status_code == 201
    project_id = upload_resp.get_json()["project_id"]

    # User B uses a separate client session
    user_b_client = client.application.test_client()

    # User B should be forbidden (403) from reading User A's project
    resp_get = user_b_client.get(f"/api/project/{project_id}")
    assert resp_get.status_code == 403
    assert "Forbidden" in resp_get.get_json()["error"]

    # User B should be forbidden (403) from deleting User A's project
    resp_del = user_b_client.delete(f"/api/project/{project_id}")
    assert resp_del.status_code == 403
    assert "Forbidden" in resp_del.get_json()["error"]

    # User B should be forbidden (403) from cleaning up User A's project
    resp_cleanup = user_b_client.post(f"/api/cleanup/{project_id}")
    assert resp_cleanup.status_code == 403
    assert "Forbidden" in resp_cleanup.get_json()["error"]

    # User B should be forbidden (403) from viewing User A's project on /generate
    resp_gen = user_b_client.get(f"/generate?project_id={project_id}")
    assert resp_gen.status_code == 403


def test_ownership_verification_allowed(client):
    upload_resp = upload(client)
    assert upload_resp.status_code == 201
    project_id = upload_resp.get_json()["project_id"]

    # User A (owner) can read project
    resp_get = client.get(f"/api/project/{project_id}")
    assert resp_get.status_code == 200
    assert resp_get.get_json()["success"] is True
    assert resp_get.get_json()["project"]["project_id"] == project_id

    # User A (owner) can delete project
    resp_del = client.delete(f"/api/project/{project_id}")
    assert resp_del.status_code == 200
    assert resp_del.get_json()["success"] is True

    # After deletion, accessing it returns 404
    resp_after = client.get(f"/api/project/{project_id}")
    assert resp_after.status_code == 404


def test_project_not_found_returns_404(client):
    assert client.get("/api/project/nonexistent-id").status_code == 404
    assert client.delete("/api/project/nonexistent-id").status_code == 404


def test_sqlglot_table_extraction_standard_queries():
    from routes.route import extract_table_names

    sql = "CREATE TABLE users (id INT PRIMARY KEY); CREATE TABLE orders (id INT, user_id INT);"
    tables = extract_table_names(sql)
    assert tables == ["orders", "users"]


def test_sqlglot_table_extraction_joins():
    from routes.route import extract_table_names

    sql = """
    SELECT u.username, o.total, p.title
    FROM users u
    JOIN orders o ON u.id = o.user_id
    LEFT JOIN products p ON o.product_id = p.id;
    """
    tables = extract_table_names(sql)
    assert tables == ["orders", "products", "users"]


def test_sqlglot_table_extraction_subqueries():
    from routes.route import extract_table_names

    sql = "SELECT * FROM (SELECT id, balance FROM accounts WHERE active = 1) sub WHERE balance > 100;"
    tables = extract_table_names(sql)
    assert tables == ["accounts"]


def test_sqlglot_handles_invalid_sql_gracefully():
    from routes.route import extract_table_names

    tables = extract_table_names("THIS IS NOT VALID SQL AT ALL 12345!@#$")
    assert tables == []


def test_rate_limiter_blocks_sixth_call(rate_limited_client):
    upload_resp = upload(rate_limited_client)
    assert upload_resp.status_code == 201

    payload = {
        "table_name": "users",
        "method": "GET",
        "auth_mode": "Token",
        "language": "FastAPI",
    }

    with patch(
        "routes.route.generate_api_code_with_gemini",
        return_value="def get_users(): return []",
    ):
        # 5 calls per minute are allowed
        for i in range(5):
            resp = rate_limited_client.post("/api/generate-code", json=payload)
            assert resp.status_code == 200, f"Call {i+1} failed with status {resp.status_code}"

        # 6th call should be blocked with 429
        sixth_resp = rate_limited_client.post("/api/generate-code", json=payload)
        assert sixth_resp.status_code == 429
        data = sixth_resp.get_json()
        assert data["success"] is False
        assert "Rate limit exceeded" in data["error"]


def test_error_never_returned_as_code_comment(client):
    assert upload(client).status_code == 201
    # Test that Gemini returning an error string comment causes GeminiError -> HTTP 503, never 200
    with patch(
        "routes.route.get_gemini_client"
    ) as mock_gemini:
        mock_gemini.return_value.models.generate_content.return_value.text = "# Error generating code: API quota exceeded"
        response = client.post(
            "/api/generate-code",
            json={
                "table_name": "users",
                "method": "GET",
                "auth_mode": "Token",
                "language": "FastAPI",
            },
        )
    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert "code" not in response.get_json()
    assert "temporarily unavailable" in response.get_json()["error"]


def test_generate_code_rejects_empty_and_invalid_parameters(client):
    assert upload(client).status_code == 201

    # Empty payload
    resp = client.post("/api/generate-code", json={})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

    # Missing parameters
    resp = client.post(
        "/api/generate-code",
        json={"table_name": "users", "method": "GET"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

    # Invalid method
    resp = client.post(
        "/api/generate-code",
        json={
            "table_name": "users",
            "method": "INVALID_METHOD",
            "auth_mode": "Token",
            "language": "FastAPI",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_cleanup_explicit_with_project_id(client):
    upload_resp = upload(client)
    assert upload_resp.status_code == 201
    project_id = upload_resp.get_json()["project_id"]

    resp = client.post(f"/api/cleanup/{project_id}")
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    # Verifying project was deleted
    assert client.get(f"/api/project/{project_id}").status_code == 404
