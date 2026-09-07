"""CathSim LA physics core - reference implementation.

Research prototype - Not for clinical use.
"""

from .catheter import (
    ActuationInput,
    CatheterModel,
    ElectrodePose,
    EntryPose,
    GenericSteerableRF,
)
from .config import (
    CALIBRATION_REQUIRED,
    SCHEMA_VERSION,
    CalibrationStatus,
    ConfigError,
    calibration_status,
    load_profile,
    material_from_profile,
)
from .rod import (
    EnergyBreakdown,
    ExternalLoads,
    RodMaterial,
    RodRest,
    RodState,
    curvature_binormal,
    energy_and_gradient,
    straight_rod,
)
from .solver import (
    BoundaryConditions,
    RodSolver,
    RodSolverError,
    SolverReport,
    SolverSettings,
)

__all__ = [
    "CALIBRATION_REQUIRED",
    "SCHEMA_VERSION",
    "ActuationInput",
    "BoundaryConditions",
    "CalibrationStatus",
    "CatheterModel",
    "ConfigError",
    "ElectrodePose",
    "EnergyBreakdown",
    "EntryPose",
    "ExternalLoads",
    "GenericSteerableRF",
    "RodMaterial",
    "RodRest",
    "RodSolver",
    "RodSolverError",
    "RodState",
    "SolverReport",
    "SolverSettings",
    "calibration_status",
    "curvature_binormal",
    "energy_and_gradient",
    "load_profile",
    "material_from_profile",
    "straight_rod",
]

__version__ = "0.1.0"
