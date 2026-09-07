"""CathSim LA geometry core.

Milestone 0 ships the synthetic demo anatomy and the *input safety limits*
only.  STL/OBJ import, mesh QA (manifoldness, inverted normals, duplicate
vertices, degenerate faces, scale) and the BVH used for contact are Milestone 2.

The limits below exist from day one because they are a safety property, not a
feature: a malformed or oversized mesh must be rejected cleanly rather than
partially parsed.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

__version__ = "0.1.0"

#: Hard input limits. Exceeding any of them is a rejection, not a warning.
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_TRIANGLES = 5_000_000
MAX_PARSE_SECONDS = 20.0

MeshUnits = Literal["mm", "cm", "UNKNOWN_ASK_USER"]


class MeshRejectedError(ValueError):
    """Raised when an input mesh cannot be accepted."""


#: Backwards-compatible alias; the plain noun reads better at call sites.
MeshRejected = MeshRejectedError


@dataclass
class MeshQAReport:
    """Result of mesh quality assurance.

    ``issues`` are reported, never silently repaired: every automatic repair
    must be recorded and reversible (project contract).
    """

    name: str
    provenance: str
    units: MeshUnits
    vertex_count: int
    triangle_count: int
    is_watertight: bool | None = None
    issues: list[str] = field(default_factory=list)
    repairs_applied: list[str] = field(default_factory=list)


def check_input_limits(file_bytes: int, triangle_count: int, parse_seconds: float) -> None:
    """Reject oversized or slow-to-parse inputs with an actionable message.

    Args:
        file_bytes: size of the uploaded file.
        triangle_count: triangles found so far.
        parse_seconds: elapsed parse time.

    Raises:
        MeshRejected: if any limit is exceeded.
    """
    if file_bytes > MAX_FILE_BYTES:
        raise MeshRejected(
            f"Mesh file is {file_bytes / 1e6:.1f} MB, above the "
            f"{MAX_FILE_BYTES / 1e6:.0f} MB limit. Decimate the mesh before "
            f"importing it."
        )
    if triangle_count > MAX_TRIANGLES:
        raise MeshRejected(
            f"Mesh has {triangle_count} triangles, above the {MAX_TRIANGLES} "
            f"limit. Decimate the mesh before importing it."
        )
    if parse_seconds > MAX_PARSE_SECONDS:
        raise MeshRejected(
            f"Parsing exceeded {MAX_PARSE_SECONDS} s and was stopped. The file "
            f"may be malformed or a decompression bomb."
        )


def require_explicit_units(declared: MeshUnits) -> float:
    """Return the mm-per-unit scale factor for a declared unit.

    A mesh file that does not state its units is **not** silently assumed to be
    millimetres; the caller must ask the user (project contract).

    Raises:
        MeshRejected: if the units are still unknown.
    """
    if declared == "mm":
        return 1.0
    if declared == "cm":
        return 10.0
    raise MeshRejected(
        "The mesh file does not declare its units. Select mm or cm explicitly; "
        "the importer will not guess, because a 10x scale error would silently "
        "invalidate every contact and gap measurement."
    )


def synthetic_chamber(
    radius_mm: float = 26.0, segments: int = 48, centre_z_mm: float | None = None
) -> tuple[np.ndarray, np.ndarray, MeshQAReport]:
    """Procedurally generate the default demo chamber (sphere).

    This is the Python twin of ``apps/viewer/src/geometry/syntheticMesh.ts``.
    It is a SHAPE PLACEHOLDER at approximately left-atrium scale - not anatomy,
    and not patient data.

    Returns:
        ``(vertices_mm (V,3), faces (F,3), report)``.
    """
    if centre_z_mm is None:
        centre_z_mm = radius_mm + 55.0
    rings = max(8, segments // 2)
    theta = np.linspace(0.0, np.pi, rings + 1)
    phi = np.linspace(0.0, 2.0 * np.pi, segments + 1)
    theta_grid, phi_grid = np.meshgrid(theta, phi, indexing="ij")
    vertices = np.stack(
        [
            radius_mm * np.sin(theta_grid) * np.cos(phi_grid),
            radius_mm * np.sin(theta_grid) * np.sin(phi_grid),
            centre_z_mm + radius_mm * np.cos(theta_grid),
        ],
        axis=-1,
    ).reshape(-1, 3)

    stride = segments + 1
    faces: list[tuple[int, int, int]] = []
    for ring in range(rings):
        for segment in range(segments):
            a = ring * stride + segment
            b = a + stride
            faces.append((a, b, a + 1))
            faces.append((a + 1, b, b + 1))
    face_array = np.asarray(faces, dtype=np.int64)

    report = MeshQAReport(
        name="Synthetic demo chamber",
        provenance=(
            "PROCEDURALLY GENERATED PLACEHOLDER - not anatomy, not patient data. "
            "Sphere at approximate left-atrium scale."
        ),
        units="mm",
        vertex_count=int(vertices.shape[0]),
        triangle_count=int(face_array.shape[0]),
        is_watertight=None,
        issues=["Watertightness check is implemented in Milestone 2."],
    )
    return vertices, face_array, report
