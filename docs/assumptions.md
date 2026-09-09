# Assumptions, defaults and calibration gaps

**Research prototype - Not for clinical use.**

This file is the single place where the project records *what it knows*, *what
it assumed* and *what still has to be measured*. Nothing in the code base may
silently contradict it. Every entry states why the choice was made, so a
reviewer can challenge the reasoning rather than guess at it.

Three categories are used throughout:

| Marker | Meaning |
| --- | --- |
| **KNOWN** | Derivable from first principles, from the discretisation, or measurable inside the software itself. |
| **ASSUMED** | A deliberate modelling choice with a stated rationale. Changing it changes results; it is not a measurement. |
| **CALIBRATION_REQUIRED** | A physical quantity that must come from a bench measurement. The software refuses to run a real simulation while it is `null`. |

---

## 1. KNOWN

| # | Item | Statement |
| --- | --- | --- |
| K1 | Unit system | mm, s, N, MPa (= N/mm²), rad. `EI` and `GJ` in N·mm², `EA` in N. Enforced by naming suffixes; see `packages/physics-core/src/cathsim_physics/units.py`. |
| K2 | Discrete energy | The discrete bending, twisting and stretching energies in `rod.py` reduce to the continuous Cosserat energy of `docs/physics-model.md` as the node spacing goes to zero. |
| K3 | Analytic gradient | The analytic gradient of the discrete energy agrees with central finite differences to a relative error < 1e-6 (test `test_gradient.py`, and the TypeScript twin in `rod.parity.test.ts`). |
| K4 | Discrete clamp bias | Fixing nodes 0 and 1 makes the first half Voronoi cell rigid, so the compliant span is `L - h/2`. The cantilever deflection therefore converges to Euler-Bernoulli at first order in `h`; the measured convergence order is 0.99 and the clamp-corrected error is 0.014-0.075 %. |
| K5 | Section properties | For the solid circular section assumed here: `A = πd²/4`, `I = πd⁴/64`, `J = 2I`, `G = E / (2(1+ν))`. |
| K6 | Solver conditioning | A rod couples a soft global bending mode (`3EI/L³`) to a stiff local stretch mode (`EA/h`); the condition number is ~1e5. This is why the L-BFGS history size matters so much (14 624 iterations at m=20 versus 607 at m=150 on the same problem) and why the browser solver carries its curvature history across frames. |
| K7 | Python ↔ TypeScript parity | The two independent implementations agree on the reference scenes to between 4.5e-15 and 1.2e-4 mm RMS on the centreline. |

---

## 2. ASSUMED

| # | Assumption | Rationale | Consequence if wrong |
| --- | --- | --- | --- |
| A1 | **Isotropic bending** (`B1 = B2 = EI`). | The modelled cross-section is round, so the two bending stiffnesses are equal by symmetry. The rest curvature is carried as a world-frame vector, which is what makes directed steering possible without an anisotropic stiffness tensor. | A catheter with a flattened or keyed shaft would prefer one bending plane; the model would not reproduce that preference. |
| A2 | **Bend-twist coupling is omitted.** The twist DOF is measured against a twist-free Bishop frame, so `E_twist` has no explicit position dependence and `∂E_twist/∂x = 0` *exactly* in this parameterisation. | The writhe/holonomy coupling enters only through a **twist-prescribed** boundary. This catheter is clamped proximally and free distally, so the equilibrium twist is uniform and the omitted term does not change the equilibrium shape. | Would matter for a distally constrained shaft (a looped catheter, or one trapped in contact). Revisit before Milestone 4 (pentaspline), where splines *are* constrained at both ends. |
| A3 | **Kirchhoff rod (no independent shear DOF).** The tangent is the third material director. | Shear deformation is negligible for a slender rod (length/diameter ≳ 40 here). The project contract allows "a shear constraint or sufficiently stiff shear". | Short, stubby segments (a deployed basket strut) may need a Cosserat shear DOF. |
| A4 | **Lagged (explicit) rest curvature.** `kb0` is expressed in world coordinates from the material frame at the start of a solve and held fixed during it. | Keeps the energy gradient exact and cheap. It is a fixed point: `solve(kb0(shape)) → shape → kb0(shape)`. Measured to converge in 1-2 passes for a steering change and up to ~14 for a 90° handle roll. | A non-converged fixed point would report a shape that is not an equilibrium. `solve_static` / `solveStatic` therefore iterate it explicitly and expose the pass count. |
| A5 | **Insertion is an arclength re-parameterisation at constant node count.** | Advancing the handle feeds material out of the sheath: existing shape is preserved and new material appears straight along the tip tangent. A constant node count keeps the DOF layout - and therefore determinism - stable across frames. | Node spacing varies with insertion (0.3-2.0 mm over the offered range), so the discretisation error varies too. The insertion slider is bounded for this reason. |
| A6 | **Over-damped implicit (minimising-movement) time integration.** | Catheter manipulation at clinical speeds is heavily damped and near quasi-static. Backward Euler on `c q̇ = -∇E` is unconditionally stable, dissipative by construction, and reduces to the static problem as `dt → ∞`. | True inertial dynamics (a whipping tip release) are not modelled. Out of scope for the stated use. |
| A7 | **`damping_n_s_per_mm` is applied per unit length**, so its effective unit is N·s/mm². | The key name is fixed by the project contract; the per-unit-length interpretation makes the coefficient mesh-independent. | Documented in the profile `units` block and in the schema. Do not read it as a lumped N·s/mm. |
| A8 | **Torsional damping fallback** = `damping_n_s_per_mm · J / A` when not given explicitly. | Dimensionally consistent scaling by the polar radius of gyration squared. | A guess. Prefer an explicit `torsional_damping_n_mm_s_per_rad`. |
| A9 | **Gravity is off by default.** | It needs a calibrated linear density, which is CALIBRATION_REQUIRED. Enabling it without one raises rather than silently assuming a density. | None; the toggle is disabled in the UI until a density exists. |
| A10 | **Synthetic demo anatomy** (sphere + tubular stub, ~26 mm radius). | The default scene must never ship patient data. It is at approximately left-atrium scale so the camera and controls feel right. | It is a **shape placeholder**, not anatomy. No anatomical or clinical conclusion may be drawn from it. It is labelled as such in the UI. |
| A11 | **Real-time frames may stop before the implicit step converges.** The browser solver runs to a wall-clock budget and carries its L-BFGS curvature history across frames. | An unbudgeted implicit step can need several hundred iterations. Carrying the history makes the per-frame budget a continuation solve that keeps descending the *same physical energy*, so the shape still reaches the validated equilibrium - measured within ~40 frames (1.3 s of simulated time) of a full-scale steering command. | The shortfall is never hidden: `converged` goes false and the residual is displayed in the HUD. `solveStatic` always solves to tolerance. |
| A12 | **Demo-profile damping is derived, not invented.** `c = τ · (3EI/L³) / L` with a target settling time `τ = 0.5 s` at a nominal deployed length `L = 110 mm`. | Makes the demo behave plausibly *and* be reproducible. The derivation is written into the profile's own `notes`. | These are demo numbers that set how fast the demo settles. They are **not** measured catheter damping and must never be quoted as such. |
| A13 | **Physics and rendering share the browser main thread**, decoupled only in *rate* (a fixed-rate timer for the solver, requestAnimationFrame for rendering). | Measured solve cost is ~6 ms per frame at 71 nodes, well inside a 30 Hz budget, so a Web Worker is not yet needed. | Moving the solver into a Web Worker is Milestone 3 work; until then a very large rod could stutter the UI. |
| A14 | **Outer catheter dimensions come from a public manufacturer product table** supplied by the project owner (8 F, 3.5 mm tip, 6 electrodes, 115 cm); **ring spacing and irrigation-port layout are estimates from a product photo** scaled to the 3.5 mm tip (about +/-0.5 mm; ring widths not resolvable). | The table is public specification data, not an invented number; the photo estimate is labelled as such in the profile (`ESTIMATED_FROM_PRODUCT_PHOTO`) and keeps `USER_MEASUREMENT_REQUIRED` status. | Positions may be off by up to a ring width until measured with calipers or a scaled photo. The deflectable length is not in the table and remains a class-level placeholder. **The project proposal PDF states 7.5 Fr / 4 electrodes for this device class, which contradicts the table; the proposal should be corrected.** |

---

## 3. CALIBRATION_REQUIRED

None of these may be guessed. `configs/generic-steerable-rf.json` leaves every one of them `null`, and the software refuses to start a simulation until they are supplied or the clearly labelled demo profile is explicitly accepted.

| Field | Unit | How it must be obtained |
| --- | --- | --- |
| `material.youngs_modulus_mpa` | MPa | Force-deflection on a clamped shaft (docs/validation-plan.md, bench B1). |
| `material.poisson_ratio` | - | Material datasheet, or from the measured `E` and `G`. |
| `material.bending_stiffness_n_mm2` | N·mm² | Directly from B1; overrides the `E × I` route. |
| `material.torsional_stiffness_n_mm2` | N·mm² | Torque-twist measurement (bench B3). |
| `material.axial_stiffness_n` | N | Axial tension test. |
| `material.damping_n_s_per_mm` | N·s/mm² | Step-release settling time (bench B1). |
| `material.density_kg_per_mm3` | kg/mm³ | Weigh a measured length. Required before gravity may be enabled. |
| `actuation.steer_gain_rad_per_mm` | rad/mm per unit input | Knob-command to tip-deflection curve (bench B2). |
| `contact.friction_coefficient` | - | Sled or phantom test (bench B5). |
| `contact.compliance_mm_per_n` | mm/N | Indentation on a silicone phantom (bench B5). |
| `geometry.*` | mm | Direct measurement of the device under study. |
| All `GenericPentasplinePFA` fields | - | Milestone 4. The deployment mechanism itself is unknown; until it is measured the model must be labelled *kinematic-mechanical hybrid, calibration required*. |

---

## 4. Deviations from the project contract

| Contract item | Actual | Reason |
| --- | --- | --- |
| Python 3.12 | Python 3.11.15 | The version available in this environment. Nothing in the code uses 3.12-only syntax; `pyproject.toml` declares `>=3.11`. |
| C++20 core, pybind11, Catch2 | Not present | Milestone 3. The Python reference and the TypeScript real-time solver already share one interface and one parity harness, so the C++ core can slot in behind it. |
| XPBD constraint solver | Not used | The contract's *first* preference - a geometrically exact discrete elastic rod - is implemented instead, with an implicit over-damped integrator that is unconditionally stable. XPBD was listed as the fallback for real-time stability; it is not needed since the DER already runs at ~6 ms/frame. Recorded in `docs/adr/0001-physics-architecture.md`. |
| Python ↔ C++ parity test (V9) | Python ↔ TypeScript parity | Same harness, same golden data, different second implementation. The C++ leg drops into the existing `tests/reference-data/` fixture unchanged. |
| WebSocket live control | REST + WebSocket scaffolded in `services/simulation-api`, viewer runs the solver locally | Keeps the viewer usable with a single command and with no backend. The transport boundary exists; wiring the viewer to it is Milestone 3. |
| Docker Compose | Not present | Local development works without Docker, which the contract requires; the container images are deferred until the API is load-bearing. |
| STL/OBJ import, contact, heat-map | Not present | Milestone 2, explicitly. The UI states this where a user would look for it. |
