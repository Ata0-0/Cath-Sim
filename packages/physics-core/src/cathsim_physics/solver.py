"""Quasi-static / over-damped solver for the discrete elastic rod.

Time integration
----------------
Catheter manipulation at clinical speeds is heavily damped and essentially
quasi-static.  We therefore integrate the rod with the *minimising movement*
(implicit gradient-flow / backward-Euler on over-damped dynamics) scheme

.. code-block:: text

    q^{n+1} = argmin_q [ E(q) + 1/(2 dt) sum_k  c_k (q_k - q_k^n)^2 ]

whose stationarity condition is  ``c (q^{n+1} - q^n)/dt = -grad E(q^{n+1})``,
i.e. backward Euler applied to ``c q_dot = -grad E``.  The scheme is
unconditionally stable (no CFL limit from the stiff bending term), is
energy-dissipating by construction, and reduces to the static equilibrium
problem as ``dt -> inf``.  That gives us the two solver entry points below:
:meth:`RodSolver.solve_static` and :meth:`RodSolver.step`.

Both are driven by L-BFGS-B on the *free* degrees of freedom with the exact
analytic gradient from :mod:`cathsim_physics.rod`.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from .rod import (
    EnergyBreakdown,
    ExternalLoads,
    RodMaterial,
    RodRest,
    RodState,
    energy_and_gradient,
)


@dataclass(frozen=True)
class BoundaryConditions:
    """Which degrees of freedom are prescribed rather than solved for.

    A proximally clamped catheter fixes node 0 and node 1 (position + tangent)
    and the twist angle of edge 0 (the handle roll).  Everything distal is free.

    Attributes:
        clamped_nodes: indices of nodes whose position is prescribed.
        clamped_edges: indices of edges whose twist angle is prescribed.
    """

    clamped_nodes: tuple[int, ...] = (0, 1)
    clamped_edges: tuple[int, ...] = (0,)


@dataclass(frozen=True)
class SolverSettings:
    """Numerical settings of the solver.

    Attributes:
        max_iterations: L-BFGS-B iteration cap per call.
        gradient_tolerance_n: convergence threshold on the infinity norm of the
            free-DOF gradient.  Positional entries are newtons, twist entries
            newton-millimetres; the same scalar threshold is used for both,
            which is why it is reported next to the residual in the UI.
        history_size: L-BFGS-B memory.  A rod couples a very stiff local
            stretch mode to a very soft global bending mode (condition number
            ~1e5 for a 80 mm shaft), so a *large* limited-memory history pays
            for itself: on the demo steering case, 20 corrections need 14624
            iterations while 150 corrections need 607.  See
            ``docs/physics-model.md``.
    """

    max_iterations: int = 3000
    gradient_tolerance_n: float = 1.0e-6
    history_size: int = 150


@dataclass
class SolverReport:
    """Diagnostics of a single solver call, mirrored into ``SimulationFrame``."""

    iterations: int = 0
    residual: float = 0.0
    max_penetration_mm: float = 0.0
    converged: bool = True
    energy: EnergyBreakdown = field(default_factory=EnergyBreakdown)
    message: str = ""


class RodSolverError(RuntimeError):
    """Raised when the solver cannot produce a usable configuration."""


class RodSolver:
    """Over-damped implicit solver for a single :class:`RodState`."""

    def __init__(
        self,
        material: RodMaterial,
        rest: RodRest,
        boundary: BoundaryConditions | None = None,
        settings: SolverSettings | None = None,
    ) -> None:
        self.material = material
        self.rest = rest
        self.boundary = boundary or BoundaryConditions()
        self.settings = settings or SolverSettings()

    # -- degree-of-freedom packing ---------------------------------------

    def _free_masks(self, state: RodState) -> tuple[np.ndarray, np.ndarray]:
        node_mask = np.ones(state.n_nodes, dtype=bool)
        node_mask[list(self.boundary.clamped_nodes)] = False
        edge_mask = np.ones(state.n_edges, dtype=bool)
        edge_mask[list(self.boundary.clamped_edges)] = False
        return node_mask, edge_mask

    def _pack(self, state: RodState, node_mask: np.ndarray, edge_mask: np.ndarray) -> np.ndarray:
        return np.concatenate([state.nodes_mm[node_mask].ravel(), state.phi_rad[edge_mask]])

    def _unpack(
        self,
        vector: np.ndarray,
        template: RodState,
        node_mask: np.ndarray,
        edge_mask: np.ndarray,
    ) -> RodState:
        n_free_nodes = int(node_mask.sum())
        nodes = template.nodes_mm.copy()
        phi = template.phi_rad.copy()
        nodes[node_mask] = vector[: 3 * n_free_nodes].reshape(n_free_nodes, 3)
        phi[edge_mask] = vector[3 * n_free_nodes :]
        return RodState(nodes, phi, template.d1_first)

    # -- solves ----------------------------------------------------------

    def solve_static(
        self,
        state: RodState,
        loads: ExternalLoads | None = None,
    ) -> tuple[RodState, SolverReport]:
        """Relax to static equilibrium (``dt -> inf``, no inertia term)."""
        return self._minimise(state, loads, previous=None, damping_scale_per_s=0.0)

    def step(
        self,
        state: RodState,
        dt_s: float,
        loads: ExternalLoads | None = None,
    ) -> tuple[RodState, SolverReport]:
        """Advance the over-damped dynamics by ``dt_s`` seconds."""
        if not np.isfinite(dt_s) or dt_s <= 0.0:
            raise RodSolverError(
                f"Time step must be a positive finite number of seconds, got {dt_s!r}."
            )
        return self._minimise(state, loads, previous=state, damping_scale_per_s=1.0 / dt_s)

    def _dissipation_weights(self, state: RodState) -> tuple[np.ndarray, np.ndarray]:
        """Per-node [N s/mm] and per-edge [N mm s/rad] damping weights."""
        half = 0.5 * self.rest.edge_lengths_mm
        node_length = np.zeros(state.n_nodes)
        node_length[:-1] += half
        node_length[1:] += half
        node_damping = self.material.damping_n_s_per_mm * node_length
        edge_damping = self.material.torsional_damping_n_mm_s_per_rad * self.rest.edge_lengths_mm
        return node_damping, edge_damping

    def _minimise(
        self,
        state: RodState,
        loads: ExternalLoads | None,
        previous: RodState | None,
        damping_scale_per_s: float,
    ) -> tuple[RodState, SolverReport]:
        node_mask, edge_mask = self._free_masks(state)
        if not node_mask.any():
            raise RodSolverError("Every node is clamped; there is nothing to solve.")

        node_damping, edge_damping = self._dissipation_weights(state)
        prev_nodes = previous.nodes_mm.copy() if previous is not None else None
        prev_phi = previous.phi_rad.copy() if previous is not None else None

        def objective(vector: np.ndarray) -> tuple[float, np.ndarray]:
            trial = self._unpack(vector, state, node_mask, edge_mask)
            energy, grad_nodes, grad_phi = energy_and_gradient(
                trial, self.rest, self.material, loads
            )
            total = energy.total
            if prev_nodes is not None and damping_scale_per_s > 0.0:
                dx = trial.nodes_mm - prev_nodes
                dphi = trial.phi_rad - prev_phi
                total += (
                    0.5
                    * damping_scale_per_s
                    * float(np.sum(node_damping[:, None] * dx**2) + np.sum(edge_damping * dphi**2))
                )
                grad_nodes = grad_nodes + damping_scale_per_s * node_damping[:, None] * dx
                grad_phi = grad_phi + damping_scale_per_s * edge_damping * dphi
            gradient = np.concatenate([grad_nodes[node_mask].ravel(), grad_phi[edge_mask]])
            return total, gradient

        x0 = self._pack(state, node_mask, edge_mask)
        try:
            result = minimize(
                objective,
                x0,
                jac=True,
                method="L-BFGS-B",
                options={
                    "maxiter": self.settings.max_iterations,
                    "maxcor": self.settings.history_size,
                    "gtol": self.settings.gradient_tolerance_n,
                    "ftol": 1.0e-16,
                },
            )
        except ValueError as exc:  # raised by rod.py on NaN / folded geometry
            raise RodSolverError(str(exc)) from exc

        solved = self._unpack(result.x, state, node_mask, edge_mask)
        energy, grad_nodes, grad_phi = energy_and_gradient(solved, self.rest, self.material, loads)
        residual = float(
            max(
                np.abs(grad_nodes[node_mask]).max(initial=0.0),
                np.abs(grad_phi[edge_mask]).max(initial=0.0),
            )
        )
        report = SolverReport(
            iterations=int(result.nit),
            residual=residual,
            max_penetration_mm=0.0,  # populated by the contact stage (Milestone 2)
            converged=bool(np.all(np.isfinite(solved.nodes_mm)))
            and (bool(result.success) or residual <= self.settings.gradient_tolerance_n),
            energy=energy,
            message=str(result.message),
        )
        return solved, report
