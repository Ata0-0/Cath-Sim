#!/usr/bin/env python3
"""Generate golden reference data from the Python reference rod solver.

The TypeScript real-time solver in ``apps/viewer`` is a port of the same
discrete elastic rod.  Its unit tests replay the scenarios written here and
compare centrelines, which is the Python <-> TypeScript counterpart of the
Python <-> C++ parity test planned for Milestone 3 (V9).

Regenerate with::

    python scripts/generate_reference_data.py

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "physics-core" / "src"))

from cathsim_physics import (  # noqa: E402
    EntryPose,
    ExternalLoads,
    GenericSteerableRF,
    RodMaterial,
    RodSolver,
    SolverSettings,
    load_profile,
    straight_rod,
)
from cathsim_physics.units import (  # noqa: E402
    circular_area_mm2,
    circular_polar_moment_mm4,
    circular_second_moment_mm4,
    shear_modulus_mpa,
)

OUTPUT = REPO_ROOT / "tests" / "reference-data"
FINE = SolverSettings(max_iterations=40000, gradient_tolerance_n=1.0e-9, history_size=150)


def cantilever_case() -> dict:
    """Clamped-free beam with a transverse tip load (mirrors validation V1)."""
    length_mm, n_nodes = 100.0, 41
    youngs_mpa, diameter_mm, poisson = 3.0, 2.5, 0.4
    bending = youngs_mpa * circular_second_moment_mm4(diameter_mm)
    torsional = shear_modulus_mpa(youngs_mpa, poisson) * circular_polar_moment_mm4(diameter_mm)
    axial = youngs_mpa * circular_area_mm2(diameter_mm)
    tip_force_n = 3.0 * bending * (0.01 * length_mm) / length_mm**3

    material = RodMaterial(bending, torsional, axial, 1.0e-6, 1.0e-6)
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], length_mm, n_nodes)
    loads = ExternalLoads(node_forces_n=np.zeros((n_nodes, 3)))
    loads.node_forces_n[-1] = [0.0, 0.0, tip_force_n]
    solved, report = RodSolver(material, rest, settings=FINE).solve_static(state, loads)

    return {
        "name": "cantilever_tip_load",
        "description": (
            "Clamped-free beam, transverse tip force. Analytic tip deflection F L^3 / (3 EI)."
        ),
        "input": {
            "length_mm": length_mm,
            "n_nodes": n_nodes,
            "bending_stiffness_n_mm2": bending,
            "torsional_stiffness_n_mm2": torsional,
            "axial_stiffness_n": axial,
            "tip_force_n": [0.0, 0.0, tip_force_n],
        },
        "expected": {
            "tip_deflection_mm": float(solved.nodes_mm[-1, 2]),
            "analytic_tip_deflection_mm": float(tip_force_n * length_mm**3 / (3.0 * bending)),
            "centerline_mm": solved.nodes_mm.tolist(),
            "residual_n": float(report.residual),
        },
    }


def steering_case(steer_x: float, steer_y: float, rotation_rad: float, insertion_mm: float) -> dict:
    """Demo steerable catheter relaxed to equilibrium for one actuation state."""
    profile = load_profile(REPO_ROOT / "configs" / "demo-steerable-rf.json")
    model = GenericSteerableRF()
    model.load_parameters(profile, accept_demo_parameters=True)
    model.initialize(EntryPose(np.zeros(3), np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])))
    model._solver.settings = FINE  # noqa: SLF001 - reference generation only
    model.set_insertion(insertion_mm)
    model.set_axial_rotation(rotation_rad)
    model.set_steering(steer_x, steer_y)
    passes = model.solve_static(max_outer_iterations=20, tolerance_mm=1.0e-5)
    nodes = model.state.nodes_mm
    return {
        "name": f"steer_x{steer_x:g}_y{steer_y:g}_roll{rotation_rad:g}_ins{insertion_mm:g}",
        "description": "GenericSteerableRF on the DEMO profile, relaxed to static equilibrium.",
        "input": {
            "profile": "configs/demo-steerable-rf.json",
            "insertion_mm": insertion_mm,
            "axial_rotation_rad": rotation_rad,
            "steer_x": steer_x,
            "steer_y": steer_y,
        },
        "expected": {
            "fixed_point_passes": passes,
            "n_nodes": int(nodes.shape[0]),
            "tip_mm": nodes[-1].tolist(),
            "arclength_mm": float(np.sum(np.linalg.norm(np.diff(nodes, axis=0), axis=1))),
            "centerline_mm": nodes.tolist(),
        },
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    cases = [
        cantilever_case(),
        steering_case(0.0, 0.0, 0.0, 80.0),
        steering_case(1.0, 0.0, 0.0, 100.0),
        steering_case(0.0, -0.6, 0.0, 90.0),
        steering_case(1.0, 0.0, np.pi / 2.0, 100.0),
    ]
    payload = {
        "schema_version": "0.1.0",
        "generator": "scripts/generate_reference_data.py",
        "note": (
            "Golden data produced by the Python reference solver. Regenerate "
            "deliberately; do not edit by hand to make a test pass."
        ),
        "cases": cases,
    }
    path = OUTPUT / "rod-reference-cases.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path} ({path.stat().st_size / 1024:.1f} kB, {len(cases)} cases)")
    for case in cases:
        expected = case["expected"]
        summary = expected.get("tip_mm") or [expected.get("tip_deflection_mm")]
        print(f"  - {case['name']}: tip = {np.round(np.asarray(summary, dtype=float), 4).tolist()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
