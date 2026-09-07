"""Analytical validation of the discrete elastic rod.

Every tolerance used here is justified in ``docs/validation-plan.md``.
Failing tests are never skipped, deleted or loosened without recording the
reason in that document.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from cathsim_physics import (
    ExternalLoads,
    RodMaterial,
    RodSolver,
    SolverSettings,
    curvature_binormal,
    energy_and_gradient,
    straight_rod,
)

FINE_SETTINGS = SolverSettings(max_iterations=40000, gradient_tolerance_n=1.0e-9, history_size=150)


def _cantilever_tip_deflection(
    material: RodMaterial, length_mm: float, n_nodes: int, tip_force_n: float
) -> tuple[float, int, float]:
    """Solve a clamped-free beam with a transverse tip load.

    Returns ``(tip_deflection_mm, iterations, residual_n)``.
    """
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], length_mm, n_nodes)
    loads = ExternalLoads(node_forces_n=np.zeros((n_nodes, 3)))
    loads.node_forces_n[-1] = [0.0, 0.0, tip_force_n]
    solver = RodSolver(material, rest, settings=FINE_SETTINGS)
    solved, report = solver.solve_static(state, loads)
    return float(solved.nodes_mm[-1, 2]), report.iterations, report.residual


# --------------------------------------------------------------------------
# V1  Cantilever beam - Euler-Bernoulli  delta = F L^3 / (3 E I)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_nodes", [21, 41, 81])
def test_cantilever_converges_to_euler_bernoulli(
    beam_material: RodMaterial, beam_section: dict[str, float], n_nodes: int, tmp_path: Path
) -> None:
    length_mm = beam_section["length_mm"]
    bending_n_mm2 = beam_section["EI_n_mm2"]

    # Load chosen so that the analytic tip deflection is 1 % of the span,
    # comfortably inside the small-deflection range where the closed form holds.
    target_deflection_mm = 0.01 * length_mm
    tip_force_n = 3.0 * bending_n_mm2 * target_deflection_mm / length_mm**3

    numeric_mm, _, residual = _cantilever_tip_deflection(
        beam_material, length_mm, n_nodes, tip_force_n
    )
    analytic_mm = tip_force_n * length_mm**3 / (3.0 * bending_n_mm2)
    raw_error = abs(numeric_mm - analytic_mm) / analytic_mm

    # The discrete clamp fixes nodes 0 and 1, so the first half Voronoi cell
    # cannot bend and the compliant span is L - h/2 (derivation in
    # docs/physics-model.md).  Both the raw and the corrected error are
    # reported so the discretisation bias stays visible.
    element_mm = length_mm / (n_nodes - 1)
    effective_length_mm = length_mm - 0.5 * element_mm
    corrected_analytic_mm = tip_force_n * effective_length_mm**3 / (3.0 * bending_n_mm2)
    corrected_error = abs(numeric_mm - corrected_analytic_mm) / corrected_analytic_mm

    print(
        f"\n[V1 cantilever] N={n_nodes:3d} h/L={element_mm / length_mm:.4f} "
        f"delta_num={numeric_mm:.6f} mm  delta_EB={analytic_mm:.6f} mm  "
        f"raw_err={raw_error * 100:.3f} %  clamp_corrected_err={corrected_error * 100:.3f} %  "
        f"residual={residual:.2e} N"
    )

    # Raw tolerance: 2 * (h/L) covers the observed first-order clamp bias with
    # a factor-of-two margin.  Corrected tolerance: 0.5 %.
    assert raw_error < 2.0 * element_mm / length_mm
    assert corrected_error < 5.0e-3


def test_cantilever_error_is_first_order_in_element_size(
    beam_material: RodMaterial, beam_section: dict[str, float]
) -> None:
    """Halving the element size must roughly halve the discretisation error."""
    length_mm = beam_section["length_mm"]
    bending_n_mm2 = beam_section["EI_n_mm2"]
    tip_force_n = 3.0 * bending_n_mm2 * (0.01 * length_mm) / length_mm**3
    analytic_mm = tip_force_n * length_mm**3 / (3.0 * bending_n_mm2)

    errors = []
    for n_nodes in (21, 41, 81):
        numeric_mm, _, _ = _cantilever_tip_deflection(
            beam_material, length_mm, n_nodes, tip_force_n
        )
        errors.append(abs(numeric_mm - analytic_mm) / analytic_mm)

    orders = [math.log2(errors[i] / errors[i + 1]) for i in range(len(errors) - 1)]
    formatted_errors = [f"{value:.4f}" for value in errors]
    formatted_orders = [f"{value:.2f}" for value in orders]
    print(f"\n[V1b convergence] errors={formatted_errors} observed_orders={formatted_orders}")
    assert all(order > 0.8 for order in orders), (
        f"Expected ~first-order convergence, observed orders {orders}."
    )


# --------------------------------------------------------------------------
# V2  Pure bending - uniform rest curvature == uniform moment M = EI kappa0
# --------------------------------------------------------------------------


def test_pure_bending_reaches_target_curvature(beam_material: RodMaterial) -> None:
    length_mm = 100.0
    n_nodes = 81
    target_curvature_per_mm = 1.0 / 200.0  # radius 200 mm

    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], length_mm, n_nodes)
    voronoi = rest.voronoi_lengths_mm
    binormal = np.tile([0.0, 1.0, 0.0], (n_nodes - 2, 1))
    rest.kb0[:] = target_curvature_per_mm * voronoi[:, None] * binormal

    solver = RodSolver(beam_material, rest, settings=FINE_SETTINGS)
    solved, report = solver.solve_static(state)

    kb = curvature_binormal(solved.nodes_mm)
    curvature_per_mm = np.linalg.norm(kb, axis=1) / voronoi
    mean_curvature = float(curvature_per_mm.mean())
    error = abs(mean_curvature - target_curvature_per_mm) / target_curvature_per_mm

    print(
        f"\n[V2 pure bending] kappa_target={target_curvature_per_mm:.6f} 1/mm  "
        f"kappa_mean={mean_curvature:.6f} 1/mm  err={error * 100:.4f} %  "
        f"equivalent moment M = EI*kappa = "
        f"{beam_material.bending_stiffness_n_mm2 * target_curvature_per_mm:.5f} N mm  "
        f"residual={report.residual:.2e}"
    )
    # A free rod adopts its rest shape exactly; the residual error is the
    # discrete-curvature relation |kb| = 2 tan(phi/2) vs kappa*lbar, which is
    # O((kappa h)^2) ~ 4e-8 here.  0.1 % is generous head-room.
    assert error < 1.0e-3
    # Shape check: the centreline must be a circular arc of radius 1/kappa0.
    curvature_spread = float(curvature_per_mm.max() - curvature_per_mm.min())
    assert curvature_spread / target_curvature_per_mm < 1.0e-3


# --------------------------------------------------------------------------
# V3  Pure torsion - twist angle  theta = T L / (G J)
# --------------------------------------------------------------------------


def test_pure_torsion_matches_analytic_twist(beam_material: RodMaterial, beam_section) -> None:
    length_mm = beam_section["length_mm"]
    n_nodes = 41
    torsional_n_mm2 = beam_section["GJ_n_mm2"]
    applied_moment_n_mm = 0.05

    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], length_mm, n_nodes)
    loads = ExternalLoads(edge_torques_n_mm=np.zeros(n_nodes - 1))
    loads.edge_torques_n_mm[-1] = applied_moment_n_mm

    solver = RodSolver(beam_material, rest, settings=FINE_SETTINGS)
    solved, report = solver.solve_static(state, loads)

    numeric_rad = float(solved.phi_rad[-1] - solved.phi_rad[0])
    # The twist DOF of edge 0 is clamped and the moment is applied on the last
    # edge, so the compliant span runs between those two edge midpoints:
    # L_eff = L - h.
    element_mm = length_mm / (n_nodes - 1)
    analytic_rad = applied_moment_n_mm * (length_mm - element_mm) / torsional_n_mm2
    error = abs(numeric_rad - analytic_rad) / analytic_rad

    print(
        f"\n[V3 pure torsion] GJ={torsional_n_mm2:.4f} N mm^2  T={applied_moment_n_mm} N mm  "
        f"theta_num={numeric_rad:.6f} rad  theta_analytic={analytic_rad:.6f} rad  "
        f"err={error * 100:.4f} %  residual={report.residual:.2e}"
    )
    # The discrete twist chain reproduces the linear ODE exactly once the
    # boundary offset above is accounted for; only round-off remains.
    assert error < 1.0e-6


# --------------------------------------------------------------------------
# V4  Rigid-body invariance
# --------------------------------------------------------------------------


def test_elastic_energy_is_rigid_body_invariant(
    beam_material: RodMaterial, rng: np.random.Generator
) -> None:
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], 60.0, 25)
    state.nodes_mm += rng.normal(0.0, 0.5, state.nodes_mm.shape)
    state.phi_rad += rng.normal(0.0, 0.1, state.phi_rad.shape)
    rest.kb0[:] = rng.normal(0.0, 0.01, rest.kb0.shape)

    reference, _, _ = energy_and_gradient(state, rest, beam_material)

    # Random rotation via a fixed-seed quaternion, plus a translation.
    axis = rng.normal(size=3)
    axis /= np.linalg.norm(axis)
    angle = 1.234
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    cross = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]], [-axis[1], axis[0], 0.0]])
    rotation = np.eye(3) * cos_a + sin_a * cross + (1.0 - cos_a) * np.outer(axis, axis)
    translation = np.array([137.0, -42.0, 11.5])

    moved = state.copy()
    moved.nodes_mm = state.nodes_mm @ rotation.T + translation
    moved.d1_first = rotation @ state.d1_first
    moved_rest = type(rest)(
        edge_lengths_mm=rest.edge_lengths_mm.copy(),
        kb0=rest.kb0 @ rotation.T,  # rest curvature is a world-frame vector
        dphi0_rad=rest.dphi0_rad.copy(),
    )
    transformed, _, _ = energy_and_gradient(moved, moved_rest, beam_material)

    relative = abs(transformed.elastic_total - reference.elastic_total) / max(
        reference.elastic_total, 1.0e-12
    )
    print(
        f"\n[V4 rigid-body invariance] E={reference.elastic_total:.9f} -> "
        f"{transformed.elastic_total:.9f} N mm  rel_change={relative:.3e}"
    )
    # Pure floating-point round-off of an O(1) energy under a 3x3 rotation.
    assert relative < 1.0e-12
