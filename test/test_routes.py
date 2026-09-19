from unittest.mock import patch

from routes.route import GeminiError

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
