"""Catheter parameter profiles and their calibration status.

Every geometric, elastic and contact number used by the physics core comes
from an explicit JSON profile under ``configs/``.  A profile may leave physical
values as ``null``; such a value is **CALIBRATION_REQUIRED** and the solver
refuses to run with it unless the caller explicitly opts into a clearly
labelled demo profile.

Geometric similarity is not mechanical accuracy.  A profile whose
``provenance.material_source`` is ``CALIBRATION_REQUIRED`` produces plausible
looking motion, not validated catheter mechanics.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .rod import RodMaterial
from .units import (
    circular_area_mm2,
    circular_polar_moment_mm4,
    circular_second_moment_mm4,
    shear_modulus_mpa,
)

SCHEMA_VERSION = "0.1.0"

#: Marker used in profiles and surfaced in the UI.
CALIBRATION_REQUIRED = "CALIBRATION_REQUIRED"


class ConfigError(ValueError):
    """Raised when a parameter profile cannot be used as given."""


@dataclass(frozen=True)
class CalibrationStatus:
    """Which required physical values are still missing from a profile."""

    missing_fields: tuple[str, ...]
    is_demo_profile: bool
    material_source: str
    geometry_source: str

    @property
    def ready_for_simulation(self) -> bool:
        """True when no required physical value is still CALIBRATION_REQUIRED."""
        return not self.missing_fields


#: Fields the rod solver cannot run without.
REQUIRED_PHYSICS_FIELDS: tuple[str, ...] = (
    "material.youngs_modulus_mpa",
    "material.poisson_ratio",
    "material.damping_n_s_per_mm",
    "actuation.steer_gain_rad_per_mm",
)


def _get_path(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def load_profile(path: str | Path) -> dict[str, Any]:
    """Read a catheter parameter profile and check its schema version."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Parameter profile '{path}' was not found. Pass the path of a JSON "
            f"profile from the configs/ directory."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Parameter profile '{path}' is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ConfigError(
            f"Parameter profile '{path}' declares schema_version={version!r} but "
            f"this build understands {SCHEMA_VERSION!r}. Migrate the profile "
            f"instead of editing the schema silently."
        )
    return data


def calibration_status(profile: dict[str, Any]) -> CalibrationStatus:
    """List the physics fields that are still ``null`` in ``profile``."""
    missing = tuple(field for field in REQUIRED_PHYSICS_FIELDS if _get_path(profile, field) is None)
    provenance = profile.get("provenance", {})
    return CalibrationStatus(
        missing_fields=missing,
        is_demo_profile=bool(profile.get("is_demo_profile", False)),
        material_source=str(provenance.get("material_source", CALIBRATION_REQUIRED)),
        geometry_source=str(provenance.get("geometry_source", CALIBRATION_REQUIRED)),
    )


def material_from_profile(
    profile: dict[str, Any], accept_demo_parameters: bool = False
) -> RodMaterial:
    """Build :class:`RodMaterial` from a profile.

    Args:
        profile: parsed profile dictionary.
        accept_demo_parameters: the caller confirms that it understands the
            profile carries uncalibrated demo numbers.  Required for any
            profile flagged ``is_demo_profile``.

    Raises:
        ConfigError: if required values are missing, or if a demo profile is
            used without explicit consent.
    """
    status = calibration_status(profile)
    if status.missing_fields:
        raise ConfigError(
            "Cannot start a simulation: the following physical parameters are "
            f"still {CALIBRATION_REQUIRED} in profile "
            f"'{profile.get('display_name', profile.get('model_type'))}': "
            + ", ".join(status.missing_fields)
            + ". Either calibrate them against bench measurements (see "
            "docs/validation-plan.md) or select the clearly labelled demo "
            "profile."
        )
    if status.is_demo_profile and not accept_demo_parameters:
        raise ConfigError(
            "This is a DEMO parameter profile with invented, uncalibrated "
            "values. It may only be used after explicitly accepting demo "
            "parameters (accept_demo_parameters=True in the API, or the "
            "'Use demo parameters' switch in the viewer). Demo values must "
            "never be reported as catheter specifications."
        )

    geometry = profile["geometry"]
    material = profile["material"]
    diameter_mm = float(geometry["outer_diameter_mm"])
    youngs_mpa = float(material["youngs_modulus_mpa"])
    poisson = float(material["poisson_ratio"])
    shear_mpa = shear_modulus_mpa(youngs_mpa, poisson)

    area_mm2 = circular_area_mm2(diameter_mm)
    second_moment_mm4 = circular_second_moment_mm4(diameter_mm)
    polar_moment_mm4 = circular_polar_moment_mm4(diameter_mm)

    # Explicit stiffness overrides win over the E/nu + section route, so a
    # bench calibration can be entered directly as EI / GJ / EA.
    bending = material.get("bending_stiffness_n_mm2")
    torsional = material.get("torsional_stiffness_n_mm2")
    axial = material.get("axial_stiffness_n")

    return RodMaterial(
        bending_stiffness_n_mm2=(
            float(bending) if bending is not None else youngs_mpa * second_moment_mm4
        ),
        torsional_stiffness_n_mm2=(
            float(torsional) if torsional is not None else shear_mpa * polar_moment_mm4
        ),
        axial_stiffness_n=float(axial) if axial is not None else youngs_mpa * area_mm2,
        damping_n_s_per_mm=float(material["damping_n_s_per_mm"]),
        torsional_damping_n_mm_s_per_rad=float(
            material.get("torsional_damping_n_mm_s_per_rad")
            # Fallback: scale the translational damping by the polar radius of
            # gyration squared.  Documented approximation, see assumptions.md.
            or material["damping_n_s_per_mm"] * polar_moment_mm4 / area_mm2
        ),
        linear_density_kg_per_mm=(
            float(material["density_kg_per_mm3"]) * area_mm2
            if material.get("density_kg_per_mm3") is not None
            else None
        ),
    )
