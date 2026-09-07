# CLAUDE.md - working agreements for this repository

**Research prototype - Not for clinical use.**

`CathSim_LA_Claude_Code_Master_Prompt.md` is the project contract. This file is
the short operational summary; when the two disagree, the contract wins, and
any deliberate deviation must be recorded in
`docs/assumptions.md` §4 with its reason.

## Non-negotiables

1. **Never invent a physical parameter.** An unknown geometric, material or
   mechanical value stays `null` in the profile and is marked
   `CALIBRATION_REQUIRED`. It must block simulation, not fall back to a
   plausible default. A `null` that stops the program is strictly better than a
   number nobody can trace.
2. **Never present a demo value as a device property.** Demo profiles live in
   their own file, carry `is_demo_profile: true`, require explicit consent, and
   are labelled in the UI and in every export.
3. **Geometric similarity is not mechanical accuracy.** Say so wherever a
   reader might otherwise assume the opposite.
4. **No commercial device names** are modelled or implied. Models are
   `GenericSteerableRF`, `GenericBalloon`, `GenericLoop`,
   `GenericLatticeSphere`, `GenericPentasplinePFA`.
5. **`Research prototype - Not for clinical use.`** appears on every screen,
   in every export and at the top of every document. There are tests for this.
6. **No lesion, electric-field, PFA-threshold or thermal prediction.** Separate
   future module.

## Physics rules

* **Motion comes out of the solver.** Never move a centreline point to make an
  animation look right. Actuation enters as a boundary condition or as a rest
  curvature, and the solver decides the shape.
* **One unit system**: mm, s, N, MPa (= N/mm²), rad. Every physical identifier
  carries its unit as a suffix. No unit-less magic numbers in physics code.
* **The gradient is analytic and tested against finite differences.** If you
  change the energy, update the gradient and confirm `test_gradient.py` and its
  TypeScript twin still pass.
* **Two implementations stay in sync.** `packages/physics-core` (Python
  reference) and `apps/viewer/src/physics` (TypeScript real time) implement the
  same model. Any change to one requires the same change to the other, plus
  regenerated golden data (`python scripts/generate_reference_data.py`) and a
  passing parity test.

## Testing rules

* **Never skip, comment out, delete or quietly widen a test.** If a tolerance
  has to change, change it *and* write the reason into
  `docs/validation-plan.md`.
* **Every tolerance needs a rationale.** "It passes now" is not one.
* **Deterministic tests use a fixed seed.** There is exactly one, in
  `packages/physics-core/tests/conftest.py`.
* **Looking right is not passing.** Screenshots support a claim; they never
  establish one.

## Code rules

* Keep the layers apart: UI → transport → geometry → physics, dependencies
  pointing downward only. The physics core imports nothing from React, Three.js
  or the DOM.
* No global mutable state.
* Error messages say what is wrong **and** how to fix it.
* Every config carries a `schema_version`. An unknown version is rejected, not
  coerced. Changing a field means a version bump and a migration.
* Do not delete or rewrite files a user created. Do not commit large binaries.

## Commands

```bash
npm run dev                       # viewer at http://localhost:5173
npm test                          # TypeScript solver, parity and UI tests
npm run typecheck && npm run lint
.venv/bin/python -m pytest        # Python reference, geometry and API tests
.venv/bin/ruff check packages services scripts
.venv/bin/ruff format packages services scripts
python scripts/generate_reference_data.py   # regenerate golden data (deliberate act)
python scripts/generate_types.py            # regenerate TypeScript types from the schema
```

## Where things are

| Looking for | Go to |
| --- | --- |
| The rod energy and its gradient | `packages/physics-core/src/cathsim_physics/rod.py` |
| The time integrator | `packages/physics-core/src/cathsim_physics/solver.py` |
| Steering / insertion / roll | `packages/physics-core/src/cathsim_physics/catheter.py` |
| The real-time port | `apps/viewer/src/physics/` |
| Why the model looks like this | `docs/adr/0001-physics-architecture.md` |
| What is assumed vs measured | `docs/assumptions.md` |
| Tolerances and their reasons | `docs/validation-plan.md` |
