# CathSim LA

> **Research prototype - Not for clinical use.**
>
> This is not a medical device. It must not be used for diagnosis, treatment
> planning, procedure rehearsal or device selection. Geometric similarity is
> not mechanical accuracy. See [`docs/regulatory-boundary.md`](docs/regulatory-boundary.md).

A research prototype for simulating the 3D motion, bending, twisting and
mechanical tissue contact of ablation catheters inside a patient-specific left
atrium geometry.

**Current state: Milestone 0 complete, Milestone 1 complete.** A validated
steerable catheter driven by a discrete elastic rod solver, running in a
browser viewer, with an analytic validation suite. Mesh import and contact are
Milestone 2 and are **not** implemented yet.

---

## Quick start

Requires Node 20+ and Python 3.11+.

```bash
# 1. Python side (reference solver, validation suite, API)
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e packages/physics-core

# 2. JavaScript side (viewer)
npm install

# 3. Run the viewer
npm run dev            # -> http://localhost:5173
```

The viewer opens on a synthetic chamber with a generic steerable catheter. Use
the sliders on the right, or:

| Key | Action |
| --- | --- |
| `W` / `S` | insert / retract |
| `A` / `D` | rotate the handle |
| `←` `→` `↑` `↓` | steer X / Y |
| `Space` | play / pause |
| `R` | reset |

Shortcuts are ignored while a text field or slider has focus. Every control is
reachable with `Tab`.

### Run the tests

```bash
.venv/bin/python -m pytest              # Python reference solver + geometry + API (42 tests)
npm test                                # TypeScript solver, parity and UI (28 tests)
npm run typecheck && npm run lint       # TypeScript types and ESLint
.venv/bin/ruff check packages services scripts   # Python lint
.venv/bin/ruff format --check packages services scripts
```

End-to-end (needs a browser):

```bash
npx playwright install chromium         # or point at a pre-installed one:
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium npm run test:e2e
```

### Optional: the transport API

```bash
.venv/bin/uvicorn cathsim_api.app:app --app-dir services/simulation-api/src --reload
# http://127.0.0.1:8000/docs
```

The viewer runs its own solver in the browser and does **not** need this
service. It exists so that the reference solver (and, from Milestone 3, the C++
core) can be driven by other clients and by batch studies.

---

## What works today

* **A discrete elastic rod**, not an animated polyline. Node positions plus a
  material twist angle per edge, with stretch, bending and torsion energies and
  an exact analytic gradient.
* **Steering as rest curvature.** The knob sets the rod's rest curvature over
  the distal active length; the solver decides the shape. No code path moves a
  centreline point to make the animation look right.
* **Insertion, axial rotation, two-axis steering**, all as boundary or
  rest-state inputs.
* **Two independent implementations** - a Python/SciPy reference and a
  TypeScript real-time solver - agreeing to between 4.5e-15 and 1.2e-4 mm RMS
  on the shared golden data.
* **A calibration gate.** Uncalibrated physical parameters are `null` and block
  simulation. A clearly labelled demo profile is opt-in.
* **A validation suite** with justified tolerances - see
  [`docs/validation-plan.md`](docs/validation-plan.md).

### Measured validation results

| Check | Result |
| --- | --- |
| Cantilever vs `δ = F L³ / (3 E I)` | raw error 7.38 / 3.73 / 1.88 % at N = 21 / 41 / 81; **clamp-corrected 0.075 / 0.026 / 0.014 %** |
| Convergence order of that error | 0.99, 0.99 (first order, as the discretisation predicts) |
| Pure bending vs target curvature | 0.0000 % |
| Pure torsion vs `θ = T L / (G J)` | 0.0000 % |
| Rigid-body invariance of the energy | 1.0e-15 relative |
| Time-step sensitivity (`dt` halved) | 0.0003 % of span |
| Energy dissipation after load removal | monotone decay, 0 non-decreasing steps |
| Determinism | bitwise identical |
| Python ↔ TypeScript parity | 4.5e-15 … 1.2e-4 mm RMS |
| Tip turn angle vs `gain × active length` | 0.01 % |
| 90° handle roll rotates the steering plane | 90.00°, deflection magnitude unchanged |
| Real-time solve cost | ~6 ms/frame at 71 nodes (~160 Hz capable; the UI targets 30 Hz) |

---

## Known limitations

Read this section before drawing any conclusion from the software.

1. **No parameter has been measured on a real catheter.** Every material and
   actuation value in `configs/generic-steerable-rf.json` is `null` and blocks
   simulation. The demo profile's numbers are arbitrary placeholders chosen to
   make the software demonstrable; the damping values are *derived from a
   target settling time*, not measured. See
   [`docs/assumptions.md`](docs/assumptions.md).
2. **No contact.** Mesh import, BVH, penetration, contact normals, contact
   force estimates and the heat-map are Milestone 2. `max_penetration_mm` and
   the `contacts` array exist in the schema and report zero / empty.
3. **No lesion, electric-field, PFA-threshold or thermal prediction.** Out of
   scope by design.
4. **No STL/OBJ import.** The only anatomy is a procedurally generated sphere
   with a tubular stub - a shape placeholder, not anatomy, and not patient data.
5. **Bend-twist coupling is omitted.** Sound for a proximally clamped, distally
   free catheter (assumption A2); must be revisited before the pentaspline
   model, whose struts are constrained at both ends.
6. **Bending is isotropic.** Correct for the round section assumed here; a
   keyed or flattened shaft would not be reproduced.
7. **An interactive frame may end before the implicit step converges.** The
   browser solver runs to a wall-clock budget. It still descends the same
   physical energy and reaches the validated equilibrium within ~40 frames, and
   the shortfall is shown in the HUD (`Converged: no` plus the residual) rather
   than hidden.
8. **The Python reference solver is slow** (hundreds to thousands of L-BFGS
   iterations for a cold static solve; ~1.6 s for the demo steering case). It is
   a reference implementation. The C++ core is Milestone 3.
9. **First-order clamp bias**: fixing two nodes makes the compliant span
   `L - h/2`, giving ~1.9 % tip-deflection error at `h/L = 1/80`.
10. **Physics and rendering share the browser main thread**, decoupled only in
    rate. A Web Worker is Milestone 3.
11. **No C++ core, no pybind11, no Docker Compose yet** - see the deviations
    table in [`docs/assumptions.md`](docs/assumptions.md#4-deviations-from-the-project-contract).

---

## Repository layout

```text
configs/          catheter parameter profiles (schema-versioned, calibration-gated)
docs/             architecture, physics model, validation plan, assumptions, ADRs
packages/
  physics-core/   Python reference rod solver + validation suite
  geometry-core/  mesh QA limits and synthetic anatomy (Milestone 2 expands this)
  shared-schema/  JSON Schema -> Pydantic + TypeScript types
services/
  simulation-api/ FastAPI + WebSocket transport
apps/viewer/      React + TypeScript + Three.js viewer, with the real-time solver
tests/reference-data/  golden data shared by both solver implementations
scripts/          reference-data and type generation
```

## Catheter display models (Blender)

`scripts/blender/generic_steerable_rf_blender.py` builds an illustrative,
class-level cutaway model of the `GenericSteerableRF` catheter (distal
assembly with transmitter coil, precision spring and location sensors, six
electrodes, steering pull wires, handle with cam mechanism) - `.blend` with three
deflection poses, plus `.glb` / `.obj` / `.stl` and preview renders - from the
same parameter profile the physics core uses. It runs inside Blender or with
the `bpy` wheel. Provenance and the placeholder list are in
[`assets/demo/catheters/README.md`](assets/demo/catheters/README.md); it is
not a model of any specific commercial device.

## Documentation

| Document | What it covers |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | Layering rule, data flow, the two solver implementations |
| [`docs/physics-model.md`](docs/physics-model.md) | Continuous energy, its discretisation, the analytic gradient, actuation |
| [`docs/validation-plan.md`](docs/validation-plan.md) | Every test, its tolerance and *why* that tolerance; the bench programme |
| [`docs/assumptions.md`](docs/assumptions.md) | Known / assumed / calibration-required, and deviations from the contract |
| [`docs/catheter-parameter-guide.md`](docs/catheter-parameter-guide.md) | Every profile field, its unit and how to measure it |
| [`docs/regulatory-boundary.md`](docs/regulatory-boundary.md) | What this software is and is not |
| [`docs/adr/0001-physics-architecture.md`](docs/adr/0001-physics-architecture.md) | Why a discrete elastic rod rather than XPBD |
| [`CathSim_LA_Claude_Code_Master_Prompt.md`](CathSim_LA_Claude_Code_Master_Prompt.md) | The project contract |

## Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| 0 | Repository, CI, viewer skeleton, synthetic mesh | **done** |
| 1 | Validated steerable rod, analytic tests, debug panel | **done** |
| 2 | STL/OBJ import, mesh QA, BVH contact, penetration and heat-map | next |
| 3 | C++20 core, pybind11, Python ↔ C++ parity, profiling | planned |
| 4 | `GenericPentasplinePFA`, mechanical basket/flower transition | planned |
| 5 | CathFit raw metrics (coverage, gaps, apposition) | planned |

## Licence

MIT, with an explicit research-only notice. See [`LICENSE`](LICENSE).
