# Catheter display models

**Research prototype - Not for clinical use.**

Illustrative 3D models of the generic catheter families, for figures, the
viewer and Blender work. They are **display geometry**, built by scripts in
`scripts/blender/` from the same parameter profiles the physics core uses.

| Family | Script | Outputs |
| --- | --- | --- |
| `GenericSteerableRF` | `scripts/blender/generic_steerable_rf_blender.py` | `generic-steerable-rf.blend` (three deflection poses as collections, closed and cutaway shells), plus `.glb` / `.obj` / `.stl` and preview `.png` per pose |

## What the GenericSteerableRF model contains

A cutaway of a generic irrigated, contact-force-sensing, point-tip steerable
RF ablation catheter. Objects, from the tip:

| Region | Objects | Status |
| --- | --- | --- |
| Tip | `TipElectrode` (3.5 mm, hemispherical dome, rows of irrigation ports cut as recesses: 8 rows x 6) | length / OD from the product table; port rows and count **estimated from a product photo** |
| Distal assembly | `TransmitterCoilCore`, `TransmitterCoil` (copper winding) → `PrecisionSpring` with two `SpringCollar_*` → `LocationSensor_1..3` on `LocationSensorCore_*` (tilted, 120° apart) → `PullWireAnchor` | **arrangement** follows published cutaway illustrations of this catheter class; every dimension **placeholder** |
| Electrodes | `RingElectrode_1..5` at 4.5 / 6.0 / 7.5 / 10.5 / 12.0 mm from the apex - a cluster of three, a gap, then two (`arclength_from_tip_mm` custom property) | count from the product table; spacing **estimated from a product photo, +/-0.5 mm**, ring widths not resolvable (`USER_MEASUREMENT_REQUIRED`) |
| Shaft | `Shaft` (closed) and `Shaft_Cutaway` (hollow tube with a sector window over the distal 4-30 mm); `IrrigationLumen`, `ElectrodeLeadBundle`, `PullWire_Up` / `PullWire_Down` in the bend plane | OD from the profile; wall, lumen and wire sizes **placeholder** |
| Handle | `StrainRelief`, `HandleNose`, `Neck`, `DeflectionKnob` (knurled rotary collar), `TensionRing`, `HandleBody` (ergonomic capsule), `Connector`, `ConnectorKey`, `Cable`, `IrrigationLine`, `IrrigationLuer` | **entirely placeholder** - a generic bidirectional handle |
| Handle mechanism | `CamShaft` from the knob to `DeflectionCam`; `PullWire_Up_Handle` / `PullWire_Down_Handle` run from the shaft, wrap ~110° around the cam and end at `CamPin_Up` / `CamPin_Down`; `ElectrodeLeadBundle_Handle`, `IrrigationLumen_Handle` | generic pull-wire-on-cam mechanism typical of the class; **placeholder** |
| Cutaway twins | `*_Cutaway` versions of the shaft, rings, body, knob and tension ring with a window on the -Y side | display only |

Closed and cutaway shells both live in each pose collection; one set is
hidden (`--no-cutaway` swaps them). Every object carries `provenance`,
`disclaimer` and `deflection_deg` custom properties. Scene units: 1 unit =
1 mm.

## Provenance - read before using any of these in a document

* Outer dimensions come from `configs/generic-steerable-rf.json`: 8 F shaft
  (2.667 mm), 3.5 mm tip electrode, 115 cm length, 6 electrodes - taken from a
  public manufacturer product table supplied by the project owner (2026-09-09).
  The 70 mm deflectable section is not in that table and stays a class-level
  placeholder. Ring spacing and irrigation-port layout were **estimated from a
  product photo** (scaled to the 3.5 mm tip, about +/-0.5 mm) - an estimate,
  not a measurement.
* The internal *arrangement* (tip electrode → transmitter coil → precision
  spring → three location sensors, irrigation lumen, two pull wires) is the
  published architecture of contact-force point-tip catheters as a class. **No
  internal dimension was measured**; all of them, and the entire handle and
  its mechanism, are display placeholders.
* **This is not a model of any specific commercial device** and must not be
  captioned, filed or presented as one. Geometric similarity is not mechanical
  accuracy - see `docs/assumptions.md`.
* The deflected poses are constant-curvature arcs over the active length. For
  an unloaded rod that is exactly the equilibrium the physics core reaches
  under uniform steering rest curvature (validation V2), so display pose and
  solver agree by construction. The precision spring's own micro-deflection
  (contact-force sensing) is **not** simulated by the physics core.

## Regenerating

```bash
# with the bpy wheel (pip install bpy) or a Blender binary:
.venv/bin/python scripts/blender/generic_steerable_rf_blender.py --out assets/demo/catheters
blender -b -P scripts/blender/generic_steerable_rf_blender.py -- --out assets/demo/catheters
```

Options: `--poses 0,45,90,135,180`, `--no-cutaway`, `--shaft-length 300`
(display only), `--no-render`, `--no-export`. Renders per pose: `distal`,
`tip`, `internals`; for the first pose also `handle` and `mechanism`.

## Opening in Blender

Open `generic-steerable-rf.blend`. Each pose is a collection
(`GenericSteerableRF_deflection_000deg`, `_090deg`, `_180deg`); only the
first is visible by default - toggle the others in the Outliner. To see the
closed device instead of the cutaway, hide the `*_Cutaway` objects and unhide
`Shaft`, `RingElectrode_*`, `HandleBody`, `DeflectionKnob`, `TensionRing`.

Large binaries are not committed (see `.gitignore`); regenerate them with the
script above.
