# Catheter display models

**Research prototype - Not for clinical use.**

Illustrative 3D models of the generic catheter families, for figures, the
viewer and Blender work. They are **display geometry**, built by scripts in
`scripts/blender/` from the same parameter profiles the physics core uses.

| Family | Script | Outputs |
| --- | --- | --- |
| `GenericSteerableRF` | `scripts/blender/generic_steerable_rf_blender.py` | `generic-steerable-rf.blend` (three deflection poses as collections), plus `.glb` / `.obj` / `.stl` and preview `.png` per pose |

## Provenance - read before using any of these in a document

* Every dimension comes from `configs/generic-steerable-rf.json`: 7.5 F shaft
  (2.5 mm), 3.5 mm tip electrode, 70 mm deflectable section, 4 electrodes.
  Those are **class-level** numbers for irrigated point-tip steerable RF
  ablation catheters as a device category.
* Ring-electrode spacing, irrigation-port count and layout, and the entire
  handle are **display placeholders** (`USER_MEASUREMENT_REQUIRED` in the
  profile). They make the model read as a catheter; they are not measurements.
* **This is not a model of any specific commercial device** and must not be
  captioned, filed or presented as one. Geometric similarity is not mechanical
  accuracy - see `docs/assumptions.md`.
* The deflected poses are constant-curvature arcs over the active length. For
  an unloaded rod that is exactly the equilibrium the physics core reaches
  under uniform steering rest curvature (validation V2), so the display pose
  and the solver agree by construction.

## Regenerating

```bash
# with the bpy wheel (pip install bpy) or a Blender binary:
.venv/bin/python scripts/blender/generic_steerable_rf_blender.py --out assets/demo/catheters
blender -b -P scripts/blender/generic_steerable_rf_blender.py -- --out assets/demo/catheters
```

Options: `--poses 0,45,90,135,180`, `--shaft-length 300` (display only),
`--no-render`, `--no-export`.

## Opening in Blender

Open `generic-steerable-rf.blend`. The scene is in millimetres (1 unit = 1 mm).
Each pose is a collection (`GenericSteerableRF_deflection_000deg`, `_090deg`,
`_180deg`); only the first is visible by default - toggle the others in the
Outliner. Every object carries `provenance` and `disclaimer` custom properties.

Large binaries are not committed (see `.gitignore`); regenerate them with the
script above.
