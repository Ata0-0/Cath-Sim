"""Pydantic models for the CathSim LA API.

These mirror ``packages/shared-schema/schemas/simulation.schema.json``.  The
module checks itself against that file at import time (see
:func:`assert_matches_shared_schema`), so a drift between the API and the
viewer is a startup error rather than a runtime surprise.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "packages"
    / "shared-schema"
    / "schemas"
    / "simulation.schema.json"
)

DISCLAIMER = "Research prototype - Not for clinical use."


class MaterialParameters(BaseModel):
    """Constitutive parameters. ``None`` means CALIBRATION_REQUIRED."""

    youngs_modulus_mpa: float | None = Field(None, description="MPa (N/mm^2)")
    poisson_ratio: float | None = Field(None, description="dimensionless")
    bending_stiffness_n_mm2: float | None = Field(None, description="EI [N mm^2]")
    torsional_stiffness_n_mm2: float | None = Field(None, description="GJ [N mm^2]")
    axial_stiffness_n: float | None = Field(None, description="EA [N]")
    damping_n_s_per_mm: float | None = Field(
        None, description="N s / mm^2, applied per unit length"
    )
    torsional_damping_n_mm_s_per_rad: float | None = Field(None, description="N mm s / rad per mm")
    density_kg_per_mm3: float | None = Field(None, description="kg/mm^3")


class ActuationInput(BaseModel):
    """Normalised handle inputs.

    ``sequence`` and ``client_timestamp_s`` let the server discard a command
    that arrives after a newer one, so out-of-order delivery is handled
    deterministically instead of producing order-dependent motion.
    """

    insertion_mm: float = Field(80.0, ge=0.0, description="mm")
    axial_rotation_rad: float = Field(0.0, description="rad")
    steer_x: float = Field(0.0, ge=-1.0, le=1.0, description="dimensionless")
    steer_y: float = Field(0.0, ge=-1.0, le=1.0, description="dimensionless")
    deployment: float = Field(0.0, ge=0.0, le=1.0, description="dimensionless")
    sequence: int = Field(0, ge=0)
    client_timestamp_s: float | None = None


class SimulationSettings(BaseModel):
    """Numerical settings for one simulation request."""

    dt_s: float = Field(1.0 / 30.0, gt=0.0, description="s")
    max_iterations: int = Field(400, ge=1)
    gradient_tolerance_n: float = Field(1.0e-6, gt=0.0, description="N")
    gravity_enabled: bool = False
    accept_demo_parameters: bool = Field(
        False,
        description=(
            "The caller confirms it understands that a demo profile carries "
            "invented, uncalibrated values."
        ),
    )


class MeshMetadata(BaseModel):
    """Anatomy provenance and QA result. Never carries patient identifiers."""

    name: str
    provenance: str
    units: Literal["mm", "cm", "UNKNOWN_ASK_USER"]
    vertex_count: int = 0
    triangle_count: int = 0
    is_watertight: bool | None = None
    issues: list[str] = Field(default_factory=list)


class ElectrodePose(BaseModel):
    """Pose of one electrode along the solved centreline."""

    index: int
    arclength_mm: float
    position_mm: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]


class ContactSample(BaseModel):
    """One rod-anatomy contact.

    ``estimated_force_n`` is a NUMERICAL ESTIMATE from an uncalibrated model.
    It is not a clinical contact-force reading and must never be presented as
    one.
    """

    node_index: int
    position_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    penetration_mm: float
    estimated_force_n: float


class ContactMetrics(BaseModel):
    """Aggregate contact metrics for a frame."""

    available: bool = False
    reason: str = "Mesh contact is implemented in Milestone 2."
    contact_count: int = 0
    max_penetration_mm: float = 0.0
    total_estimated_force_n: float = 0.0


class SolverReport(BaseModel):
    """Diagnostics of the last solver call."""

    iterations: int = 0
    residual: float = 0.0
    max_penetration_mm: float = 0.0
    converged: bool = True


class SimulationFrame(BaseModel):
    """One solved frame. Matches the contract's SimulationFrame shape."""

    time_s: float = 0.0
    centerline_mm: list[tuple[float, float, float]] = Field(default_factory=list)
    orientations_xyzw: list[tuple[float, float, float, float]] = Field(default_factory=list)
    electrodes: list[ElectrodePose] = Field(default_factory=list)
    contacts: list[ContactSample] = Field(default_factory=list)
    solver: SolverReport = Field(default_factory=SolverReport)


class ValidationResult(BaseModel):
    """Outcome of one validation test, with its tolerance rationale."""

    test_id: str
    description: str = ""
    measured: float
    expected: float
    relative_error: float
    tolerance: float
    passed: bool
    tolerance_rationale: str = ""


class CalibrationStatusModel(BaseModel):
    """Which required physical values a profile is still missing."""

    missing_fields: list[str]
    is_demo_profile: bool
    material_source: str
    geometry_source: str
    ready_for_simulation: bool


class ServiceInfo(BaseModel):
    """Service identity, schema version and the research-only disclaimer."""

    name: str = "cathsim-la simulation-api"
    version: str = "0.1.0"
    schema_version: str = "0.1.0"
    disclaimer: str = DISCLAIMER


def assert_matches_shared_schema() -> None:
    """Fail loudly if a schema entity has no Pydantic counterpart.

    This is deliberately a *structural* check rather than code generation: the
    API must never quietly diverge from the schema the viewer is typed against.
    """
    if not SCHEMA_PATH.exists():  # pragma: no cover - packaging safety net
        return
    definitions = set(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"])
    implemented = set(globals())
    # CatheterParameters is read as raw JSON by the physics core, which owns its
    # validation and its calibration gate; it is intentionally not re-modelled.
    missing = definitions - implemented - {"CatheterParameters"}
    if missing:
        raise RuntimeError(
            "The API models have drifted from "
            f"{SCHEMA_PATH.name}: no Pydantic model for {sorted(missing)}. "
            "Add the model or bump the schema version with a migration."
        )


assert_matches_shared_schema()
