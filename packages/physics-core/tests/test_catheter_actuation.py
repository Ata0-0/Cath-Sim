"""GenericSteerableRF actuation and calibration-gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from cathsim_physics import (
    ActuationInput,
    ConfigError,
    EntryPose,
    GenericSteerableRF,
    calibration_status,
    load_profile,
    material_from_profile,
)


@pytest.fixture
def demo_profile(repo_root: Path) -> dict:
    return load_profile(repo_root / "configs" / "demo-steerable-rf.json")


@pytest.fixture
def catheter(demo_profile: dict) -> GenericSteerableRF:
    model = GenericSteerableRF()
    model.load_parameters(demo_profile, accept_demo_parameters=True)
    model.initialize(EntryPose(np.zeros(3), np.array([0.0, 0.0, 1.0])))
    return model


# -- calibration gate --------------------------------------------------------


def test_uncalibrated_profile_blocks_simulation(repo_root: Path) -> None:
    profile = load_profile(repo_root / "configs" / "generic-steerable-rf.json")
    status = calibration_status(profile)
    assert not status.ready_for_simulation
    assert status.material_source == "CALIBRATION_REQUIRED"
    with pytest.raises(ConfigError, match="CALIBRATION_REQUIRED"):
        material_from_profile(profile)


def test_demo_profile_requires_explicit_consent(demo_profile: dict) -> None:
    with pytest.raises(ConfigError, match="DEMO"):
        material_from_profile(demo_profile)
    assert material_from_profile(demo_profile, accept_demo_parameters=True) is not None


def test_unknown_schema_version_is_rejected(tmp_path: Path, demo_profile: dict) -> None:
    demo_profile["schema_version"] = "9.9.9"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(demo_profile))
    with pytest.raises(ConfigError, match="schema_version"):
        load_profile(path)


# -- actuation ---------------------------------------------------------------


def test_straight_catheter_stays_straight(catheter: GenericSteerableRF) -> None:
    catheter.set_insertion(80.0)
    catheter.solve_static()
    nodes = catheter.state.nodes_mm
    lateral = np.linalg.norm(nodes[:, :2], axis=1)
    assert float(lateral.max()) < 1.0e-6
    assert catheter.state.nodes_mm[-1, 2] == pytest.approx(80.0, rel=1.0e-4)


def test_steering_bends_only_the_distal_active_length(catheter: GenericSteerableRF) -> None:
    insertion_mm = 100.0
    active_mm = catheter.profile["geometry"]["active_length_mm"]
    catheter.set_insertion(insertion_mm)
    catheter.set_steering(1.0, 0.0)
    catheter.solve_static()

    nodes = catheter.state.nodes_mm
    element_mm = insertion_mm / (nodes.shape[0] - 1)
    arclength_mm = np.arange(nodes.shape[0]) * element_mm
    proximal = arclength_mm < (insertion_mm - active_mm) - 2.0 * element_mm

    lateral_mm = np.linalg.norm(nodes[:, :2], axis=1)
    print(
        f"\n[actuation] insertion={insertion_mm} mm, active={active_mm} mm, "
        f"tip lateral offset={lateral_mm[-1]:.2f} mm, "
        f"max proximal lateral offset={lateral_mm[proximal].max():.2e} mm"
    )
    # The passive proximal shaft carries no rest curvature and no external load,
    # so it must remain straight.
    assert float(lateral_mm[proximal].max()) < 1.0e-6
    # The distal section must actually deflect.
    assert float(lateral_mm[-1]) > 0.1 * active_mm


def test_steering_magnitude_follows_the_configured_gain(catheter: GenericSteerableRF) -> None:
    """Total tip turn angle must equal gain * input * active length."""
    gain_rad_per_mm = catheter.profile["actuation"]["steer_gain_rad_per_mm"]
    active_mm = catheter.profile["geometry"]["active_length_mm"]
    catheter.set_insertion(100.0)
    catheter.set_steering(1.0, 0.0)
    catheter.solve_static()

    nodes = catheter.state.nodes_mm
    entry_tangent = np.array([0.0, 0.0, 1.0])
    tip_tangent = nodes[-1] - nodes[-2]
    tip_tangent /= np.linalg.norm(tip_tangent)
    turn_rad = float(np.arccos(np.clip(np.dot(entry_tangent, tip_tangent), -1.0, 1.0)))
    expected_rad = gain_rad_per_mm * active_mm

    error = abs(turn_rad - expected_rad) / expected_rad
    print(
        f"\n[actuation gain] turn_num={turn_rad:.4f} rad  "
        f"turn_expected=gain*L_active={expected_rad:.4f} rad  err={error * 100:.2f} %"
    )
    # The free distal section adopts its rest curvature; the residual gap is the
    # half-element at each end of the actuated span (documented in V2).
    assert error < 0.05


def test_axial_rotation_rolls_the_steering_plane(catheter: GenericSteerableRF) -> None:
    catheter.set_insertion(100.0)
    catheter.set_steering(1.0, 0.0)
    catheter.solve_static()
    tip_unrolled = catheter.state.nodes_mm[-1].copy()

    catheter.set_axial_rotation(np.pi / 2.0)
    catheter.solve_static()
    tip_rolled = catheter.state.nodes_mm[-1].copy()

    lateral_before = tip_unrolled[:2]
    lateral_after = tip_rolled[:2]
    angle_before = float(np.arctan2(lateral_before[1], lateral_before[0]))
    angle_after = float(np.arctan2(lateral_after[1], lateral_after[0]))
    delta = (angle_after - angle_before + np.pi) % (2.0 * np.pi) - np.pi

    print(
        f"\n[axial rotation] steering plane rotated by {np.degrees(delta):.2f} deg "
        f"for a 90 deg handle roll; |lateral| {np.linalg.norm(lateral_before):.2f} -> "
        f"{np.linalg.norm(lateral_after):.2f} mm"
    )
    assert abs(delta - np.pi / 2.0) < np.radians(5.0)
    # Rolling must not change how far the tip is deflected.
    assert np.linalg.norm(lateral_after) == pytest.approx(np.linalg.norm(lateral_before), rel=0.05)


def test_insertion_changes_the_deployed_length(catheter: GenericSteerableRF) -> None:
    for insertion_mm in (40.0, 80.0, 120.0):
        catheter.set_insertion(insertion_mm)
        catheter.solve_static()
        nodes = catheter.state.nodes_mm
        arclength_mm = float(np.sum(np.linalg.norm(np.diff(nodes, axis=0), axis=1)))
        assert arclength_mm == pytest.approx(insertion_mm, rel=1.0e-3)


def test_non_finite_actuation_is_rejected() -> None:
    with pytest.raises(ValueError, match="NaN or Inf"):
        ActuationInput(insertion_mm=float("nan")).validated(1.0)


def test_steering_input_is_clamped_to_the_configured_range() -> None:
    clamped = ActuationInput(steer_x=5.0, steer_y=-3.0, deployment=2.0).validated(1.0)
    assert clamped.steer_x == 1.0
    assert clamped.steer_y == -1.0
    assert clamped.deployment == 1.0


def test_render_geometry_matches_the_simulation_frame_contract(
    catheter: GenericSteerableRF,
) -> None:
    catheter.set_insertion(80.0)
    catheter.step(1.0 / 60.0)
    frame = catheter.get_render_geometry()
    assert set(frame) >= {
        "time_s",
        "centerline_mm",
        "orientations_xyzw",
        "electrodes",
        "contacts",
        "solver",
    }
    assert len(frame["centerline_mm"]) == catheter.state.n_nodes
    assert len(frame["orientations_xyzw"]) == catheter.state.n_edges
    assert len(frame["electrodes"]) == catheter.profile["electrodes"]["count"]
    assert set(frame["solver"]) >= {
        "iterations",
        "residual",
        "max_penetration_mm",
        "converged",
    }
    for quaternion in frame["orientations_xyzw"]:
        assert np.linalg.norm(quaternion) == pytest.approx(1.0, abs=1.0e-9)
