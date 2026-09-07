# Architecture

**Research prototype - Not for clinical use.**

## Layering rule

Four layers, and dependencies only ever point downward. This is the rule that
keeps the physics testable and keeps "just nudge the centreline for the
animation" from ever becoming possible.

```text
  UI            apps/viewer/src/components, state
    |             React, Zustand, Three.js. Writes ACTUATION only.
    v
  Transport     services/simulation-api  (packages/shared-schema types both ends)
    |             Schema-typed frames. No physics, no rendering.
    |             The viewer runs its solver locally, so it does not use this
    |             layer today; the boundary exists as real code so that batch
    |             studies and the Milestone 3 C++ core can drive the solver.
    v
  Geometry      packages/geometry-core, apps/viewer/src/geometry
    |             Meshes, BVH, mesh QA. No physics state.
    v
  Physics       packages/physics-core (reference), apps/viewer/src/physics (real time)
                  Rod state, energy, gradient, solver. No React, no Three.js.
```

Concretely:

* The UI never touches `RodState`. It writes `insertion`, `axial rotation`,
  `steer x/y` and `deployment` into the store; the simulation loop forwards
  them to the model; the model returns a `SimulationFrame`.
* The physics core imports nothing from React, Three.js or the DOM. It is
  exercised entirely from Node and from pytest.
* The renderer reads the latest frame and never writes to it.

## Repository map

```text
cathsim-la/
  CathSim_LA_Claude_Code_Master_Prompt.md   the project contract
  configs/                     catheter parameter profiles (schema-versioned)
  docs/                        architecture, physics, validation, assumptions, ADRs
  packages/
    physics-core/              Python reference rod solver + validation suite
    geometry-core/             mesh QA and BVH (Milestone 2)
    shared-schema/             JSON Schema -> Pydantic + TypeScript types
  services/
    simulation-api/            FastAPI + WebSocket transport
  apps/
    viewer/                    React + TypeScript + Three.js viewer
      src/physics/             real-time TypeScript port of the reference solver
  tests/reference-data/        golden data shared by both implementations
  scripts/                     reference-data generation and helpers
```

## Two solver implementations, one interface

| | Reference | Real-time |
| --- | --- | --- |
| Location | `packages/physics-core` | `apps/viewer/src/physics` |
| Language | Python + NumPy/SciPy | TypeScript |
| Minimiser | SciPy L-BFGS-B (More-Thuente line search) | L-BFGS with Armijo backtracking |
| Role | Validated against analytic solutions; generates golden data | Runs the viewer at interactive rates |
| Budget | Unbounded; correctness first | Wall-clock budget per frame, persistent curvature history |

Both implement the same catheter interface required by the contract:

```text
CatheterModel
  loadParameters(config)      initialize(entryPose)
  setInsertion(mm)            setAxialRotation(rad)
  setSteering(x, y)           setDeployment(value)
  step(dt)                    reset()
  getRenderGeometry()         getElectrodePoses()      getContactMetrics()
```

`GenericSteerableRF` implements it today. `GenericBalloon`, `GenericLoop`,
`GenericLatticeSphere` and `GenericPentasplinePFA` are planned derivations; the
abstract base exists so the transport and UI layers are already written against
the final signature.

Milestone 3 replaces the *reference* leg with a C++20 core behind pybind11. It
reuses `tests/reference-data/` unchanged, so parity is measured the same way.

## Data flow of one frame

```text
  keyboard / slider
        |  actuation only
        v
  Zustand store  --->  useSimulationLoop (fixed-rate timer at solverHz)
                              |
                              | setActuation()  -> boundary conditions + rest curvature
                              v
                       GenericSteerableRF.step(dt)
                              |
                              | implicit over-damped solve (L-BFGS)
                              v
                       SimulationFrame  ---> frameRef
                              |                    |
                              | metrics            | requestAnimationFrame
                              v                    v
                        store.publishFrame     SceneView renders
```

The physics timer and the render loop run at independent rates. They currently
share the browser main thread; a Web Worker is Milestone 3 work (assumption
A13).

## Schema

`packages/shared-schema/schemas/*.schema.json` is the single source of truth.
`scripts/generate_types.py` derives the TypeScript interfaces from it, and the
Pydantic models in `services/simulation-api` are validated against the same
files at import time. A profile carries `schema_version`; an unknown version is
rejected rather than coerced.

## Safety and data handling

* The default anatomy is synthetic and is labelled as a placeholder everywhere
  it appears.
* No DICOM in this milestone. No patient name, identifier, date or DICOM tag is
  ever read or stored.
* Uploaded meshes are processed locally; file size, triangle count and parse
  time are bounded (Milestone 2, `packages/geometry-core`).
* Logs never contain file contents.
