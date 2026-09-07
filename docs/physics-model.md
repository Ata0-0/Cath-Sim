# Physics model

**Research prototype - Not for clinical use.**

## 1. Continuous model

The catheter shaft is treated as a Kirchhoff/Cosserat rod. Its stored elastic
energy is the line integral required by the project contract:

```text
E = ∫ [ ½ (κ - κ0)ᵀ B (κ - κ0)
      + ½ (τ - τ0)ᵀ C (τ - τ0)
      + ½ (ε - ε0)ᵀ S (ε - ε0) ] ds
```

with, in the project unit system (mm, s, N, MPa):

| Symbol | Meaning | Unit |
| --- | --- | --- |
| `s` | arclength along the centreline | mm |
| `κ` | material curvature | 1/mm |
| `τ` | twist rate | rad/mm |
| `ε` | axial strain | - |
| `B = EI` | bending stiffness | N·mm² |
| `C = GJ` | torsional stiffness | N·mm² |
| `S = EA` | axial stiffness | N |

`κ0`, `τ0`, `ε0` are the **rest** (undeformed) values. Steering writes into
`κ0`; it does not apply a force to the tip and it never moves a node directly.

## 2. Discretisation

### 2.1 Degrees of freedom

* `N` nodes `x₀ … x_{N-1}` ∈ ℝ³ [mm]; `M = N-1` edges `e_j = x_{j+1} - x_j`.
* One scalar material twist angle `φ_j` [rad] per edge.

`φ` is measured against a **Bishop frame**: the director `d1` of edge 0 is
parallel-transported along the rod, which produces a rotation-minimising -
i.e. *twist-free* - reference frame. Two consequences follow, and both are
load-bearing for the rest of the design:

1. The material twist between two edges is simply `φ_i - φ_{i-1}`; there is no
   separate reference-twist bookkeeping.
2. `E_twist` has **no explicit position dependence**, so `∂E_twist/∂x = 0`
   *exactly*. See assumption A2 in `docs/assumptions.md` for why this is a
   sound modelling choice for a proximally clamped, distally free catheter, and
   for when it stops being one.

### 2.2 Geometry

Discrete curvature binormal at interior node `i`:

```text
kb_i = 2 e_{i-1} × e_i / (|e_{i-1}| |e_i| + e_{i-1}·e_i)
```

`kb` is dimensionless and satisfies `|kb_i| = 2 tan(φ_i/2)`, where `φ_i` is the
turning angle at node `i`. For small turning angles `|kb_i| ≈ κ_i · l̄_i`, with
the Voronoi length `l̄_i = (l_{i-1} + l_i)/2` [mm]. This is the relation used to
convert a physical rest curvature [1/mm] into a rest `kb0` [-].

### 2.3 Discrete energies

Each term below is the trapezoidal/Voronoi discretisation of the corresponding
integrand above. All energies are in N·mm.

```text
E_stretch = Σ_j  ½ EA (|e_j|/l_j - 1)² l_j
E_bend    = Σ_i  EI / (2 l̄_i) |kb_i - kb0_i|²
E_twist   = Σ_i  GJ / (2 l̄_i) (φ_i - φ_{i-1} - Δφ0_i)²
```

* `E_stretch` ← `½ ε² EA` integrated over the edge rest length.
* `E_bend` ← `½ EI (κ-κ0)²` with `κ ≈ kb/l̄`, giving `½ EI (kb-kb0)²/l̄² · l̄`.
  Bending is isotropic (`B1 = B2 = EI`), correct for the round section assumed
  here; see assumption A1.
* `E_twist` ← `½ GJ (τ-τ0)²` with `τ ≈ Δφ/l̄`.

### 2.4 Analytic gradient

The gradient is exact, not a finite-difference stand-in. For the bending term,
with `D = |e0||e1| + e0·e1`:

```text
∂kb/∂e0 = ( -2 [e1]×  - kb ⊗ (|e1| t0 + e1) ) / D
∂kb/∂e1 = (  2 [e0]×  - kb ⊗ (|e0| t1 + e0) ) / D
```

and, using the identity `wᵀ [v]× = w × v`, the assembled node gradients are

```text
w        = (EI / l̄_i) (kb_i - kb0_i)                     [N·mm]
a0       = ( -2 (w × e1) - (w·kb) (|e1| t0 + e1) ) / D    [N]
a1       = (  2 (w × e0) - (w·kb) (|e0| t1 + e0) ) / D    [N]
∇_{x_{i-1}} E = -a0 ,  ∇_{x_i} E = a0 - a1 ,  ∇_{x_{i+1}} E = a1
```

A dedicated test (`test_gradient.py`, and its TypeScript twin) checks this
against central finite differences; the observed relative error is ~1e-9.

## 3. Actuation

### 3.1 Steering

The handle knob sets a **rest curvature** over the distal `active_length_mm`:

```text
κ0 [1/mm]      = steer_gain_rad_per_mm · |(steer_x, steer_y)|
ψ              = atan2(steer_y, steer_x)
bend direction = cos ψ · m1 + sin ψ · m2          (material frame, unit)
kb0_i          = κ0 · l̄_i · ( t_i × bend direction )
```

`steer_gain_rad_per_mm` is a **calibration parameter**, not a tendon force. The
first model deliberately does not claim a tendon force in newtons.

Because the bend direction is expressed in the *material* frame, rolling the
handle rolls the steering plane. This is checked directly: a 90° handle roll
rotates the deflection plane by 90.00° while the tip deflection magnitude is
unchanged (44.76 mm → 44.76 mm).

`kb0` is a world-frame vector held fixed during a solve and rebuilt afterwards,
which makes equilibrium a fixed point (assumption A4).

Hysteresis is **off** in this MVP. The data model already carries the actuation
input as a record, so a Preisach- or Bouc-Wen-type operator can be inserted
between the knob command and `κ0` without changing any other layer.

### 3.2 Insertion and axial rotation

* **Insertion** is an arclength re-parameterisation: the deployed length beyond
  the sheath tip changes, existing shape is preserved, and new material appears
  straight along the tip tangent. Retraction pulls the tip back along the path
  the catheter already occupies. Node count stays constant (assumption A5).
* **Axial rotation** is the prescribed twist angle of edge 0 - a boundary
  condition on `φ`, not a rigid rotation of the geometry. The roll therefore
  propagates distally through `GJ`, and the transient shows torsional lag.
* **Sheath** exit position and axis are boundary data; nodes 0 and 1 are
  clamped, which fixes both position and tangent.

## 4. Time integration

The rod is integrated with the **minimising-movement** (implicit gradient-flow
/ backward Euler on over-damped dynamics) scheme:

```text
q^{n+1} = argmin_q [ E(q) + 1/(2 dt) Σ_k c_k (q_k - q_k^n)² ]
```

Its stationarity condition is `c (q^{n+1} - q^n)/dt = -∇E(q^{n+1})`, i.e.
backward Euler on `c q̇ = -∇E`. Properties:

* unconditionally stable - no CFL limit from the stiff bending term;
* dissipative by construction (verified: elastic energy decays monotonically
  over 40 steps after the load is removed, with zero non-decreasing steps);
* reduces to the static equilibrium problem as `dt → ∞`, which is exactly what
  `solve_static` solves.

The minimisation is L-BFGS on the free degrees of freedom with the exact
analytic gradient. The limited-memory history size matters a great deal here
(assumption K6): 20 corrections need 14 624 iterations on the demo steering
case, 150 corrections need 607.

## 5. Contact

Not implemented in this milestone. Milestone 2 adds BVH/AABB acceleration,
capsule-triangle closest point, unilateral non-penetration, friction, contact
normals and per-node force estimates. `SolverReport.max_penetration_mm` and the
`contacts` array in `SimulationFrame` already exist and are reported as zero /
empty, so the schema does not change when contact lands.

When contact forces do appear they are **numerical estimates from an
uncalibrated model**, and the UI says so. They are not clinical contact-force
readings.

## 6. Explicitly out of scope

No lesion prediction, no electric-field solve, no PFA threshold, no thermal
damage estimate. Those are a separate future module, and nothing in this code
base should be read as approximating them.
