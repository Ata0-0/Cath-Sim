# Validation plan

**Research prototype - Not for clinical use.**

Looking plausible is not an acceptance criterion. Every physics milestone is
gated on automated tests with **stated, justified tolerances**. A failing test
is never skipped, deleted, or widened without recording the reason here.

Two things are validated separately and must not be confused:

1. **Numerical validation** - does the code solve the equations it claims to
   solve? Covered below and running today.
2. **Physical validation** - do those equations describe a real catheter? That
   requires the bench programme in section 3 and has **not** been done. Until
   it has, every material and actuation number stays `CALIBRATION_REQUIRED`.

---

## 1. Numerical validation suite (running)

Run with:

```bash
.venv/bin/python -m pytest packages/physics-core/tests -q -s   # Python reference
npm test                                                        # TypeScript real-time solver + UI
```

| ID | Test | Tolerance | Rationale for the tolerance | Measured |
| --- | --- | --- | --- | --- |
| **V0** | Analytic gradient vs central finite differences | relative error < 1e-6 | Central differences at `h = 1e-6` on an O(1e3) energy carry ~1e-8 relative truncation/round-off noise. 1e-6 leaves head-room without being able to hide a real error. | ~1e-9 |
| **V1** | Cantilever tip deflection vs `δ = F L³ / (3 E I)`, at N = 21, 41, 81 | raw error < `2·h/L`; clamp-corrected error < 0.5 % | The discrete clamp makes the compliant span `L - h/2` (K4), a first-order bias. The raw bound tracks that bias with a factor-of-two margin; the corrected bound then checks the *physics* rather than the discretisation. Load chosen so the analytic deflection is 1 % of the span, well inside small-deflection theory. | raw 7.38 / 3.73 / 1.88 %; corrected 0.075 / 0.026 / 0.014 % |
| **V1b** | Convergence order of the V1 error | observed order > 0.8 between successive refinements | The clamp bias is O(h), so first order is the expected and correct behaviour. Requiring > 0.8 detects a broken discretisation without demanding an order the scheme does not have. | 0.99, 0.99 |
| **V2** | Pure bending: uniform rest curvature (equivalent to a uniform moment `M = EI κ0`) | mean-curvature error < 0.1 %; curvature spread < 0.1 % | A free rod adopts its rest shape exactly; the only residual error is the discrete relation `\|kb\| = 2 tan(φ/2)` versus `κ l̄`, which is O((κh)²) ≈ 4e-8 here. 0.1 % is generous head-room. The spread check confirms the shape is a circular arc, not just the right average. | 0.0000 % |
| **V3** | Pure torsion vs `θ = T L / (G J)` | relative error < 1e-6 | The discrete twist chain reproduces the linear ODE exactly once the boundary offset is accounted for (edge 0's twist is clamped and the moment acts on the last edge, so the compliant span is `L - h`). Only round-off remains. | 0.0000 % |
| **V4** | Rigid-body invariance of the elastic energy under an arbitrary rotation + translation | relative change < 1e-12 | Pure floating-point round-off of an O(1) energy under a 3×3 rotation. Anything larger means a frame-dependent term leaked into the energy. | 1.0e-15 |
| **V5** | Time-step sensitivity: `dt = 0.05 s` versus `0.025 s` over 4 s | RMS centreline difference < 0.1 % of span | Backward Euler is first order in time, so the runs differ by O(dt) during the transient; after 4 s of over-damped relaxation (20 time constants) both are near the same equilibrium. The damping in the fixture is *derived* from a target relaxation time (τ = 0.2 s) so the test exercises a resolvable time scale rather than a frozen rod. | 0.0003 % of span (2.6e-4 mm) |
| **V6** | Mesh contact: maximum penetration when pressed onto a plane / sphere | *Milestone 2* | - | not yet implemented |
| **V7** | Energy / damping: after the external load is removed, elastic energy must decrease monotonically and decay | zero non-decreasing steps; `E_final < 1e-3 · E_initial` | The minimising-movement scheme is dissipative by construction, so *any* increase is a bug, not a tolerance question. The decay factor checks the damping actually acts over 40 steps (10 time constants). | 0 increases; decay factor 9.0e-6 |
| **V8** | Determinism: identical inputs, identical outputs | bitwise equality of nodes, twist angles and iteration count | The solver has no RNG and no parallel reduction, so anything short of bitwise equality would indicate hidden state. | bitwise identical |
| **V9** | Cross-implementation parity on the reference scenes | RMS centreline difference < 0.01 mm | Two independent implementations (Python/SciPy and TypeScript) with different line searches stop at slightly different points on the same very flat energy minimum. 0.01 mm is three orders of magnitude above the observed differences and far below any resolution this prototype could be validated against. **The C++ core of Milestone 3 drops into this same harness.** | 4.5e-15, 5.7e-9, 9.6e-8, 1.2e-4 mm |
| **V10** | NaN / Inf and degenerate input handling | must raise a specific, actionable error - never return silently | Every failure path (non-finite state, collapsed edge, rod folded 180°, invalid `dt`, gravity without a calibrated density, unknown schema version) is asserted to raise with a message that says what is wrong and how to fix it. | all pass |

### Actuation behaviour tests

| Test | Tolerance | Measured |
| --- | --- | --- |
| Unsteered catheter stays straight | max lateral offset < 1e-6 mm | 1.5e-9 mm |
| Steering bends only the distal `active_length_mm` | proximal lateral offset < 1e-6 mm | 1.5e-9 mm |
| Tip turn angle equals `gain × active_length` | relative error < 5 % | 0.01 % |
| A 90° handle roll rotates the steering plane by 90° at constant deflection | angle within 5°, magnitude within 5 % | 90.00°, 44.76 → 44.76 mm |
| Insertion changes the deployed arclength | relative error < 0.1 % | passes |
| Calibration gate blocks an uncalibrated profile | must raise | passes |

---

## 2. What these tests do **not** establish

* They do not show the model matches a real catheter. Not one parameter has
  been measured on a device.
* They do not validate contact, since contact is not implemented.
* Geometric similarity between a rendered catheter and a photograph is not
  evidence of mechanical accuracy.

---

## 3. Bench calibration programme (planned, not performed)

Each experiment identifies specific `CALIBRATION_REQUIRED` fields.

| ID | Experiment | Method | Identifies |
| --- | --- | --- | --- |
| **B1** | Force-deflection | Clamp the shaft at a known free length; hang calibrated masses at the tip; record deflection optically. Repeat with a step release to record the settling transient. | `bending_stiffness_n_mm2` (or `youngs_modulus_mpa`), `damping_n_s_per_mm` |
| **B2** | Tip deflection curve | Sweep the deflection knob through its full travel in both directions; record the tip deflection angle and radius at each command, on both the loading and unloading path. | `steer_gain_rad_per_mm`, and the hysteresis loop for a future Preisach/Bouc-Wen model |
| **B3** | Axial rotation transfer and torsional lag | Apply a known handle rotation; measure the distal rotation and its time lag, straight and at several bend radii. | `torsional_stiffness_n_mm2`, `torsional_damping_n_mm_s_per_rad`, and whether A2 (no bend-twist coupling) survives |
| **B4** | Shape comparison at several bend radii | Run the catheter through fixed-radius guides; compare the recorded centreline against the simulated one. | Global check of the bending model, not a single parameter |
| **B5** | Contact and gap in a transparent silicone PV phantom | Press the tip against the phantom wall at known indentations while recording force; image the contact patch and any gap. | `friction_coefficient`, `compliance_mm_per_n` |
| **B6** | Centreline ground truth | Biplanar imaging or a calibrated multi-camera rig; reconstruct the 3D centreline. | Ground truth for B4 and for all contact metrics |

### Parameter estimation

Calibration will be posed as a parameter-estimation problem over the recorded
data, with two supported back-ends:

* **Least squares** - minimise the centreline residual between simulation and
  measurement over the unknown parameters. Report the covariance so the
  uncertainty travels with the estimate.
* **Bayesian estimation** - a posterior over the parameters, so a parameter that
  the data does not constrain is *visibly* unconstrained rather than silently
  fitted.

Hard rule: a parameter that was not measured, and was not identified by one of
these procedures against real data, is never displayed as if it had been.
`provenance.last_calibrated_at` stays `null` and the profile keeps its
`CALIBRATION_REQUIRED` status.

---

## 4. Known numerical limitations

| Limitation | Impact | Planned fix |
| --- | --- | --- |
| First-order clamp bias (K4) | 1.9 % tip-deflection error at `h/L = 1/80` | Half-Voronoi weighting at the clamped end, or a ghost edge |
| Ill-conditioned system (K6) | The Python reference needs hundreds to thousands of L-BFGS iterations; a browser frame may end unconverged (A11) | Sparse Newton with the analytic Hessian, and the C++ core in Milestone 3 |
| Rest-curvature fixed point converges linearly for a handle roll (A4) | Up to ~14 passes for a 90° roll | Include the frame derivative, or an Anderson-accelerated fixed point |
| Bend-twist coupling omitted (A2) | No effect for the current boundary conditions; will matter for a doubly constrained spline | Add the holonomy term before Milestone 4 |
