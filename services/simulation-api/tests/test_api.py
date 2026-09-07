"""Transport-layer tests: the calibration gate must hold at the API boundary."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulation-api" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "physics-core" / "src"))

from cathsim_api.app import app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health_carries_the_research_only_disclaimer(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["disclaimer"] == "Research prototype - Not for clinical use."
    assert body["schema_version"] == "0.1.0"


def test_profiles_expose_calibration_status(client: TestClient) -> None:
    profiles = {entry["name"]: entry for entry in client.get("/profiles").json()}
    generic = profiles["generic-steerable-rf.json"]["calibration"]
    assert generic["ready_for_simulation"] is False
    assert "material.youngs_modulus_mpa" in generic["missing_fields"]
    demo = profiles["demo-steerable-rf.json"]["calibration"]
    assert demo["is_demo_profile"] is True


def test_uncalibrated_profile_is_refused(client: TestClient) -> None:
    response = client.post(
        "/simulate/static?profile=generic-steerable-rf.json",
        json={"actuation": {}, "settings": {"dt_s": 0.033}},
    )
    assert response.status_code == 422
    assert "CALIBRATION_REQUIRED" in response.json()["detail"]


def test_demo_profile_needs_explicit_consent(client: TestClient) -> None:
    response = client.post(
        "/simulate/static?profile=demo-steerable-rf.json",
        json={"actuation": {}, "settings": {"dt_s": 0.033}},
    )
    assert response.status_code == 422
    assert "DEMO" in response.json()["detail"]


def test_unknown_profile_returns_a_helpful_404(client: TestClient) -> None:
    response = client.post(
        "/simulate/static?profile=does-not-exist.json",
        json={"actuation": {}, "settings": {"dt_s": 0.033}},
    )
    assert response.status_code == 404
    assert "GET /profiles" in response.json()["detail"]


def test_static_solve_matches_the_reference_equilibrium(client: TestClient) -> None:
    response = client.post(
        "/simulate/static?profile=demo-steerable-rf.json",
        json={
            "actuation": {
                "insertion_mm": 100.0,
                "axial_rotation_rad": 0.0,
                "steer_x": 1.0,
                "steer_y": 0.0,
                "deployment": 0.0,
            },
            "settings": {"dt_s": 0.033, "accept_demo_parameters": True},
        },
    )
    assert response.status_code == 200
    frame = response.json()
    assert len(frame["centerline_mm"]) == 71
    tip = frame["centerline_mm"][-1]
    # Same equilibrium as tests/reference-data/rod-reference-cases.json.
    assert tip[1] == pytest.approx(44.7631, abs=1e-2)
    assert tip[2] == pytest.approx(74.7406, abs=1e-2)
    assert frame["solver"]["converged"] is True


def test_out_of_range_actuation_is_rejected_by_the_schema(client: TestClient) -> None:
    response = client.post(
        "/simulate/static?profile=demo-steerable-rf.json",
        json={"actuation": {"steer_x": 5.0}, "settings": {"dt_s": 0.033}},
    )
    assert response.status_code == 422


def test_contact_metrics_are_honestly_unavailable(client: TestClient) -> None:
    body = client.get("/contact-metrics").json()
    assert body["available"] is False
    assert "Milestone 2" in body["reason"]
