"""fire through the full API stack
and test auth, rate limiting, protected routes, event submission,
incident workflow, entity history, and correlation"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import sys
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app

client = TestClient(app)

#helpers 

def register_user(username: str, password: str, role: str = "viewer"):
    return client.post("/auth/register", json={
        "username": username,
        "password": password,
        "role": role,
    })

def login_user(username: str, password: str) -> str | None:
    resp = client.post("/auth/login", json={
        "username": username,
        "password": password,
    })
    if resp.status_code == 200:
        return resp.json()["access_token"]
    return None


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

ACTIVITY_PAYLOAD = {
    "username":      "alice",
    "ip_address":    "203.0.113.99",
    "timestamp":     "2024-11-01T02:15:00",
    "failed_logins": 8,
    "command":       "cat /etc/passwd",
}

TRANSACTION_PAYLOAD = {
    "account_id":      "alice",
    "amount":          50000.00,
    "currency":        "ZAR",
    "location":        "London",
    "last_location":   "Johannesburg",
    "device_id":       "device-new",
    "known_devices":   ["device-trusted"],
    "recent_tx_count": 5,
    "timestamp":       "2024-11-01T02:15:00",
    "username":        "alice",
    "ip_address":      "203.0.113.99",
}

# fixtures 
@pytest.fixture(scope="module")
def admin_token():
    register_user("test_admin", "adminpass123", "admin")
    token = login_user("test_admin", "adminpass123")
    assert token is not None
    return token


@pytest.fixture(scope="module")
def viewer_token():
    register_user("test_viewer", "viewerpass123", "viewer")
    token = login_user("test_viewer", "viewerpass123")
    assert token is not None
    return token

# make a real incident and return its ID for workflow test
@pytest.fixture(scope="module")
def incident_id(admin_token):
    resp = client.post(
        "/events/activity",
        json=ACTIVITY_PAYLOAD,
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    inc_id = resp.json().get("id")
    assert inc_id is not None
    return inc_id

# auth tests
class TestAuth:

    def test_register_success(self):
        username = f"new_user_{uuid.uuid4().hex[:8]}"
        resp = register_user(username, "password123", "viewer")
        assert resp.status_code == 201
        assert "created" in resp.json()["message"]

    def test_register_duplicate_username(self):
        register_user("duplicate_user", "password123")
        resp = register_user("duplicate_user", "password123")
        assert resp.status_code == 409

    def test_login_success(self):
        register_user("login_test_user", "password123", "viewer")
        resp = client.post("/auth/login", json={
            "username": "login_test_user",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["role"] == "viewer"

    def test_login_wrong_password(self):
        register_user("login_test_user2", "correctpass")
        resp = client.post("/auth/login", json={
            "username": "login_test_user2",
            "password": "wrongpass",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self):
        resp = client.post("/auth/login", json={
            "username": "nobody",
            "password": "password",
        })
        assert resp.status_code == 401

# protected route tests 
class TestProtectedRoutes:

    def test_activity_without_token_returns_401(self):
        resp = client.post("/events/activity", json=ACTIVITY_PAYLOAD)
        assert resp.status_code == 401

    def test_transaction_without_token_returns_401(self):
        resp = client.post("/events/transaction", json=TRANSACTION_PAYLOAD)
        assert resp.status_code == 401

    def test_incidents_without_token_returns_401(self):
        resp = client.get("/incidents/")
        assert resp.status_code == 401

    def test_viewer_cannot_submit_activity(self, viewer_token):
        resp = client.post(
            "/events/activity",
            json=ACTIVITY_PAYLOAD,
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403

    def test_viewer_cannot_submit_transaction(self, viewer_token):
        resp = client.post(
            "/events/transaction",
            json=TRANSACTION_PAYLOAD,
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403

    def test_viewer_can_read_incidents(self, viewer_token):
        resp = client.get(
            "/incidents/",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200

    def test_invalid_token_returns_401(self):
        resp = client.get(
            "/incidents/",
            headers={"Authorization": "Bearer totallynotavalidtoken"},
        )
        assert resp.status_code == 401

# event submission tests
class TestEventSubmission:

    def test_submit_activity_event(self, admin_token):
        resp = client.post(
            "/events/activity",
            json=ACTIVITY_PAYLOAD,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
        assert "alert_level" in data
        assert "reasons" in data
        assert "explanations" in data
        assert "severity_rationale" in data
        assert data["id"] is not None

    def test_submit_transaction_event(self, admin_token):
        resp = client.post(
            "/events/transaction",
            json=TRANSACTION_PAYLOAD,
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "risk_score" in data
        assert data["risk_score"] >= 0

    def test_activity_high_risk_flags(self, admin_token):
        resp = client.post(
            "/events/activity",
            json=ACTIVITY_PAYLOAD,
            headers=auth_header(admin_token),
        )
        data = resp.json()
        assert data["alert_level"] in ("MEDIUM", "HIGH", "CRITICAL")
        assert len(data["reasons"]) > 0
        assert len(data["explanations"]) > 0

    def test_activity_invalid_payload_returns_422(self, admin_token):
        resp = client.post(
            "/events/activity",
            json={"username": "alice"},  # missing required fields
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 422

# add incident workflow tests

class TestIncidentWorkflow:

    def test_list_incidents(self, viewer_token):
        resp = client.get("/incidents/", headers=auth_header(viewer_token))
        assert resp.status_code == 200
        data = resp.json()
        assert "incidents" in data
        assert "count" in data

    def test_get_incident_by_id(self, viewer_token, incident_id):
        resp = client.get(
            f"/incidents/{incident_id}",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == incident_id
        assert "state" in data

    def test_get_nonexistent_incident_returns_404(self, viewer_token):
        resp = client.get("/incidents/999999", headers=auth_header(viewer_token))
        assert resp.status_code == 404

    def test_update_incident_state(self, admin_token, incident_id):
        resp = client.patch(
            f"/incidents/{incident_id}/state",
            json={"state": "investigating"},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "investigating"
        assert data["updated_by"] == "test_admin"

    def test_update_incident_severity(self, admin_token, incident_id):
        resp = client.patch(
            f"/incidents/{incident_id}/severity",
            json={"severity": "CRITICAL"},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["severity"] == "CRITICAL"

    def test_viewer_cannot_update_state(self, viewer_token, incident_id):
        resp = client.patch(
            f"/incidents/{incident_id}/state",
            json={"state": "resolved"},
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 403

    def test_invalid_state_returns_422(self, admin_token, incident_id):
        resp = client.patch(
            f"/incidents/{incident_id}/state",
            json={"state": "banana"},
            headers=auth_header(admin_token),
        )
        assert resp.status_code == 422

    def test_incident_history_recorded(self, viewer_token, incident_id):
        resp = client.get(
            f"/incidents/{incident_id}/history",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        entry = data["history"][0]
        assert "changed_by" in entry
        assert "old_value" in entry
        assert "new_value" in entry
        assert "timestamp" in entry

# entiry history

class TestEntityHistory:

    def test_user_history_found(self, viewer_token):
        resp = client.get(
            "/entities/users/alice",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert "stats" in data
        assert "total_incidents" in data["stats"]
        assert "average_score" in data["stats"]

    def test_user_history_not_found(self, viewer_token):
        resp = client.get(
            "/entities/users/nobody_exists_xyz",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 404
    def test_ip_history_found(self, viewer_token):
        resp = client.get(
            "/entities/ips/203.0.113.99",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1

# correlations tests 
class TestCorrelations:

    def test_correlations_returns_200(self, viewer_token):
        resp = client.get(
            "/correlations/",
            headers=auth_header(viewer_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "window_minutes" in data
        assert "group_count" in data
        assert "correlations" in data
    def test_correlations_structure(self, viewer_token):
        resp = client.get(
            "/correlations/",
            headers=auth_header(viewer_token),
        )
        data = resp.json()
        assert data["window_minutes"] == 60
        if data["group_count"] > 0:
            group = data["correlations"][0]
            assert "correlation_type" in group
            assert "entity" in group
            assert "incident_ids" in group
            assert "summary" in group

# health and status tests
class TestStatus:

    def test_root_returns_200(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Sentinel"
        assert data["status"] == "running"

    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"