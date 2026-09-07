"""FastAPI transport for the CathSim LA reference solver.

The viewer runs its own real-time solver in the browser, so this service is not
on the critical path for Milestone 0/1.  It exists so that the transport
boundary is real code rather than a diagram: the reference (and, from Milestone
3, the C++) solver can be driven over HTTP and WebSocket by other clients and
by batch studies.

Live control uses a WebSocket.  Commands carry a ``sequence`` number; a command
whose sequence is not newer than the last applied one is dropped, so
out-of-order or delayed delivery is handled deterministically instead of
producing order-dependent motion.

Research prototype - Not for clinical use.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np
from cathsim_physics import (
    ActuationInput as CoreActuation,
)
from cathsim_physics import (
    ConfigError,
    EntryPose,
    GenericSteerableRF,
    RodSolverError,
    calibration_status,
    load_profile,
)
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    ActuationInput,
    CalibrationStatusModel,
    ContactMetrics,
    ElectrodePose,
    ServiceInfo,
    SimulationFrame,
    SimulationSettings,
    SolverReport,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CONFIG_DIR = REPO_ROOT / "configs"

app = FastAPI(
    title="CathSim LA simulation API",
    version="0.1.0",
    description=(
        "Research prototype - Not for clinical use. Geometric similarity is "
        "not mechanical accuracy. No lesion, electric-field, PFA-threshold or "
        "thermal prediction is performed."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=ServiceInfo)
def health() -> ServiceInfo:
    """Liveness probe; also carries the research-only disclaimer."""
    return ServiceInfo()


@app.get("/profiles")
def list_profiles() -> list[dict[str, Any]]:
    """List the available parameter profiles and their calibration status."""
    profiles: list[dict[str, Any]] = []
    for path in sorted(CONFIG_DIR.glob("*.json")):
        try:
            profile = load_profile(path)
        except ConfigError as error:
            profiles.append({"name": path.name, "error": str(error)})
            continue
        status = calibration_status(profile)
        profiles.append(
            {
                "name": path.name,
                "model_type": profile.get("model_type"),
                "display_name": profile.get("display_name"),
                "status": profile.get("status"),
                "calibration": CalibrationStatusModel(
                    missing_fields=list(status.missing_fields),
                    is_demo_profile=status.is_demo_profile,
                    material_source=status.material_source,
                    geometry_source=status.geometry_source,
                    ready_for_simulation=status.ready_for_simulation,
                ).model_dump(),
            }
        )
    return profiles


def _load_model(profile_name: str, settings: SimulationSettings) -> GenericSteerableRF:
    path = CONFIG_DIR / profile_name
    if not path.is_file() or path.parent != CONFIG_DIR:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No parameter profile named '{profile_name}' in configs/. "
                f"Call GET /profiles to see what is available."
            ),
        )
    try:
        profile = load_profile(path)
        model = GenericSteerableRF()
        model.load_parameters(profile, accept_demo_parameters=settings.accept_demo_parameters)
    except ConfigError as error:
        # 422: the request is well formed but the profile cannot be simulated.
        raise HTTPException(status_code=422, detail=str(error)) from error
    model.initialize(EntryPose(np.zeros(3), np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])))
    return model


def _to_frame(model: GenericSteerableRF) -> SimulationFrame:
    geometry = model.get_render_geometry()
    solver = geometry["solver"]
    return SimulationFrame(
        time_s=geometry["time_s"],
        centerline_mm=[tuple(point) for point in geometry["centerline_mm"]],
        orientations_xyzw=[tuple(q) for q in geometry["orientations_xyzw"]],
        electrodes=[ElectrodePose(**electrode) for electrode in geometry["electrodes"]],
        contacts=[],
        solver=SolverReport(
            iterations=solver["iterations"],
            residual=solver["residual"],
            max_penetration_mm=solver["max_penetration_mm"],
            converged=solver["converged"],
        ),
    )


@app.post("/simulate/static", response_model=SimulationFrame)
def simulate_static(
    actuation: ActuationInput,
    settings: SimulationSettings,
    profile: str = "demo-steerable-rf.json",
) -> SimulationFrame:
    """Relax to static equilibrium for one actuation state."""
    model = _load_model(profile, settings)
    model.set_actuation(
        CoreActuation(
            insertion_mm=actuation.insertion_mm,
            axial_rotation_rad=actuation.axial_rotation_rad,
            steer_x=actuation.steer_x,
            steer_y=actuation.steer_y,
            deployment=actuation.deployment,
        )
    )
    try:
        model.solve_static()
    except (RodSolverError, ValueError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return _to_frame(model)


@app.get("/contact-metrics", response_model=ContactMetrics)
def contact_metrics() -> ContactMetrics:
    """Contact metrics are added in Milestone 2; the shape is stable already."""
    return ContactMetrics()


@app.websocket("/ws/simulate")
async def websocket_simulate(websocket: WebSocket) -> None:
    """Live control.

    Protocol: the client sends ``{"type": "init", ...}`` once, then
    ``{"type": "actuation", ...}`` messages carrying a monotonically increasing
    ``sequence``.  The server steps the model on its own clock and pushes a
    ``SimulationFrame`` after every step.
    """
    await websocket.accept()
    model: GenericSteerableRF | None = None
    settings = SimulationSettings()
    last_sequence = -1

    async def receive_loop() -> None:
        nonlocal model, settings, last_sequence
        while True:
            message = json.loads(await websocket.receive_text())
            kind = message.get("type")
            if kind == "init":
                settings = SimulationSettings(**message.get("settings", {}))
                model = _load_model(message.get("profile", "demo-steerable-rf.json"), settings)
                last_sequence = -1
            elif kind == "actuation" and model is not None:
                command = ActuationInput(**message.get("actuation", {}))
                # Deterministic handling of late / out-of-order commands.
                if command.sequence <= last_sequence:
                    continue
                last_sequence = command.sequence
                model.set_actuation(
                    CoreActuation(
                        insertion_mm=command.insertion_mm,
                        axial_rotation_rad=command.axial_rotation_rad,
                        steer_x=command.steer_x,
                        steer_y=command.steer_y,
                        deployment=command.deployment,
                    )
                )

    async def step_loop() -> None:
        while True:
            await asyncio.sleep(settings.dt_s)
            if model is None:
                continue
            try:
                model.step(settings.dt_s)
            except (RodSolverError, ValueError) as error:
                # Safe stop: report and wait for a new command rather than
                # streaming meaningless geometry.
                await websocket.send_text(json.dumps({"type": "error", "detail": str(error)}))
                continue
            await websocket.send_text(
                json.dumps({"type": "frame", "frame": _to_frame(model).model_dump()})
            )

    try:
        await asyncio.gather(receive_loop(), step_loop())
    except (WebSocketDisconnect, json.JSONDecodeError):
        return
    except HTTPException as error:
        await websocket.send_text(json.dumps({"type": "error", "detail": error.detail}))
