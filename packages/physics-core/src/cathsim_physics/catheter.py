"""Catheter models built on top of the discrete elastic rod.

``CatheterModel`` is the interface every catheter family in the roadmap
implements (GenericSteerableRF, GenericBalloon, GenericLoop,
GenericLatticeSphere, GenericPentasplinePFA).  Only ``GenericSteerableRF`` is
implemented in this milestone; the others raise ``NotImplementedError`` from
the shared base so that the transport and UI layers can already be written
against the final signature.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .config import ConfigError, calibration_status, material_from_profile
from .frames import any_perpendicular, frame_to_quaternion_xyzw, normalise
from .rod import (
    RodMaterial,
    RodRest,
    RodState,
    material_directors,
    straight_rod,
)
from .solver import BoundaryConditions, RodSolver, RodSolverError, SolverSettings


@dataclass(frozen=True)
class EntryPose:
    """Sheath exit ("entry") pose: where the catheter leaves the sheath.

    Attributes:
        position_mm: ``(3,)`` sheath tip position [mm].
        direction: ``(3,)`` sheath axis, pointing into the chamber.
        roll_reference: ``(3,)`` director defining zero handle roll; it is
            re-orthogonalised against ``direction``.
    """

    position_mm: np.ndarray = field(default_factory=lambda: np.zeros(3))
    direction: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))
    roll_reference: np.ndarray | None = None


@dataclass
class ActuationInput:
    """Normalised handle inputs.

    Attributes:
        insertion_mm: deployed length beyond the sheath tip [mm], >= 0.
        axial_rotation_rad: handle roll applied at the sheath tip [rad].
        steer_x: normalised deflection knob, ``[-1, 1]`` [-].
        steer_y: normalised deflection knob, ``[-1, 1]`` [-].
        deployment: expansion parameter, ``[0, 1]``; unused by a steerable RF
            catheter, present for the shared interface.
    """

    insertion_mm: float = 60.0
    axial_rotation_rad: float = 0.0
    steer_x: float = 0.0
    steer_y: float = 0.0
    deployment: float = 0.0

    def validated(self, max_steering_input: float) -> ActuationInput:
        """Clamp the inputs into their legal ranges and reject non-finite ones."""
        values = (
            self.insertion_mm,
            self.axial_rotation_rad,
            self.steer_x,
            self.steer_y,
            self.deployment,
        )
        if not all(np.isfinite(v) for v in values):
            raise ValueError(
                "Actuation input contains NaN or Inf. Check the control that "
                "produced insertion/rotation/steering values."
            )
        limit = float(max_steering_input)
        return ActuationInput(
            insertion_mm=max(0.0, float(self.insertion_mm)),
            axial_rotation_rad=float(self.axial_rotation_rad),
            steer_x=float(np.clip(self.steer_x, -limit, limit)),
            steer_y=float(np.clip(self.steer_y, -limit, limit)),
            deployment=float(np.clip(self.deployment, 0.0, 1.0)),
        )


@dataclass
class ElectrodePose:
    """Pose of one electrode along the catheter."""

    index: int
    arclength_mm: float
    position_mm: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]


class CatheterModel(abc.ABC):
    """Common interface for every catheter family (see the project contract)."""

    @abc.abstractmethod
    def load_parameters(
        self, profile: dict[str, Any], accept_demo_parameters: bool = False
    ) -> None:
        """Read a parameter profile and refuse any uncalibrated physical value."""

    @abc.abstractmethod
    def initialize(self, entry_pose: EntryPose) -> None:
        """Place the catheter at the sheath exit pose and build the solver."""

    @abc.abstractmethod
    def set_insertion(self, insertion_mm: float) -> None:
        """Set the deployed length beyond the sheath tip [mm]."""

    @abc.abstractmethod
    def set_axial_rotation(self, rotation_rad: float) -> None:
        """Set the handle roll applied at the proximal boundary [rad]."""

    @abc.abstractmethod
    def set_steering(self, steer_x: float, steer_y: float) -> None:
        """Set the normalised deflection knob inputs, each in [-1, 1]."""

    @abc.abstractmethod
    def set_deployment(self, deployment: float) -> None:
        """Set the expansion parameter in [0, 1] (basket/flower families)."""

    @abc.abstractmethod
    def step(self, dt_s: float) -> None:
        """Advance the over-damped dynamics by ``dt_s`` seconds."""

    @abc.abstractmethod
    def get_render_geometry(self) -> dict[str, Any]:
        """Return the current SimulationFrame payload."""

    @abc.abstractmethod
    def get_electrode_poses(self) -> list[ElectrodePose]:
        """Return the pose of every electrode along the solved centreline."""

    @abc.abstractmethod
    def get_contact_metrics(self) -> dict[str, Any]:
        """Return the contact metrics for the current frame."""

    @abc.abstractmethod
    def reset(self) -> None:
        """Return to the undeformed configuration at t = 0."""


class GenericSteerableRF(CatheterModel):
    """Generic bidirectional steerable ablation catheter.

    NOT a model of any specific commercial device.  Geometry and material
    values come entirely from the supplied parameter profile.
    """

    def __init__(self) -> None:
        self._profile: dict[str, Any] | None = None
        self._material: RodMaterial | None = None
        self._entry = EntryPose()
        self._actuation = ActuationInput()
        self._state: RodState | None = None
        self._rest: RodRest | None = None
        self._solver: RodSolver | None = None
        self._time_s = 0.0
        self._last_report = None
        self._n_nodes = 0

    # -- configuration ---------------------------------------------------

    def load_parameters(
        self, profile: dict[str, Any], accept_demo_parameters: bool = False
    ) -> None:
        """Read a parameter profile and refuse any uncalibrated physical value."""
        self._material = material_from_profile(profile, accept_demo_parameters)
        self._profile = profile
        geometry = profile["geometry"]
        spacing = float(geometry["node_spacing_mm"])
        if spacing <= 0.0:
            raise ConfigError("geometry.node_spacing_mm must be positive.")
        working = float(geometry.get("working_length_mm", geometry["active_length_mm"] * 2.0))
        self._n_nodes = max(5, round(working / spacing) + 1)

    @property
    def profile(self) -> dict[str, Any]:
        """The loaded parameter profile."""
        if self._profile is None:
            raise ConfigError("load_parameters() must be called before use.")
        return self._profile

    @property
    def calibration(self):  # noqa: ANN201 - dataclass from config module
        """Read a parameter profile and refuse any uncalibrated physical value."""
        return calibration_status(self.profile)

    # -- lifecycle -------------------------------------------------------

    def initialize(self, entry_pose: EntryPose) -> None:
        """Calibration status of the loaded profile."""
        """Calibration status of the loaded profile."""
        """Calibration status of the loaded profile."""
        """Calibration status of the loaded profile."""
        """Calibration status of the loaded profile."""
        """Calibration status of the loaded profile."""
        """Place the catheter at the sheath exit pose and build the solver."""
        if self._material is None:
            raise ConfigError("load_parameters() must be called before initialize().")
        self._entry = entry_pose
        self.reset()

    def reset(self) -> None:
        """Return to a straight, untwisted configuration at t = 0."""
        direction = normalise(np.asarray(self._entry.direction, dtype=float)[None, :])[0]
        roll_reference = self._entry.roll_reference
        d1_first = (
            any_perpendicular(direction)
            if roll_reference is None
            else normalise(
                (
                    np.asarray(roll_reference, dtype=float)
                    - np.dot(roll_reference, direction) * direction
                )[None, :]
            )[0]
        )
        self._state, self._rest = straight_rod(
            np.asarray(self._entry.position_mm, dtype=float),
            direction,
            max(self._actuation.insertion_mm, 1.0),
            self._n_nodes,
            d1_first=d1_first,
        )
        assert self._material is not None
        self._solver = RodSolver(
            self._material,
            self._rest,
            boundary=BoundaryConditions(clamped_nodes=(0, 1), clamped_edges=(0,)),
            settings=SolverSettings(),
        )
        self._time_s = 0.0
        self._last_report = None
        self._apply_boundary_and_rest()

    # -- actuation -------------------------------------------------------

    def _max_steer(self) -> float:
        return float(self.profile["actuation"].get("max_steering_input", 1.0))

    def set_insertion(self, insertion_mm: float) -> None:
        """Set the deployed length beyond the sheath tip [mm]."""
        self._actuation.insertion_mm = insertion_mm
        self._actuation = self._actuation.validated(self._max_steer())
        self._apply_boundary_and_rest()

    def set_axial_rotation(self, rotation_rad: float) -> None:
        """Set the handle roll applied at the proximal boundary [rad]."""
        self._actuation.axial_rotation_rad = rotation_rad
        self._actuation = self._actuation.validated(self._max_steer())
        self._apply_boundary_and_rest()

    def set_steering(self, steer_x: float, steer_y: float) -> None:
        """Set the normalised deflection knob inputs, each in [-1, 1]."""
        self._actuation.steer_x = steer_x
        self._actuation.steer_y = steer_y
        self._actuation = self._actuation.validated(self._max_steer())
        self._apply_boundary_and_rest()

    def set_deployment(self, deployment: float) -> None:
        """Set the expansion parameter in [0, 1] (unused by a steerable RF catheter)."""
        # A steerable RF catheter has no deployable basket; the parameter is
        # accepted (and clamped) for interface compatibility only.
        self._actuation.deployment = deployment
        self._actuation = self._actuation.validated(self._max_steer())

    def set_actuation(self, actuation: ActuationInput) -> None:
        """Apply a full actuation record in one call (used by the API layer)."""
        self._actuation = actuation.validated(self._max_steer())
        self._apply_boundary_and_rest()

    # -- boundary conditions and rest curvature --------------------------

    def _apply_boundary_and_rest(self) -> None:
        """Refresh rest lengths (insertion), the clamp (rotation) and kb0 (steering).

        Insertion is modelled by feeding rod material through the sheath tip:
        the deployed arclength changes while the node count stays constant, so
        the rest length of every edge becomes ``insertion_mm / (N-1)``.  The
        node count is fixed on purpose - a changing DOF count would make the
        solver non-deterministic across frames.
        """
        if self._state is None or self._rest is None:
            return
        state, rest = self._state, self._rest
        geometry = self.profile["geometry"]

        spacing_mm = float(geometry["node_spacing_mm"])
        deployed_mm = max(self._actuation.insertion_mm, 2.0 * spacing_mm)
        edge_length = deployed_mm / (state.n_edges)
        if abs(edge_length - float(rest.edge_lengths_mm[0])) > 1.0e-12:
            self._feed_through_sheath(deployed_mm)
        rest.edge_lengths_mm[:] = edge_length

        # Proximal clamp: node 0 at the sheath tip, node 1 one rest length
        # along the sheath axis -> position + tangent boundary condition.
        direction = normalise(np.asarray(self._entry.direction, dtype=float)[None, :])[0]
        state.nodes_mm[0] = np.asarray(self._entry.position_mm, dtype=float)
        state.nodes_mm[1] = state.nodes_mm[0] + edge_length * direction

        # Handle roll enters as the prescribed twist angle of edge 0.
        state.phi_rad[0] = self._actuation.axial_rotation_rad

        self._update_rest_curvature()

    def _feed_through_sheath(self, deployed_mm: float) -> None:
        """Re-sample the centreline for a new deployed length (insert / retract).

        Advancing the handle pushes catheter material out of the sheath: the
        already-deployed shape is kept and new, initially straight material
        appears beyond the tip along the current tip tangent.  Retracting pulls
        the tip back *along the path the catheter already occupies*.  Both are
        arclength re-parameterisations of the current centreline, which is why
        the node count can stay constant without introducing a spurious stretch
        (naively leaving the nodes in place and only changing the rest lengths
        injects a large artificial axial strain and folds the solver).

        Args:
            deployed_mm: new deployed arclength beyond the sheath tip [mm].
        """
        state = self._state
        assert state is not None
        nodes = state.nodes_mm
        segment_mm = np.linalg.norm(np.diff(nodes, axis=0), axis=1)
        arclength_mm = np.concatenate([[0.0], np.cumsum(segment_mm)])
        current_mm = float(arclength_mm[-1])

        if deployed_mm > current_mm:
            # Extend straight along the tip tangent, then resample.
            tip_tangent = normalise((nodes[-1] - nodes[-2])[None, :])[0]
            nodes = np.vstack([nodes, nodes[-1] + (deployed_mm - current_mm) * tip_tangent])
            arclength_mm = np.concatenate([arclength_mm, [deployed_mm]])

        targets_mm = np.linspace(0.0, deployed_mm, state.n_nodes)
        resampled = np.column_stack(
            [np.interp(targets_mm, arclength_mm, nodes[:, axis]) for axis in range(3)]
        )

        # The twist angle lives on edges; resample it at the edge midpoints.
        old_midpoints_mm = 0.5 * (arclength_mm[:-1] + arclength_mm[1:])
        old_phi = state.phi_rad
        if old_midpoints_mm.size > old_phi.size:  # an edge was appended above
            old_phi = np.concatenate([old_phi, old_phi[-1:]])
        new_midpoints_mm = 0.5 * (targets_mm[:-1] + targets_mm[1:])
        state.phi_rad = np.interp(new_midpoints_mm, old_midpoints_mm, old_phi)
        state.nodes_mm = resampled

    def _update_rest_curvature(self) -> None:
        """Write the steering command into the rest curvature ``kb0``.

        The handle knob does not move the tip directly.  It sets a rest
        curvature over the distal ``active_length_mm`` of the rod, and the rod
        solver decides the resulting shape.  Magnitude::

            curvature0 [1/mm] = steer_gain_rad_per_mm * |steer|

        Direction: the unit bend direction in the material frame is
        ``cos(psi) m1 + sin(psi) m2`` with ``psi = atan2(steer_y, steer_x)``,
        so rolling the handle rolls the steering plane.  The rest curvature
        binormal of interior node ``i`` is then
        ``kb0_i = curvature0 * lbar_i * (t_i x bend_direction)``.

        ``kb0`` is expressed in world coordinates and held fixed while the
        solver relaxes; it is refreshed from the material frame at the start of
        every step, so equilibrium is a consistent fixed point.
        """
        state, rest = self._state, self._rest
        assert state is not None and rest is not None
        geometry = self.profile["geometry"]
        actuation = self.profile["actuation"]

        gain_rad_per_mm = actuation.get("steer_gain_rad_per_mm")
        if gain_rad_per_mm is None:
            raise ConfigError(
                "actuation.steer_gain_rad_per_mm is CALIBRATION_REQUIRED; the "
                "steering command cannot be converted into a rest curvature."
            )

        magnitude = float(np.hypot(self._actuation.steer_x, self._actuation.steer_y))
        rest.kb0[:] = 0.0
        rest.dphi0_rad[:] = 0.0
        if magnitude <= 0.0:
            return

        tangents, m1, m2 = material_directors(state)
        psi = float(np.arctan2(self._actuation.steer_y, self._actuation.steer_x))
        bend_direction = np.cos(psi) * m1 + np.sin(psi) * m2  # (M, 3), unit
        binormal = np.cross(tangents, bend_direction)  # (M, 3), unit

        # Interior node i sits between edges i-1 and i: average the two edges.
        node_binormal = 0.5 * (binormal[:-1] + binormal[1:])

        # Only the distal active_length_mm is actuated.
        edge_length = float(rest.edge_lengths_mm[0])
        arclength_from_tip = (state.n_nodes - 1 - np.arange(1, state.n_nodes - 1)) * edge_length
        active = arclength_from_tip <= float(geometry["active_length_mm"])

        curvature0_per_mm = float(gain_rad_per_mm) * magnitude
        voronoi = rest.voronoi_lengths_mm
        rest.kb0[active] = curvature0_per_mm * voronoi[active][:, None] * node_binormal[active]

    # -- simulation ------------------------------------------------------

    def step(self, dt_s: float) -> None:
        """Advance the over-damped rod dynamics by ``dt_s`` seconds."""
        if self._solver is None or self._state is None:
            raise ConfigError("initialize() must be called before step().")
        self._apply_boundary_and_rest()
        try:
            self._state, self._last_report = self._solver.step(self._state, dt_s)
        except (RodSolverError, ValueError) as exc:
            raise RodSolverError(
                f"The rod solver stopped safely at t = {self._time_s:.3f} s: {exc}"
            ) from exc
        self._time_s += dt_s

    def solve_static(self, max_outer_iterations: int = 12, tolerance_mm: float = 1.0e-4) -> int:
        """Relax to equilibrium for the current actuation state.

        The rest curvature ``kb0`` is expressed in world coordinates and is
        rebuilt from the material frame, which itself depends on the solved
        shape.  Equilibrium is therefore the fixed point of

            solve(kb0(shape))  ->  shape  ->  kb0(shape)  ->  ...

        This loop iterates it until the centreline stops moving.  In practice
        one pass suffices for a pure steering change and two to four for a
        handle roll (which has to propagate the twist first).

        Args:
            max_outer_iterations: cap on fixed-point passes.
            tolerance_mm: max node displacement between two passes that counts
                as converged.

        Returns:
            The number of fixed-point passes performed.
        """
        if self._solver is None or self._state is None:
            raise ConfigError("initialize() must be called before solve_static().")
        assert self._rest is not None
        for iteration in range(1, max_outer_iterations + 1):
            self._apply_boundary_and_rest()
            kb0_used = self._rest.kb0.copy()
            previous_nodes = self._state.nodes_mm.copy()

            self._state, self._last_report = self._solver.solve_static(self._state)

            movement_mm = float(np.abs(self._state.nodes_mm - previous_nodes).max(initial=0.0))
            # Fixed-point residual: rebuild kb0 from the *solved* shape and see
            # whether it still agrees with the kb0 the solve was given.  A pure
            # handle roll changes kb0 without moving a single node (the twist
            # DOF is decoupled from the positions in the Bishop
            # parameterisation), so checking node movement alone would declare
            # convergence one pass too early.
            self._update_rest_curvature()
            rest_curvature_change = float(np.abs(self._rest.kb0 - kb0_used).max(initial=0.0))
            if movement_mm <= tolerance_mm and rest_curvature_change <= 1.0e-6:
                return iteration
        return max_outer_iterations

    # -- outputs ---------------------------------------------------------

    @property
    def time_s(self) -> float:
        """Simulated time since the last reset [s]."""
        return self._time_s

    @property
    def state(self) -> RodState:
        """The current rod state (read-only from outside the physics layer)."""
        if self._state is None:
            raise ConfigError("initialize() must be called first.")
        return self._state

    def get_render_geometry(self) -> dict[str, Any]:
        """Return the current SimulationFrame payload."""
        state = self.state
        tangents, m1, m2 = material_directors(state)
        quats = frame_to_quaternion_xyzw(tangents, m1, m2)
        report = self._last_report
        return {
            "time_s": self._time_s,
            "centerline_mm": state.nodes_mm.tolist(),
            "orientations_xyzw": quats.tolist(),
            "radius_mm": float(self.profile["contact"]["catheter_collision_radius_mm"]),
            "electrodes": [
                {
                    "index": e.index,
                    "arclength_mm": e.arclength_mm,
                    "position_mm": list(e.position_mm),
                    "orientation_xyzw": list(e.orientation_xyzw),
                }
                for e in self.get_electrode_poses()
            ],
            "contacts": [],
            "solver": {
                "iterations": int(report.iterations) if report else 0,
                "residual": float(report.residual) if report else 0.0,
                "max_penetration_mm": float(report.max_penetration_mm) if report else 0.0,
                "converged": bool(report.converged) if report else True,
                "energy_n_mm": {
                    "stretch": report.energy.stretch if report else 0.0,
                    "bend": report.energy.bend if report else 0.0,
                    "twist": report.energy.twist if report else 0.0,
                    "total": report.energy.total if report else 0.0,
                },
            },
        }

    def get_electrode_poses(self) -> list[ElectrodePose]:
        """Electrode poses interpolated along the solved centreline."""
        state = self.state
        electrodes = self.profile.get("electrodes", {})
        offsets = electrodes.get("arclength_from_tip_mm", [])
        if not offsets:
            return []
        tangents, m1, m2 = material_directors(state)
        quats = frame_to_quaternion_xyzw(tangents, m1, m2)
        edge_length = float(self._rest.edge_lengths_mm[0]) if self._rest is not None else 1.0
        total_mm = edge_length * state.n_edges
        poses: list[ElectrodePose] = []
        for index, offset_mm in enumerate(offsets):
            arclength = float(np.clip(total_mm - float(offset_mm), 0.0, total_mm))
            position_index = arclength / edge_length
            lower = int(np.clip(np.floor(position_index), 0, state.n_nodes - 2))
            fraction = float(position_index - lower)
            point = (1.0 - fraction) * state.nodes_mm[lower] + fraction * state.nodes_mm[lower + 1]
            poses.append(
                ElectrodePose(
                    index=index,
                    arclength_mm=arclength,
                    position_mm=(float(point[0]), float(point[1]), float(point[2])),
                    orientation_xyzw=tuple(float(v) for v in quats[lower]),
                )
            )
        return poses

    def get_contact_metrics(self) -> dict[str, Any]:
        """Contact metrics. Empty until Milestone 2 adds the mesh contact stage."""
        return {
            "available": False,
            "reason": "Mesh contact is implemented in Milestone 2.",
            "max_penetration_mm": 0.0,
            "contact_count": 0,
        }
