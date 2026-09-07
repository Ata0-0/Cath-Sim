# Catheter parameter guide

**Research prototype - Not for clinical use.**

Every number the physics core uses comes from a JSON profile in `configs/`.
Nothing is hard-coded, and no unit-less magic number appears in physics code.

## Profile status values

| `status` | Meaning |
| --- | --- |
| `RESEARCH_ONLY_CALIBRATION_REQUIRED` | Structure is complete, physical values are still `null`. Simulation is **blocked**. |
| `DEMO_ONLY_NOT_A_DEVICE_SPECIFICATION` | Arbitrary placeholder values so the software can be exercised. Requires explicit consent, and results are **not** mechanically valid. |
| `CALIBRATED` | Values identified from bench measurement, with `provenance.last_calibrated_at` set. No profile has this status yet. |

## Shipped profiles

| File | Status | Use |
| --- | --- | --- |
| `generic-steerable-rf.json` | `RESEARCH_ONLY_CALIBRATION_REQUIRED` | The real template. Fill it in from your own measurements. |
| `demo-steerable-rf.json` | `DEMO_ONLY_NOT_A_DEVICE_SPECIFICATION` | Software demonstration only. |
| `generic-pentaspline-pfa.json` | `RESEARCH_ONLY_CALIBRATION_REQUIRED` | Schema placeholder for Milestone 4. |

## Field reference

### `geometry`

| Field | Unit | Meaning |
| --- | --- | --- |
| `total_length_mm` | mm | Full device length, tip to handle. |
| `working_length_mm` | mm | Length that is discretised as a rod. Sets the node count together with `node_spacing_mm`. |
| `outer_diameter_mm` | mm | Shaft outer diameter. Drives `A`, `I`, `J` for the round section assumed here. |
| `tip_length_mm` | mm | Distal tip electrode length. |
| `active_length_mm` | mm | Distal length over which steering creates rest curvature. |
| `node_spacing_mm` | mm | Target discretisation. Smaller means more accurate and slower; the cantilever error is roughly `1.5 · h/L`. |

### `material`

| Field | Unit | Notes |
| --- | --- | --- |
| `youngs_modulus_mpa` | MPa (N/mm²) | With `poisson_ratio` and the section, gives `EI`, `GJ`, `EA`. |
| `poisson_ratio` | - | `G = E / (2(1+ν))`. |
| `bending_stiffness_n_mm2` | N·mm² | `EI`. **Overrides** the `E × I` route - use it when you measured `EI` directly. |
| `torsional_stiffness_n_mm2` | N·mm² | `GJ`. Overrides `G × J`. |
| `axial_stiffness_n` | N | `EA`. Overrides `E × A`. |
| `damping_n_s_per_mm` | N·s/mm² | Applied **per unit length**. The key name is fixed by the project contract; see assumption A7. |
| `torsional_damping_n_mm_s_per_rad` | N·mm·s/rad per mm | Optional. Falls back to `damping × J/A` (assumption A8). |
| `density_kg_per_mm3` | kg/mm³ | Only needed if gravity is enabled. Without it, enabling gravity raises an error. |

### `actuation`

| Field | Unit | Notes |
| --- | --- | --- |
| `steer_gain_rad_per_mm` | rad/mm per unit input | Rest curvature per unit of normalised knob command. **This is a calibration parameter, not a tendon force.** |
| `max_steering_input` | - | Clamp for `steer_x`, `steer_y`. |
| `bidirectional` | - | Whether the knob deflects both ways. |
| `hysteresis_model` | - | `DISABLED_IN_MVP`. Reserved for a Preisach/Bouc-Wen operator. |

### `contact` (used from Milestone 2)

| Field | Unit | Notes |
| --- | --- | --- |
| `friction_coefficient` | - | Catheter against tissue. |
| `compliance_mm_per_n` | mm/N | Contact compliance. |
| `catheter_collision_radius_mm` | mm | Collision capsule radius; also the rendered shaft radius. |

### `provenance`

| Field | Meaning |
| --- | --- |
| `geometry_source` | `USER_MEASUREMENT_REQUIRED`, `PLACEHOLDER_NOT_MEASURED`, or a citation. |
| `material_source` | `CALIBRATION_REQUIRED`, `PLACEHOLDER_NOT_MEASURED`, or a citation. |
| `last_calibrated_at` | ISO-8601 timestamp, or `null` if never calibrated. |

## The calibration gate

These fields block simulation while `null`:

* `material.youngs_modulus_mpa`
* `material.poisson_ratio`
* `material.damping_n_s_per_mm`
* `actuation.steer_gain_rad_per_mm`

Both implementations refuse to build a material from such a profile and raise a
message naming the missing fields. The viewer shows the same list in the
calibration panel and marks the profile `BLOCKED`.

A profile flagged `is_demo_profile` additionally requires explicit consent
(`accept_demo_parameters=True` in the API, the "run with demo parameters"
switch in the viewer).

## Adding a calibrated profile

1. Copy `configs/generic-steerable-rf.json`.
2. Measure geometry directly; record the method in `provenance.geometry_source`.
3. Run the bench programme in `docs/validation-plan.md` §3 to identify the
   material and actuation values.
4. Fill in the values, set `provenance.last_calibrated_at`, and change `status`
   to `CALIBRATED`.
5. Add a regression case to `tests/reference-data/` so future changes cannot
   silently move the calibrated behaviour.

Never fill a field with a plausible-looking guess. A `null` that blocks the
simulation is strictly better than a number nobody can trace.

## Schema versioning

Every profile carries `schema_version`. A profile whose version this build does
not understand is **rejected**, not coerced. Adding or renaming a field means
bumping the version and writing a migration - never editing the meaning of an
existing field in place.
