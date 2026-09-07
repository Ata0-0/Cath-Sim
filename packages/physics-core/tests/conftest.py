"""Shared fixtures. Deterministic by construction: every RNG uses a fixed seed."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "physics-core" / "src"))

from cathsim_physics import RodMaterial  # noqa: E402
from cathsim_physics.units import (  # noqa: E402
    circular_area_mm2,
    circular_polar_moment_mm4,
    circular_second_moment_mm4,
    shear_modulus_mpa,
)

#: Fixed seed for every stochastic check in the suite.
SEED = 20260907

#: Reference beam used by the analytical tests.  These are *test fixture*
#: numbers chosen to exercise the solver in a regime where the closed-form
#: solutions apply; they are NOT catheter properties.
BEAM_LENGTH_MM = 100.0
BEAM_DIAMETER_MM = 2.5
BEAM_YOUNGS_MPA = 3.0
BEAM_POISSON = 0.4


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def beam_section() -> dict[str, float]:
    """Closed-form section properties of the reference beam."""
    area = circular_area_mm2(BEAM_DIAMETER_MM)
    second_moment = circular_second_moment_mm4(BEAM_DIAMETER_MM)
    polar_moment = circular_polar_moment_mm4(BEAM_DIAMETER_MM)
    shear = shear_modulus_mpa(BEAM_YOUNGS_MPA, BEAM_POISSON)
    return {
        "length_mm": BEAM_LENGTH_MM,
        "area_mm2": area,
        "EI_n_mm2": BEAM_YOUNGS_MPA * second_moment,
        "GJ_n_mm2": shear * polar_moment,
        "EA_n": BEAM_YOUNGS_MPA * area,
    }


#: Target over-damped relaxation time constant of the reference beam [s].
#: The damping coefficients below are *derived* from it rather than guessed, so
#: that the transient tests (V5, V7) exercise a resolvable time scale instead of
#: a rod that is effectively frozen.  For a first-order system
#: ``c_total x_dot = -k x`` the time constant is ``tau = c_total / k``.
BEAM_RELAXATION_TIME_S = 0.2


@pytest.fixture(scope="session")
def beam_material(beam_section: dict[str, float]) -> RodMaterial:
    length_mm = beam_section["length_mm"]
    # Cantilever tip stiffness k = 3 EI / L^3 [N/mm]  ->  c_total = tau * k,
    # distributed over the span: c_per_length [N s / mm^2].
    tip_stiffness_n_per_mm = 3.0 * beam_section["EI_n_mm2"] / length_mm**3
    damping_per_length = BEAM_RELAXATION_TIME_S * tip_stiffness_n_per_mm / length_mm
    # Torsional counterpart: k_twist = GJ / L [N mm / rad].
    twist_stiffness = beam_section["GJ_n_mm2"] / length_mm
    torsional_damping_per_length = BEAM_RELAXATION_TIME_S * twist_stiffness / length_mm
    return RodMaterial(
        bending_stiffness_n_mm2=beam_section["EI_n_mm2"],
        torsional_stiffness_n_mm2=beam_section["GJ_n_mm2"],
        axial_stiffness_n=beam_section["EA_n"],
        damping_n_s_per_mm=damping_per_length,
        torsional_damping_n_mm_s_per_rad=torsional_damping_per_length,
    )


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(SEED)
