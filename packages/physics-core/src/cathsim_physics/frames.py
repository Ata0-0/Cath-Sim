"""Adapted (Bishop) frame utilities for the discrete elastic rod.

A Bishop frame is a rotation-minimising orthonormal frame ``(t, d1, d2)``
carried along the rod centreline.  It is obtained by parallel-transporting the
director ``d1`` of the first edge onto every following edge.  By construction a
Bishop frame carries **zero twist**, which is exactly why we use it: the twist
degree of freedom ``phi`` of an edge is then the *material* twist angle
measured against a twist-free reference, and the twist energy becomes a
function of ``phi`` alone (see :mod:`cathsim_physics.rod`).

All vectors are in millimetres / dimensionless directions.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import numpy as np

_EPS = 1.0e-12


def normalise(vectors: np.ndarray) -> np.ndarray:
    """Return ``vectors`` (..., 3) scaled to unit length.

    Raises:
        ValueError: if any vector is (numerically) of zero length, which in a
            rod means a collapsed edge and is never physically meaningful.
    """
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    if not np.all(np.isfinite(norms)) or np.any(norms < _EPS):
        raise ValueError(
            "Cannot normalise a zero-length or non-finite direction vector. "
            "This usually means two rod nodes collapsed onto each other; "
            "reduce the time step or increase the axial stiffness."
        )
    return vectors / norms


def parallel_transport(vector: np.ndarray, t_from: np.ndarray, t_to: np.ndarray) -> np.ndarray:
    """Parallel-transport ``vector`` from unit tangent ``t_from`` to ``t_to``.

    Rotation-minimising transport about the axis ``t_from x t_to``.  Works on a
    single 3-vector or on a batch of shape ``(..., 3)``.
    """
    vector = np.asarray(vector, dtype=float)
    t_from = np.asarray(t_from, dtype=float)
    t_to = np.asarray(t_to, dtype=float)

    axis = np.cross(t_from, t_to)
    sin_theta = np.linalg.norm(axis, axis=-1, keepdims=True)
    cos_theta = np.sum(t_from * t_to, axis=-1, keepdims=True)

    # Degenerate case: tangents (anti)parallel -> transport is the identity.
    safe = sin_theta > _EPS
    axis_unit = np.where(safe, axis / np.where(safe, sin_theta, 1.0), 0.0)

    # Rodrigues rotation.
    cross_term = np.cross(axis_unit, vector)
    dot_term = np.sum(axis_unit * vector, axis=-1, keepdims=True)
    rotated = vector * cos_theta + cross_term * sin_theta + axis_unit * dot_term * (1.0 - cos_theta)
    return np.where(safe, rotated, vector)


def any_perpendicular(tangent: np.ndarray) -> np.ndarray:
    """Return an arbitrary unit vector perpendicular to ``tangent`` (3,)."""
    tangent = normalise(np.asarray(tangent, dtype=float))
    helper = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(tangent, helper))) > 0.9:
        helper = np.array([1.0, 0.0, 0.0])
    return normalise(np.cross(tangent, helper))


def bishop_frame(tangents: np.ndarray, d1_first: np.ndarray) -> np.ndarray:
    """Build the Bishop directors ``d1`` for every edge.

    Args:
        tangents: ``(M, 3)`` unit tangents, one per edge.
        d1_first: ``(3,)`` director of edge 0, must be perpendicular to
            ``tangents[0]`` (it is re-orthogonalised defensively).

    Returns:
        ``(M, 3)`` array of unit directors, each perpendicular to its tangent.
    """
    tangents = np.asarray(tangents, dtype=float)
    n_edges = tangents.shape[0]
    d1 = np.empty((n_edges, 3), dtype=float)

    first = np.asarray(d1_first, dtype=float)
    first = first - np.dot(first, tangents[0]) * tangents[0]
    d1[0] = normalise(first)

    for edge in range(1, n_edges):
        transported = parallel_transport(d1[edge - 1], tangents[edge - 1], tangents[edge])
        transported = transported - np.dot(transported, tangents[edge]) * tangents[edge]
        d1[edge] = normalise(transported)
    return d1


def material_frame(
    tangents: np.ndarray, d1: np.ndarray, phi_rad: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Rotate the Bishop directors by the material twist angle ``phi``.

    Returns ``(m1, m2)``, each ``(M, 3)``::

        m1 =  cos(phi) d1 + sin(phi) d2
        m2 = -sin(phi) d1 + cos(phi) d2      with d2 = t x d1
    """
    d2 = np.cross(tangents, d1)
    cos_phi = np.cos(phi_rad)[:, None]
    sin_phi = np.sin(phi_rad)[:, None]
    m1 = cos_phi * d1 + sin_phi * d2
    m2 = -sin_phi * d1 + cos_phi * d2
    return m1, m2


def frame_to_quaternion_xyzw(tangent: np.ndarray, m1: np.ndarray, m2: np.ndarray) -> np.ndarray:
    """Convert the orthonormal frame ``(m1, m2, t)`` to quaternions ``[x,y,z,w]``.

    Column convention: the rotation matrix maps the local axes
    ``(e_x, e_y, e_z)`` onto ``(m1, m2, tangent)``.  Batched over ``(M, 3)``.
    """
    m = np.stack([m1, m2, tangent], axis=-1)  # (M, 3, 3), columns are the axes
    trace = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    quat = np.zeros((m.shape[0], 4), dtype=float)

    positive = trace > 0.0
    s = np.zeros(m.shape[0])
    s[positive] = np.sqrt(trace[positive] + 1.0) * 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        quat[positive, 3] = 0.25 * s[positive]
        quat[positive, 0] = (m[positive, 2, 1] - m[positive, 1, 2]) / s[positive]
        quat[positive, 1] = (m[positive, 0, 2] - m[positive, 2, 0]) / s[positive]
        quat[positive, 2] = (m[positive, 1, 0] - m[positive, 0, 1]) / s[positive]

    # Fallback branch for trace <= 0: pick the largest diagonal element.
    for index in np.flatnonzero(~positive):
        mat = m[index]
        diag = np.argmax([mat[0, 0], mat[1, 1], mat[2, 2]])
        if diag == 0:
            root = np.sqrt(1.0 + mat[0, 0] - mat[1, 1] - mat[2, 2]) * 2.0
            quat[index] = [
                0.25 * root,
                (mat[0, 1] + mat[1, 0]) / root,
                (mat[0, 2] + mat[2, 0]) / root,
                (mat[2, 1] - mat[1, 2]) / root,
            ]
        elif diag == 1:
            root = np.sqrt(1.0 + mat[1, 1] - mat[0, 0] - mat[2, 2]) * 2.0
            quat[index] = [
                (mat[0, 1] + mat[1, 0]) / root,
                0.25 * root,
                (mat[1, 2] + mat[2, 1]) / root,
                (mat[0, 2] - mat[2, 0]) / root,
            ]
        else:
            root = np.sqrt(1.0 + mat[2, 2] - mat[0, 0] - mat[1, 1]) * 2.0
            quat[index] = [
                (mat[0, 2] + mat[2, 0]) / root,
                (mat[1, 2] + mat[2, 1]) / root,
                0.25 * root,
                (mat[1, 0] - mat[0, 1]) / root,
            ]
    return quat / np.linalg.norm(quat, axis=-1, keepdims=True)
