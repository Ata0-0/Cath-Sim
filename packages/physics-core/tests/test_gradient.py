"""The analytic energy gradient must equal the finite-difference gradient.

This underpins every other physics test: an incorrect gradient produces a
converged-looking but wrong equilibrium.  Tolerance rationale in
``docs/validation-plan.md`` (V0).
"""

from __future__ import annotations

import numpy as np
from cathsim_physics import ExternalLoads, RodMaterial, energy_and_gradient, straight_rod


def _perturbed_rod(rng: np.random.Generator):
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], 50.0, 12)
    state.nodes_mm += rng.normal(0.0, 1.0, state.nodes_mm.shape)
    state.phi_rad += rng.normal(0.0, 0.3, state.phi_rad.shape)
    rest.kb0[:] = rng.normal(0.0, 0.05, rest.kb0.shape)
    rest.dphi0_rad[:] = rng.normal(0.0, 0.02, rest.dphi0_rad.shape)
    return state, rest


def test_analytic_gradient_matches_finite_differences(rng: np.random.Generator) -> None:
    state, rest = _perturbed_rod(rng)
    material = RodMaterial(120.0, 90.0, 4000.0, 1.0, 1.0)
    loads = ExternalLoads(
        node_forces_n=rng.normal(0.0, 0.01, state.nodes_mm.shape),
        edge_torques_n_mm=rng.normal(0.0, 0.01, state.phi_rad.shape),
    )
    _, grad_nodes, grad_phi = energy_and_gradient(state, rest, material, loads)

    step = 1.0e-6
    max_relative_error = 0.0
    gradient_scale = max(np.abs(grad_nodes).max(), np.abs(grad_phi).max())

    for node in range(state.n_nodes):
        for axis in range(3):
            plus, minus = state.copy(), state.copy()
            plus.nodes_mm[node, axis] += step
            minus.nodes_mm[node, axis] -= step
            numeric = (
                energy_and_gradient(plus, rest, material, loads)[0].total
                - energy_and_gradient(minus, rest, material, loads)[0].total
            ) / (2.0 * step)
            max_relative_error = max(
                max_relative_error, abs(numeric - grad_nodes[node, axis]) / gradient_scale
            )

    for edge in range(state.n_edges):
        plus, minus = state.copy(), state.copy()
        plus.phi_rad[edge] += step
        minus.phi_rad[edge] -= step
        numeric = (
            energy_and_gradient(plus, rest, material, loads)[0].total
            - energy_and_gradient(minus, rest, material, loads)[0].total
        ) / (2.0 * step)
        max_relative_error = max(max_relative_error, abs(numeric - grad_phi[edge]) / gradient_scale)

    # Central differences at h=1e-6 on an O(1e3) energy carry ~1e-8 relative
    # truncation/round-off noise; 1e-6 leaves head-room without hiding an error.
    assert max_relative_error < 1.0e-6, (
        f"Analytic gradient disagrees with finite differences by "
        f"{max_relative_error:.3e} (relative to |grad|_max = {gradient_scale:.3e})."
    )
