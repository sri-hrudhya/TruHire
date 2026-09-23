def test_register_user_success(client):
    payload = {
        "email": "sarah.connor@example.com",
        "name": "Sarah Connor",
        "password": "ResistancePassword2026!"
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "sarah.connor@example.com"
    assert data["user"]["name"] == "Sarah Connor"


def test_register_duplicate_email(client, test_user):
    payload = {
        "email": test_user.email,
        "name": "Duplicate User",
        "password": "Password123!"
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_login_success(client, test_user):
    payload = {
        "email": "test_recruiter@truhire.io",
        "password": "SecretPassword123!"
    }
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == test_user.email


def test_login_wrong_password(client, test_user):
    payload = {
        "email": test_user.email,
        "password": "WrongPassword999!"
    }
    response = client.post("/api/auth/login", json=payload)
    assert response.status_code == 401


def test_get_current_user_profile(client, auth_headers, test_user):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == test_user.id
    assert response.json()["email"] == test_user.email


def test_unauthenticated_request_rejected(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
