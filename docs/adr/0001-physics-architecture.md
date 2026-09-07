# ADR 0001 - Physics architecture for the steerable catheter

* **Status:** Accepted
* **Date:** 2026-09-07
* **Milestone:** 1 (first validated steerable rod)

**Research prototype - Not for clinical use.**

## Context

The project contract requires a catheter that behaves like a continuous,
mechanically consistent elastic body rather than a polyline that is bent by
hand for the animation. It states a preference order for the solver:

1. Discrete Elastic Rods, or a geometrically exact Cosserat rod;
2. an XPBD constraint solver for real-time stability;
3. mass-spring only as a temporary debugging comparison, never as the final
   model.

It also requires a Python reference implementation validated against analytic
solutions first, and a performance-critical solver moved to C++ later behind
the *same* interface, with the two compared within tolerance.

Two further constraints shape the decision:

* Actuation must enter as a **rest curvature** consumed by the solver, never as
  a direct displacement of the tip.
* Unknown physical parameters must stay `CALIBRATION_REQUIRED` and must block
  simulation rather than being silently defaulted.

## Decision

### 1. A Bishop-frame discrete elastic rod, solved implicitly

We implement option 1 - a discrete elastic rod - and do **not** use XPBD.

* Degrees of freedom: node positions plus one scalar material twist angle per
  edge, measured against a Bishop (rotation-minimising, twist-free) frame.
* Energy: discrete stretch, isotropic bending against a world-frame rest
  curvature `kb0`, and twist. Derived term by term from the contract's
  continuous energy in `docs/physics-model.md`.
* Gradient: exact and analytic, verified against central finite differences.
* Time integration: the minimising-movement scheme (backward Euler on
  over-damped dynamics), which is unconditionally stable and reduces to static
  equilibrium as `dt → ∞`.
* Minimiser: L-BFGS with a backtracking Armijo line search.

### 2. Two implementations behind one interface, with a parity harness

* `packages/physics-core` (Python + NumPy/SciPy) is the **reference**. It is
  the implementation validated against the analytic solutions, and the one that
  generates the golden data in `tests/reference-data/`.
* `apps/viewer/src/physics` (TypeScript) is the **real-time** implementation:
  the same energy, the same analytic gradient, the same integrator.
* `tests/reference-data/rod-reference-cases.json` is the shared fixture. The
  TypeScript tests replay it and compare centrelines node by node.

### 3. Rest curvature is world-frame and lagged

`kb0` is stored as a world-space vector, built from the material frame at the
start of a solve and rebuilt afterwards. Equilibrium is the fixed point of
`solve(kb0(shape)) → shape → kb0(shape)`, and the solver iterates it explicitly
and reports the pass count.

## Rationale

**Why a DER rather than XPBD.** XPBD is the contract's *fallback* "for
real-time stability". It is not needed: the implicit DER runs at ~6 ms per
frame with 71 nodes, comfortably inside a 30 Hz budget, and it is
unconditionally stable without one. A DER also buys two things XPBD would have
cost us:

* an *exact* energy and gradient, so the analytic beam, bending and torsion
  tests measure the model rather than the number of constraint iterations;
* an equilibrium that is independent of the iteration count. Under XPBD the
  effective stiffness depends on how many iterations you can afford, which
  would make the cantilever test a test of the solver budget, not of `EI`.

**Why a Bishop frame rather than time-parallel frames with reference twist.**
It makes the twist energy a function of `φ` alone, so `∂E_twist/∂x = 0` exactly
and the whole gradient stays closed-form and verifiable. The price is the
bend-twist (writhe) coupling, which enters only through a *twist-prescribed*
boundary. The catheter is clamped proximally and free distally, so the omitted
term does not change the equilibrium. This is recorded as assumption A2 with an
explicit trigger for revisiting it (Milestone 4, where pentaspline struts are
constrained at both ends).

**Why world-frame rest curvature.** Directed steering needs a bend *direction*.
Carrying `κ0` as a world vector keeps bending isotropic (right for a round
section) while still letting the handle roll rotate the steering plane through
the material frame. Measured: a 90° roll rotates the deflection plane by 90.00°
at unchanged deflection magnitude.

**Why TypeScript for the real-time leg.** The viewer must start with one
command and no backend. A browser-local solver also keeps the physics
independent of network latency. The interface is identical to the Python one,
so the C++ core of Milestone 3 replaces the *Python* implementation and reuses
the same parity fixture without any schema change.

**Why an implicit integrator.** Catheter manipulation at clinical speeds is
heavily damped and near quasi-static. An explicit integrator would need a time
step set by the stiff bending term; the implicit scheme has no such limit and
is dissipative by construction, which is directly testable (V7).

## Consequences

### Positive

* Analytic validation is meaningful: cantilever error converges at first order
  with a clamp-corrected error of 0.014-0.075 %; pure bending and pure torsion
  match to round-off; rigid-body invariance holds to 1e-15.
* Two independent implementations agree to between 4.5e-15 and 1.2e-4 mm RMS,
  which is a genuine check on both.
* Steering, insertion and axial rotation are all boundary/rest-state inputs, so
  no code path moves a centreline point for the animation.
* The C++ core can be added without touching the schema, the UI, or the tests.

### Negative / accepted costs

* The system is ill-conditioned (~1e5), so the Python reference needs hundreds
  to thousands of L-BFGS iterations for a cold static solve (1.6 s for the demo
  steering case). Acceptable for a reference implementation; the fix is a
  sparse Newton solver and the C++ core.
* An interactive frame may end before the implicit step converges. This is
  handled by a wall-clock budget plus a persistent L-BFGS history, so the frame
  budget acts as a continuation solve that still reaches the validated
  equilibrium (measured: within ~40 frames). The shortfall is displayed, never
  hidden.
* The rest-curvature fixed point converges linearly for a handle roll (up to
  ~14 passes for 90°).
* Bend-twist coupling is absent (A2) and must be revisited before Milestone 4.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| **XPBD Cosserat rod** (contract option 2) | Effective stiffness depends on the iteration count, which would compromise the analytic validation tests. Not needed for stability, since the implicit DER already runs in real time. Still the right choice if contact constraints later dominate the cost - revisit at Milestone 2. |
| **Mass-spring** | Explicitly forbidden by the contract as a final model, and it cannot represent torsion at all. |
| **Full Bergou-style DER with time-parallel frames and reference twist** | Captures bend-twist coupling, but the gradient formulas rely on a quasi-static-frame approximation that is harder to verify and buys nothing for the present boundary conditions. |
| **Finite-difference gradients** | Would have avoided deriving `∂kb/∂e`, at a cost of ~600 energy evaluations per gradient. Too slow, and it hides sign errors instead of exposing them. |
| **Serving every frame from the Python API over WebSocket** | Makes the viewer depend on a running backend and on network latency, and contradicts "local development must work without Docker". The transport boundary is scaffolded for when live control is needed. |
