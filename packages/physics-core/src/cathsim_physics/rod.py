"""Discrete elastic rod - reference implementation (Python + NumPy).

Continuous model
----------------
The catheter shaft is a Kirchhoff / Cosserat rod whose stored elastic energy is

.. code-block:: text

    E = integral [ 1/2 (kappa - kappa0)^T B (kappa - kappa0)
                 + 1/2 (tau   - tau0  )^T C (tau   - tau0  )
                 + 1/2 (eps   - eps0  )^T S (eps   - eps0  ) ] ds

with bending stiffness ``B = EI`` [N mm^2], torsional stiffness ``C = GJ``
[N mm^2] and axial stiffness ``S = EA`` [N].  ``docs/physics-model.md`` derives
the discretisation below from this integral term by term.

Discretisation (Bishop-frame discrete elastic rod)
--------------------------------------------------
* ``N`` nodes ``x_0 .. x_{N-1}`` [mm], ``M = N-1`` edges ``e_j = x_{j+1}-x_j``.
* One scalar material twist angle ``phi_j`` [rad] per edge, measured against a
  Bishop (rotation-minimising, twist-free) frame anchored on edge 0.
* Discrete curvature binormal at interior node ``i``:
  ``kb_i = 2 e_{i-1} x e_i / (|e_{i-1}||e_i| + e_{i-1}.e_i)``  [-]
  which satisfies ``|kb_i| = 2 tan(phi_i/2) ~= curvature_i * lbar_i``.
* Voronoi length ``lbar_i = (l_{i-1} + l_i)/2`` [mm].

Discrete energies (all in N mm):

.. code-block:: text

    E_stretch = sum_j  1/2 EA (|e_j|/l_j - 1)^2 l_j
    E_bend    = sum_i  EI / (2 lbar_i) |kb_i - kb0_i|^2
    E_twist   = sum_i  GJ / (2 lbar_i) (phi_i - phi_{i-1} - dphi0_i)^2

``kb0_i`` is the **rest curvature binormal expressed in world coordinates**.
Steering writes into it (see :mod:`cathsim_physics.catheter`).  It is held
fixed while the solver relaxes one actuation state and refreshed from the
material frame at the start of the next step; at equilibrium this is a fixed
point, so the converged shape is consistent.

Modelling scope of this MVP (see ``docs/assumptions.md``):

* Bending is **isotropic** (``B1 = B2 = EI``), correct for the round
  cross-section assumed here.  Anisotropic bending is future work.
* Because the twist DOF is measured against a twist-free Bishop frame,
  ``E_twist`` has no explicit position dependence, so ``dE_twist/dx = 0``
  *exactly* in this parameterisation.  The bend-twist (writhe/holonomy)
  coupling therefore only enters through a *twist-prescribed* boundary.  The
  catheter is clamped proximally and free distally, so the omitted coupling
  term does not change the equilibrium.  This is documented, not accidental.
* Shear is suppressed by the inextensible-direction assumption of the
  Kirchhoff rod (tangent == material director 3); no separate shear DOF.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .frames import bishop_frame, material_frame, normalise

_EPS = 1.0e-12


@dataclass(frozen=True)
class RodMaterial:
    """Constitutive parameters of the rod, all in the project unit system.

    Attributes:
        bending_stiffness_n_mm2: ``EI`` [N mm^2].
        torsional_stiffness_n_mm2: ``GJ`` [N mm^2].
        axial_stiffness_n: ``EA`` [N].
        damping_n_s_per_mm: lumped nodal translational viscous damping
            coefficient.  NOTE: the *key name* is fixed by the project
            contract; the coefficient is applied **per unit length**, so its
            effective unit is [N s / mm^2].  See ``docs/assumptions.md``.
        torsional_damping_n_mm_s_per_rad: viscous damping on the twist DOF
            [N mm s / rad], applied per unit length.
        linear_density_kg_per_mm: mass per unit length, only used when gravity
            is enabled.  ``None`` means gravity cannot be enabled.
    """

    bending_stiffness_n_mm2: float
    torsional_stiffness_n_mm2: float
    axial_stiffness_n: float
    damping_n_s_per_mm: float
    torsional_damping_n_mm_s_per_rad: float
    linear_density_kg_per_mm: float | None = None


@dataclass
class RodState:
    """Kinematic state of the rod.

    Attributes:
        nodes_mm: ``(N, 3)`` node positions [mm].
        phi_rad: ``(N-1,)`` material twist angle per edge [rad].
        d1_first: ``(3,)`` Bishop director anchor of edge 0 [-].
    """

    nodes_mm: np.ndarray
    phi_rad: np.ndarray
    d1_first: np.ndarray

    def copy(self) -> RodState:
        """Return an independent deep copy of this state."""
        return RodState(self.nodes_mm.copy(), self.phi_rad.copy(), self.d1_first.copy())

    @property
    def n_nodes(self) -> int:
        """Number of nodes N."""
        return int(self.nodes_mm.shape[0])

    @property
    def n_edges(self) -> int:
        """Number of edges M = N - 1."""
        return int(self.nodes_mm.shape[0] - 1)


@dataclass
class RodRest:
    """Undeformed (rest) configuration of the rod.

    Attributes:
        edge_lengths_mm: ``(M,)`` rest length of every edge [mm].
        kb0: ``(N-2, 3)`` rest curvature binormal at interior nodes [-].
        dphi0_rad: ``(N-2,)`` rest twist increment per interior node [rad].
    """

    edge_lengths_mm: np.ndarray
    kb0: np.ndarray
    dphi0_rad: np.ndarray

    @property
    def voronoi_lengths_mm(self) -> np.ndarray:
        """``(N-2,)`` Voronoi length of every interior node [mm]."""
        return 0.5 * (self.edge_lengths_mm[:-1] + self.edge_lengths_mm[1:])


@dataclass
class ExternalLoads:
    """External generalised loads. Empty by default.

    Attributes:
        node_forces_n: ``(N, 3)`` force applied to each node [N].
        edge_torques_n_mm: ``(M,)`` twisting moment applied to each edge's twist
            DOF [N mm].
        gravity_mm_per_s2: ``(3,)`` gravity vector [mm/s^2], or ``None`` for off.
    """

    node_forces_n: np.ndarray | None = None
    edge_torques_n_mm: np.ndarray | None = None
    gravity_mm_per_s2: np.ndarray | None = None


@dataclass
class EnergyBreakdown:
    """Elastic energy split by mode [N mm]."""

    stretch: float = 0.0
    bend: float = 0.0
    twist: float = 0.0
    external: float = 0.0

    @property
    def elastic_total(self) -> float:
        """Stretch + bend + twist energy [N mm]."""
        return self.stretch + self.bend + self.twist

    @property
    def total(self) -> float:
        """Elastic energy plus the external-load potential [N mm]."""
        return self.elastic_total + self.external


def curvature_binormal(nodes_mm: np.ndarray) -> np.ndarray:
    """Discrete curvature binormal ``kb`` at every interior node.

    Args:
        nodes_mm: ``(N, 3)`` node positions [mm].

    Returns:
        ``(N-2, 3)`` dimensionless curvature binormals.
    """
    e0 = nodes_mm[1:-1] - nodes_mm[:-2]
    e1 = nodes_mm[2:] - nodes_mm[1:-1]
    n0 = np.linalg.norm(e0, axis=1)
    n1 = np.linalg.norm(e1, axis=1)
    denom = n0 * n1 + np.sum(e0 * e1, axis=1)
    if np.any(denom < _EPS):
        raise ValueError(
            "Rod folded back on itself (a discrete turning angle reached 180 deg). "
            "Reduce the time step, lower the steering input, or refine the node "
            "spacing."
        )
    return 2.0 * np.cross(e0, e1) / denom[:, None]


def _check_finite(name: str, array: np.ndarray) -> None:
    if not np.all(np.isfinite(array)):
        raise ValueError(
            f"Non-finite value (NaN/Inf) encountered in '{name}'. The solver was "
            f"stopped to avoid producing meaningless geometry. Check the input "
            f"configuration and the time step."
        )


def energy_and_gradient(
    state: RodState,
    rest: RodRest,
    material: RodMaterial,
    loads: ExternalLoads | None = None,
) -> tuple[EnergyBreakdown, np.ndarray, np.ndarray]:
    """Total energy [N mm] and its gradient w.r.t. every degree of freedom.

    Returns:
        ``(energy, grad_nodes, grad_phi)`` where ``grad_nodes`` is ``(N, 3)``
        in newtons and ``grad_phi`` is ``(M,)`` in newton-millimetres.
    """
    nodes = state.nodes_mm
    phi = state.phi_rad
    _check_finite("nodes_mm", nodes)
    _check_finite("phi_rad", phi)

    grad_nodes = np.zeros_like(nodes)
    grad_phi = np.zeros_like(phi)
    energy = EnergyBreakdown()

    # ---- axial stretch -------------------------------------------------
    edges = nodes[1:] - nodes[:-1]
    lengths = np.linalg.norm(edges, axis=1)
    if np.any(lengths < _EPS):
        raise ValueError(
            "Two neighbouring rod nodes collapsed (zero edge length). Increase "
            "the axial stiffness EA or reduce the time step."
        )
    strain = lengths / rest.edge_lengths_mm - 1.0
    energy.stretch = float(
        0.5 * material.axial_stiffness_n * np.sum(strain**2 * rest.edge_lengths_mm)
    )
    tangents = edges / lengths[:, None]
    edge_force = (material.axial_stiffness_n * strain)[:, None] * tangents  # [N]
    grad_nodes[1:] += edge_force
    grad_nodes[:-1] -= edge_force

    # ---- bending -------------------------------------------------------
    voronoi = rest.voronoi_lengths_mm
    e0 = nodes[1:-1] - nodes[:-2]
    e1 = nodes[2:] - nodes[1:-1]
    n0 = lengths[:-1]
    n1 = lengths[1:]
    denom = n0 * n1 + np.sum(e0 * e1, axis=1)
    if np.any(denom < _EPS):
        raise ValueError(
            "Rod folded back on itself (a discrete turning angle reached 180 deg). "
            "Reduce the time step or the steering input."
        )
    kb = 2.0 * np.cross(e0, e1) / denom[:, None]
    delta_kb = kb - rest.kb0
    bend_coeff = material.bending_stiffness_n_mm2 / voronoi  # [N mm]
    energy.bend = float(0.5 * np.sum(bend_coeff * np.sum(delta_kb**2, axis=1)))

    # w = dE/dkb  (N mm, dimensionless kb -> newton-millimetre)
    w = bend_coeff[:, None] * delta_kb
    # Using  w^T [v]_x = w x v :
    #   w^T dkb/de0 = (-2 (w x e1) - (w.kb) (n1 t0 + e1)) / denom
    #   w^T dkb/de1 = ( 2 (w x e0) - (w.kb) (n0 t1 + e0)) / denom
    w_dot_kb = np.sum(w * kb, axis=1)[:, None]
    t0 = tangents[:-1]
    t1 = tangents[1:]
    a0 = (-2.0 * np.cross(w, e1) - w_dot_kb * (n1[:, None] * t0 + e1)) / denom[:, None]
    a1 = (2.0 * np.cross(w, e0) - w_dot_kb * (n0[:, None] * t1 + e0)) / denom[:, None]
    grad_nodes[:-2] -= a0
    grad_nodes[1:-1] += a0 - a1
    grad_nodes[2:] += a1

    # ---- twist ---------------------------------------------------------
    twist_increment = phi[1:] - phi[:-1] - rest.dphi0_rad
    twist_coeff = material.torsional_stiffness_n_mm2 / voronoi  # [N mm]
    energy.twist = float(0.5 * np.sum(twist_coeff * twist_increment**2))
    moment = twist_coeff * twist_increment  # [N mm]
    grad_phi[1:] += moment
    grad_phi[:-1] -= moment

    # ---- external loads ------------------------------------------------
    if loads is not None:
        if loads.node_forces_n is not None:
            energy.external += float(-np.sum(loads.node_forces_n * nodes))
            grad_nodes -= loads.node_forces_n
        if loads.edge_torques_n_mm is not None:
            energy.external += float(-np.sum(loads.edge_torques_n_mm * phi))
            grad_phi -= loads.edge_torques_n_mm
        if loads.gravity_mm_per_s2 is not None:
            if material.linear_density_kg_per_mm is None:
                raise ValueError(
                    "Gravity was enabled but 'linear_density_kg_per_mm' is not "
                    "calibrated (CALIBRATION_REQUIRED). Disable gravity or supply "
                    "a density in the parameter profile."
                )
            # Lumped nodal mass from the Voronoi length of each node [kg].
            node_mass = np.zeros(state.n_nodes)
            half = 0.5 * rest.edge_lengths_mm * material.linear_density_kg_per_mm
            node_mass[:-1] += half
            node_mass[1:] += half
            # 1 kg * 1 mm/s^2 = 1e-3 N  ->  weight [N] = m[kg]*g[mm/s^2]*1e-3
            weight = node_mass[:, None] * loads.gravity_mm_per_s2[None, :] * 1.0e-3
            energy.external += float(-np.sum(weight * nodes))
            grad_nodes -= weight

    _check_finite("energy gradient (nodes)", grad_nodes)
    _check_finite("energy gradient (twist)", grad_phi)
    return energy, grad_nodes, grad_phi


def bishop_directors(state: RodState) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(tangents, d1)`` for the current state, both ``(M, 3)``."""
    edges = state.nodes_mm[1:] - state.nodes_mm[:-1]
    tangents = normalise(edges)
    d1 = bishop_frame(tangents, state.d1_first)
    return tangents, d1


def material_directors(state: RodState) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(tangents, m1, m2)`` of the material frame, each ``(M, 3)``."""
    tangents, d1 = bishop_directors(state)
    m1, m2 = material_frame(tangents, d1, state.phi_rad)
    return tangents, m1, m2


def straight_rod(
    origin_mm: np.ndarray,
    direction: np.ndarray,
    total_length_mm: float,
    n_nodes: int,
    d1_first: np.ndarray | None = None,
) -> tuple[RodState, RodRest]:
    """Build a straight, untwisted rod of ``n_nodes`` nodes.

    Args:
        origin_mm: ``(3,)`` position of node 0 [mm].
        direction: ``(3,)`` direction the rod points in (need not be unit).
        total_length_mm: arclength from node 0 to node N-1 [mm].
        n_nodes: number of nodes, must be >= 3.
        d1_first: optional Bishop anchor director; an arbitrary perpendicular
            is chosen when omitted.
    """
    if n_nodes < 3:
        raise ValueError("A discrete elastic rod needs at least 3 nodes.")
    if total_length_mm <= 0.0:
        raise ValueError("total_length_mm must be positive.")
    unit = normalise(np.asarray(direction, dtype=float)[None, :])[0]
    s = np.linspace(0.0, total_length_mm, n_nodes)
    nodes = np.asarray(origin_mm, dtype=float)[None, :] + s[:, None] * unit[None, :]
    edge_lengths = np.full(n_nodes - 1, total_length_mm / (n_nodes - 1))
    if d1_first is None:
        from .frames import any_perpendicular

        d1_first = any_perpendicular(unit)
    state = RodState(
        nodes_mm=nodes,
        phi_rad=np.zeros(n_nodes - 1),
        d1_first=np.asarray(d1_first, dtype=float),
    )
    rest = RodRest(
        edge_lengths_mm=edge_lengths,
        kb0=np.zeros((n_nodes - 2, 3)),
        dphi0_rad=np.zeros(n_nodes - 2),
    )
    return state, rest
