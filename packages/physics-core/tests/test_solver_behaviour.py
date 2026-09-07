"""Time integration, dissipation, determinism and failure-mode tests.

Tolerances are justified in ``docs/validation-plan.md`` (V5, V7, V8, V10).
"""

from __future__ import annotations

import numpy as np
import pytest
from cathsim_physics import (
    ExternalLoads,
    RodMaterial,
    RodSolver,
    RodSolverError,
    SolverSettings,
    energy_and_gradient,
    straight_rod,
)

SETTINGS = SolverSettings(max_iterations=4000, gradient_tolerance_n=1.0e-9, history_size=150)


def _relaxation_run(material: RodMaterial, dt_s: float, duration_s: float, n_nodes: int = 41):
    """Release a rod with a constant transverse tip load and integrate in time."""
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], 100.0, n_nodes)
    loads = ExternalLoads(node_forces_n=np.zeros((n_nodes, 3)))
    loads.node_forces_n[-1] = [0.0, 0.0, 2.0e-5]
    solver = RodSolver(material, rest, settings=SETTINGS)
    steps = round(duration_s / dt_s)
    report = None
    for _ in range(steps):
        state, report = solver.step(state, dt_s, loads)
    return state, rest, report


# --------------------------------------------------------------------------
# V5  Time-step sensitivity
# --------------------------------------------------------------------------


def test_quasi_static_shape_is_time_step_insensitive(beam_material: RodMaterial) -> None:
    """Halving dt must not change the relaxed shape beyond the stated tolerance."""
    duration_s = 4.0
    coarse, _, _ = _relaxation_run(beam_material, dt_s=0.05, duration_s=duration_s)
    fine, _, _ = _relaxation_run(beam_material, dt_s=0.025, duration_s=duration_s)

    difference_mm = np.linalg.norm(coarse.nodes_mm - fine.nodes_mm, axis=1)
    rms_mm = float(np.sqrt(np.mean(difference_mm**2)))
    tip_mm = float(difference_mm[-1])
    span_mm = 100.0

    print(
        f"\n[V5 dt sensitivity] dt=0.05 s vs 0.025 s over {duration_s} s: "
        f"RMS centreline difference={rms_mm:.6f} mm ({rms_mm / span_mm * 100:.4f} % of span), "
        f"tip difference={tip_mm:.6f} mm"
    )
    # Backward Euler is first-order in time, so the two runs differ by O(dt)
    # during the transient.  After 4 s of over-damped relaxation both are close
    # to the same equilibrium; 0.1 % of span is the documented bound.
    assert rms_mm < 1.0e-3 * span_mm


# --------------------------------------------------------------------------
# V7  Energy / damping behaviour
# --------------------------------------------------------------------------


def test_energy_decays_monotonically_after_load_removal(beam_material: RodMaterial) -> None:
    """With the external load removed, elastic energy must decay, never grow."""
    n_nodes = 41
    state, rest, _ = _relaxation_run(beam_material, dt_s=0.05, duration_s=2.0, n_nodes=n_nodes)
    solver = RodSolver(beam_material, rest, settings=SETTINGS)

    energies = []
    for _ in range(40):
        state, _ = solver.step(state, 0.05, loads=None)  # load removed
        energies.append(energy_and_gradient(state, rest, beam_material)[0].elastic_total)

    increases = [
        (index, energies[index + 1] - energies[index])
        for index in range(len(energies) - 1)
        if energies[index + 1] > energies[index] + 1.0e-12
    ]
    print(
        f"\n[V7 dissipation] E_elastic: {energies[0]:.6e} -> {energies[-1]:.6e} N mm  "
        f"(decay factor {energies[-1] / energies[0]:.3e}), non-decreasing steps: {len(increases)}"
    )
    assert not increases, f"Elastic energy increased at steps {increases}."
    assert energies[-1] < 1.0e-3 * energies[0]
    assert np.all(np.isfinite(state.nodes_mm))


# --------------------------------------------------------------------------
# V8  Determinism
# --------------------------------------------------------------------------


def test_identical_inputs_produce_bitwise_identical_output(beam_material: RodMaterial) -> None:
    first, _, report_a = _relaxation_run(beam_material, dt_s=0.05, duration_s=1.0)
    second, _, report_b = _relaxation_run(beam_material, dt_s=0.05, duration_s=1.0)
    print(
        f"\n[V8 determinism] max |dx| = "
        f"{np.abs(first.nodes_mm - second.nodes_mm).max():.3e} mm, "
        f"iterations {report_a.iterations} vs {report_b.iterations}"
    )
    np.testing.assert_array_equal(first.nodes_mm, second.nodes_mm)
    np.testing.assert_array_equal(first.phi_rad, second.phi_rad)
    assert report_a.iterations == report_b.iterations


# --------------------------------------------------------------------------
# V10  NaN / Inf and degenerate inputs fail loudly and safely
# --------------------------------------------------------------------------


def test_non_finite_state_is_rejected_with_an_actionable_message(
    beam_material: RodMaterial,
) -> None:
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], 50.0, 11)
    state.nodes_mm[5, 1] = np.nan
    with pytest.raises(ValueError, match="Non-finite"):
        energy_and_gradient(state, rest, beam_material)


def test_collapsed_edge_is_rejected(beam_material: RodMaterial) -> None:
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], 50.0, 11)
    state.nodes_mm[6] = state.nodes_mm[5]
    with pytest.raises(ValueError, match="collapsed"):
        energy_and_gradient(state, rest, beam_material)


@pytest.mark.parametrize("bad_dt", [0.0, -0.1, float("nan"), float("inf")])
def test_invalid_time_step_is_rejected(beam_material: RodMaterial, bad_dt: float) -> None:
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], 50.0, 11)
    solver = RodSolver(beam_material, rest)
    with pytest.raises(RodSolverError, match="positive finite"):
        solver.step(state, bad_dt)


def test_gravity_without_calibrated_density_is_refused(beam_material: RodMaterial) -> None:
    state, rest = straight_rod(np.zeros(3), [1.0, 0.0, 0.0], 50.0, 11)
    loads = ExternalLoads(gravity_mm_per_s2=np.array([0.0, 0.0, -9806.65]))
    with pytest.raises(ValueError, match="CALIBRATION_REQUIRED"):
        energy_and_gradient(state, rest, beam_material, loads)
