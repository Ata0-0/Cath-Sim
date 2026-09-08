#!/usr/bin/env python3
"""Build a Blender model of the GenericSteerableRF catheter.

Research prototype - Not for clinical use.

What this is
------------
An ILLUSTRATIVE, class-level 3D model of a generic irrigated point-tip
steerable RF ablation catheter (7.5 F shaft, 3.5 mm tip electrode, three ring
electrodes, deflectable distal section, generic handle).  Every dimension comes
from ``configs/generic-steerable-rf.json`` - the same profile the physics core
uses - or is a clearly marked display placeholder.

What this is NOT
----------------
It is not a model of any specific commercial device and must not be presented
as one.  Handle shape, irrigation-port layout and ring spacing are generic
placeholders (``USER_MEASUREMENT_REQUIRED`` in the profile).  Geometric
similarity is not mechanical accuracy.

Usage
-----
Inside Blender (Scripting tab -> Open -> Run Script), or headless::

    blender -b -P scripts/blender/generic_steerable_rf_blender.py -- --out assets/demo/catheters
    # or with the bpy wheel:
    python scripts/blender/generic_steerable_rf_blender.py --out assets/demo/catheters

Options::

    --poses 0,90,180     deflection angles [deg] to build, one collection each
    --no-export          only build the scene (no .blend / .glb / .obj / .stl)
    --no-render          skip the preview renders
    --shaft-length MM    override the visible shaft length (display only)

The deflected pose is a constant-curvature arc over ``active_length_mm``.  For
an unloaded rod that is exactly the equilibrium the physics core reaches when
steering sets a uniform rest curvature (validation test V2), so the display
pose and the solver agree by construction.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]

DISCLAIMER = "Research prototype - Not for clinical use."
PROVENANCE = (
    "GenericSteerableRF - illustrative class-level geometry. Dimensions from "
    "configs/generic-steerable-rf.json; handle, ring spacing and irrigation "
    "port layout are display placeholders (USER_MEASUREMENT_REQUIRED). Not a "
    "model of any specific commercial device. Geometric similarity is not "
    "mechanical accuracy."
)

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

#: Embedded copy of the geometry section of configs/generic-steerable-rf.json,
#: used only when the script runs outside the repository (e.g. pasted into
#: Blender on another machine).  Keep in sync with the profile.
EMBEDDED_PROFILE = {
    "geometry": {
        "total_length_mm": 1100.0,
        "outer_diameter_mm": 2.5,
        "tip_length_mm": 3.5,
        "active_length_mm": 70.0,
    },
    "electrodes": {
        "count": 4,
        "arclength_from_tip_mm": [1.75, 8.0, 12.0, 16.0],
        "length_mm": [3.5, 1.0, 1.0, 1.0],
        "source": "USER_MEASUREMENT_REQUIRED",
    },
}

#: Display-only placeholders (not physics, not device data).
DISPLAY = {
    "ring_outer_diameter_mm": 2.6,  # rings sit slightly proud of the shaft
    "irrigation_port_count": 6,  # PLACEHOLDER - layout is device-specific
    "irrigation_port_diameter_mm": 0.35,
    "irrigation_port_depth_mm": 0.6,
    "irrigation_port_latitude_deg": 40.0,  # on the dome, from the equator
    "strain_relief_length_mm": 28.0,
    "strain_relief_end_diameter_mm": 4.8,
    "handle_length_mm": 120.0,
    "handle_diameter_mm": 22.0,
    "lever_length_mm": 30.0,
    "lever_width_mm": 9.0,
    "lever_height_mm": 4.0,
    "connector_length_mm": 22.0,
    "connector_diameter_mm": 12.0,
    "cable_length_mm": 40.0,
    "cable_diameter_mm": 4.5,
    "segments_around": 32,
    "sample_mm_bend": 0.5,
    "sample_mm_straight": 5.0,
}


def find_profile() -> dict:
    """Load the repository profile when reachable, else the embedded copy."""
    here = Path(__file__).resolve() if "__file__" in globals() else Path.cwd()
    for parent in [here, *here.parents]:
        candidate = parent / "configs" / "generic-steerable-rf.json"
        if candidate.is_file():
            with candidate.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if data.get("schema_version") != "0.1.0":
                raise RuntimeError(
                    f"{candidate} declares schema_version={data.get('schema_version')!r}; "
                    "this script understands 0.1.0. Migrate the profile instead of "
                    "editing the schema silently."
                )
            return data
    print("[warn] configs/generic-steerable-rf.json not found - using the embedded copy.")
    return EMBEDDED_PROFILE


# ---------------------------------------------------------------------------
# Centreline
# ---------------------------------------------------------------------------


class Centreline:
    """Straight proximal shaft + constant-curvature distal arc + rigid tip.

    Coordinates: shaft axis +X, handle at the origin pointing toward -X, tip at
    +X.  Deflection bends the distal ``active_length_mm`` toward +Z.  Units mm.
    """

    def __init__(
        self,
        shaft_length_mm: float,
        active_length_mm: float,
        tip_length_mm: float,
        deflection_deg: float,
    ) -> None:
        self.flexible_start = shaft_length_mm - active_length_mm  # from the handle
        self.flexible_end = shaft_length_mm
        self.tip_length = tip_length_mm
        self.total = shaft_length_mm + tip_length_mm
        self.active = active_length_mm
        self.theta = math.radians(deflection_deg)
        self.radius = self.active / self.theta if abs(self.theta) > 1e-9 else float("inf")

    def point(self, s: float) -> tuple[Vector, Vector]:
        """Position and unit tangent at arclength ``s`` measured from the handle."""
        if s <= self.flexible_start or self.radius == float("inf"):
            return Vector((s, 0.0, 0.0)), Vector((1.0, 0.0, 0.0))
        u = min(s, self.flexible_end) - self.flexible_start  # arclength into the bend
        phi = u / self.radius
        base = Vector((self.flexible_start, 0.0, 0.0))
        pos = base + Vector((self.radius * math.sin(phi), 0.0, self.radius * (1.0 - math.cos(phi))))
        tan = Vector((math.cos(phi), 0.0, math.sin(phi)))
        if s > self.flexible_end:  # rigid tip electrode continues along the tangent
            pos = pos + tan * (s - self.flexible_end)
        return pos, tan

    def frame(self, s: float) -> tuple[Vector, Vector, Vector, Vector]:
        """Position, tangent, normal (in the bend plane) and binormal at ``s``."""
        pos, tan = self.point(s)
        binormal = Vector((0.0, 1.0, 0.0))  # bend plane is XZ, so Y is constant
        normal = binormal.cross(tan).normalized()
        return pos, tan, normal, binormal


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------


def sweep(
    frames: list[tuple[Vector, Vector, Vector, Vector]],
    radii: list[float],
    n_around: int,
    cap_start: bool = True,
    cap_end: bool = True,
):
    """Sweep a circle of varying radius along frames. Zero radius collapses to an apex."""
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    rings: list[list[int] | int] = []
    for (pos, _tan, normal, binormal), radius in zip(frames, radii, strict=True):
        if radius <= 1e-6:
            verts.append(tuple(pos))
            rings.append(len(verts) - 1)
            continue
        start = len(verts)
        for k in range(n_around):
            angle = 2.0 * math.pi * k / n_around
            offset = normal * (radius * math.cos(angle)) + binormal * (radius * math.sin(angle))
            verts.append(tuple(pos + offset))
        rings.append(list(range(start, start + n_around)))

    for a, b in itertools.pairwise(rings):
        if isinstance(a, int) and isinstance(b, int):
            continue
        if isinstance(a, int):  # apex -> ring
            for k in range(n_around):
                faces.append((a, b[(k + 1) % n_around], b[k]))
        elif isinstance(b, int):  # ring -> apex
            for k in range(n_around):
                faces.append((a[k], a[(k + 1) % n_around], b))
        else:
            for k in range(n_around):
                k2 = (k + 1) % n_around
                faces.append((a[k], a[k2], b[k2], b[k]))

    if cap_start and isinstance(rings[0], list):
        faces.append(tuple(reversed(rings[0])))
    if cap_end and isinstance(rings[-1], list):
        faces.append(tuple(rings[-1]))
    return verts, faces


def make_object(name: str, verts, faces, material, collection, smooth: bool = True):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if smooth:
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    collection.objects.link(obj)
    return obj


def material(name: str, rgb: tuple[float, float, float], metallic: float, roughness: float):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*rgb, 1.0)
    mat.metallic = metallic
    mat.roughness = roughness
    return mat


def evaluated_copy(obj):
    """Return a new mesh with the object's modifiers applied (no operators needed)."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    return bpy.data.meshes.new_from_object(evaluated)


# ---------------------------------------------------------------------------
# Catheter parts
# ---------------------------------------------------------------------------


def build_pose(
    profile: dict, deflection_deg: float, shaft_length_mm: float, collection, materials: dict
):
    geometry = profile["geometry"]
    electrodes = profile["electrodes"]
    outer_r = geometry["outer_diameter_mm"] / 2.0
    tip_len = geometry["tip_length_mm"]
    active = geometry["active_length_mm"]
    n_around = DISPLAY["segments_around"]

    line = Centreline(shaft_length_mm, active, tip_len, deflection_deg)
    objects = []

    # --- shaft: from the strain relief to the base of the tip electrode ----
    samples: list[float] = []
    s = 0.0
    while s < line.flexible_end:
        samples.append(s)
        in_bend = s >= line.flexible_start - 2
        s += DISPLAY["sample_mm_bend"] if in_bend else DISPLAY["sample_mm_straight"]
    samples.append(line.flexible_end)
    frames = [line.frame(v) for v in samples]
    verts, faces = sweep(frames, [outer_r] * len(frames), n_around)
    objects.append(make_object("Shaft", verts, faces, materials["shaft"], collection))

    # --- tip electrode: cylinder + hemispherical dome, rigid --------------
    dome_r = outer_r
    straight = tip_len - dome_r
    tip_frames = []
    tip_radii = []
    for t in (0.0, straight):
        pos, tan, nrm, bin_ = line.frame(line.flexible_end)
        tip_frames.append((pos + tan * t, tan, nrm, bin_))
        tip_radii.append(outer_r)
    for k in range(1, 13):
        angle = (math.pi / 2.0) * k / 12.0
        pos, tan, nrm, bin_ = line.frame(line.flexible_end)
        tip_frames.append((pos + tan * (straight + dome_r * math.sin(angle)), tan, nrm, bin_))
        tip_radii.append(dome_r * math.cos(angle))
    verts, faces = sweep(tip_frames, tip_radii, n_around, cap_end=False)
    tip = make_object("TipElectrode", verts, faces, materials["electrode"], collection)
    objects.append(tip)

    # --- irrigation ports: small cylinders cut into the dome ---------------
    n_ports = DISPLAY["irrigation_port_count"]
    port_r = DISPLAY["irrigation_port_diameter_mm"] / 2.0
    depth = DISPLAY["irrigation_port_depth_mm"]
    lat = math.radians(DISPLAY["irrigation_port_latitude_deg"])
    pos, tan, nrm, bin_ = line.frame(line.flexible_end)
    centre = pos + tan * straight  # dome centre
    cutter_verts: list = []
    cutter_faces: list = []
    for k in range(n_ports):
        az = 2.0 * math.pi * k / n_ports
        radial = (nrm * math.cos(az) + bin_ * math.sin(az)) * math.cos(lat) + tan * math.sin(lat)
        radial.normalize()
        helper = tan if abs(radial.dot(tan)) < 0.9 else nrm
        u = radial.cross(helper).normalized()
        v = radial.cross(u).normalized()
        base = centre + radial * (dome_r - depth)
        outer = centre + radial * (dome_r + 0.3)
        frames_p = [(base, radial, u, v), (outer, radial, u, v)]
        pv, pf = sweep(frames_p, [port_r, port_r], 12)
        offset = len(cutter_verts)
        cutter_verts.extend(pv)
        cutter_faces.extend(tuple(i + offset for i in f) for f in pf)
    cutter = make_object(
        "IrrigationPorts", cutter_verts, cutter_faces, materials["port"], collection, smooth=False
    )
    boolean = tip.modifiers.new("IrrigationPorts", "BOOLEAN")
    boolean.operation = "DIFFERENCE"
    boolean.solver = "EXACT"
    boolean.object = cutter
    cut_mesh = evaluated_copy(tip)
    tip.modifiers.remove(boolean)
    old = tip.data
    tip.data = cut_mesh
    bpy.data.meshes.remove(old)
    for polygon in tip.data.polygons:
        polygon.use_smooth = True
    tip.data.materials.append(materials["electrode"])
    # The cutter has done its job; the ports are now real recesses in the dome.
    cutter_mesh = cutter.data
    bpy.data.objects.remove(cutter)
    bpy.data.meshes.remove(cutter_mesh)

    # --- ring electrodes ---------------------------------------------------
    ring_r = DISPLAY["ring_outer_diameter_mm"] / 2.0
    offsets = electrodes["arclength_from_tip_mm"]
    lengths = electrodes.get("length_mm", [tip_len] + [1.0] * (len(offsets) - 1))
    for index, (from_tip, length) in enumerate(zip(offsets, lengths, strict=True)):
        if index == 0:
            continue  # the tip electrode is built above
        s_centre = line.total - from_tip
        half = length / 2.0
        ring_frames = []
        ring_radii = []
        for t, r in (
            (-half, outer_r * 1.001),
            (-half + 0.1, ring_r),
            (half - 0.1, ring_r),
            (half, outer_r * 1.001),
        ):
            ring_frames.append(line.frame(s_centre + t))
            ring_radii.append(r)
        verts, faces = sweep(ring_frames, ring_radii, n_around)
        objects.append(
            make_object(f"RingElectrode_{index}", verts, faces, materials["electrode"], collection)
        )

    # --- handle (generic, illustrative) ----------------------------------
    def axis_frames(x: float):
        """Frame on the handle axis (+X) at abscissa ``x``."""
        return (
            Vector((x, 0.0, 0.0)),
            Vector((1.0, 0.0, 0.0)),
            Vector((0.0, 0.0, 1.0)),
            Vector((0.0, 1.0, 0.0)),
        )

    sr_len = DISPLAY["strain_relief_length_mm"]
    sr_end_r = DISPLAY["strain_relief_end_diameter_mm"] / 2.0
    frames_sr = []
    radii_sr = []
    for k in range(13):
        u = k / 12.0
        x = -sr_len * u
        r = outer_r + (sr_end_r - outer_r) * (u**1.6)
        frames_sr.append(axis_frames(x))
        radii_sr.append(r)
    verts, faces = sweep(frames_sr, radii_sr, n_around)
    objects.append(make_object("StrainRelief", verts, faces, materials["handle"], collection))

    h_len = DISPLAY["handle_length_mm"]
    h_r = DISPLAY["handle_diameter_mm"] / 2.0
    x0 = -sr_len
    x1 = -sr_len - h_len
    frames_h = []
    radii_h = []
    n_h = 48
    for k in range(n_h + 1):
        u = k / n_h
        x = x0 + (x1 - x0) * u
        d_start = x0 - x
        d_end = x - x1
        r = h_r
        if d_start < h_r:
            r = math.sqrt(max(h_r**2 - (h_r - d_start) ** 2, 0.0))
        elif d_end < h_r:
            r = math.sqrt(max(h_r**2 - (h_r - d_end) ** 2, 0.0))
        frames_h.append(axis_frames(x))
        radii_h.append(max(r, sr_end_r if d_start < 1.0 else r))
    verts, faces = sweep(frames_h, radii_h, n_around)
    objects.append(make_object("HandleBody", verts, faces, materials["handle"], collection))

    # deflection lever on top of the handle
    lever_len = DISPLAY["lever_length_mm"]
    lever_w = DISPLAY["lever_width_mm"]
    lever_h = DISPLAY["lever_height_mm"]
    lx = x0 - 18.0 - lever_len / 2.0
    lever = bpy.data.objects.new("DeflectionLever", bpy.data.meshes.new("DeflectionLever"))
    hx, hy = lever_len / 2, lever_w / 2
    z0, z1 = h_r - 1.0, h_r + lever_h
    lever.data.from_pydata(
        [
            (lx - hx, -hy, z0),
            (lx + hx, -hy, z0),
            (lx + hx, hy, z0),
            (lx - hx, hy, z0),
            (lx - hx, -hy, z1),
            (lx + hx, -hy, z1),
            (lx + hx, hy, z1),
            (lx - hx, hy, z1),
        ],
        [],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    lever.data.update()
    lever.data.materials.append(materials["lever"])
    collection.objects.link(lever)
    bevel = lever.modifiers.new("Bevel", "BEVEL")
    bevel.width = 1.5
    bevel.segments = 6
    beveled = evaluated_copy(lever)
    lever.modifiers.remove(bevel)
    old = lever.data
    lever.data = beveled
    bpy.data.meshes.remove(old)
    lever.data.materials.append(materials["lever"])
    for polygon in lever.data.polygons:
        polygon.use_smooth = True
    objects.append(lever)

    # connector + cable at the proximal end
    c_len = DISPLAY["connector_length_mm"]
    c_r = DISPLAY["connector_diameter_mm"] / 2.0
    verts, faces = sweep([axis_frames(x1 + 1.0), axis_frames(x1 - c_len)], [c_r, c_r], n_around)
    objects.append(make_object("Connector", verts, faces, materials["connector"], collection))
    cab_len = DISPLAY["cable_length_mm"]
    cab_r = DISPLAY["cable_diameter_mm"] / 2.0
    verts, faces = sweep(
        [axis_frames(x1 - c_len + 0.5), axis_frames(x1 - c_len - cab_len)], [cab_r, cab_r], n_around
    )
    objects.append(make_object("Cable", verts, faces, materials["cable"], collection))

    for obj in objects:
        obj["provenance"] = PROVENANCE
        obj["disclaimer"] = DISCLAIMER
        obj["deflection_deg"] = deflection_deg
    return objects, line


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001  # 1 Blender unit = 1 mm
    scene.unit_settings.length_unit = "MILLIMETERS"
    scene["disclaimer"] = DISCLAIMER
    scene["provenance"] = PROVENANCE
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs[0].default_value = (0.92, 0.93, 0.95, 1.0)
        background.inputs[1].default_value = 1.0
    return scene


def make_materials():
    return {
        "shaft": material("Shaft_Polymer", (0.93, 0.93, 0.90), 0.0, 0.35),
        "electrode": material("Electrode_PtIr", (0.78, 0.78, 0.80), 1.0, 0.25),
        "port": material("Irrigation_Port", (0.05, 0.05, 0.06), 0.0, 0.8),
        "handle": material("Handle_Polymer", (0.20, 0.22, 0.26), 0.0, 0.5),
        "lever": material("Lever_Polymer", (0.08, 0.08, 0.09), 0.0, 0.6),
        "connector": material("Connector", (0.35, 0.36, 0.38), 0.3, 0.5),
        "cable": material("Cable", (0.10, 0.10, 0.11), 0.0, 0.7),
    }


VIEWS = {
    # name: (target function, distance mm, focal length mm, direction)
    "distal": (
        lambda line: (line.point(line.flexible_start - 15.0)[0] + line.point(line.total)[0]) / 2.0,
        250.0,
        50.0,
        Vector((-0.25, -1.0, 0.35)),
    ),
    # Look back at the dome so the irrigation ports face the camera.
    "tip": (lambda line: line.point(line.total - 8.0)[0], 55.0, 85.0, Vector((0.85, -0.75, 0.45))),
    "handle": (
        lambda _line: Vector(
            (
                20.0 - DISPLAY["strain_relief_length_mm"] - DISPLAY["handle_length_mm"] / 2.0,
                0.0,
                0.0,
            )
        ),
        520.0,
        50.0,
        Vector((0.35, -1.0, 0.45)),
    ),
}


def add_camera_and_light(scene, line: Centreline):
    """Camera with a tracked target empty; `set_view` re-aims it per render."""
    target = bpy.data.objects.new("CameraTarget", None)
    scene.collection.objects.link(target)
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.clip_end = 100000.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam
    set_view(scene, line, "distal")

    sun_data = bpy.data.lights.new("KeyLight", "SUN")
    sun_data.energy = 3.0
    sun_data.angle = math.radians(8.0)
    sun = bpy.data.objects.new("KeyLight", sun_data)
    sun.rotation_euler = (math.radians(50.0), math.radians(10.0), math.radians(-35.0))
    scene.collection.objects.link(sun)
    fill_data = bpy.data.lights.new("FillLight", "SUN")
    fill_data.energy = 1.2
    fill = bpy.data.objects.new("FillLight", fill_data)
    fill.rotation_euler = (math.radians(-60.0), math.radians(-20.0), math.radians(140.0))
    scene.collection.objects.link(fill)


def set_view(scene, line: Centreline, view: str) -> None:
    target_fn, distance, lens, direction = VIEWS[view]
    target = bpy.data.objects["CameraTarget"]
    cam = scene.camera
    target.location = target_fn(line)
    cam.data.lens = lens
    cam.location = target.location + direction.normalized() * distance


def add_disclaimer_text(scene, line: Centreline):
    curve = bpy.data.curves.new("Disclaimer", "FONT")
    curve.body = (
        f"{DISCLAIMER}\n"
        "GenericSteerableRF - illustrative class-level geometry, not a specific device."
    )
    curve.size = 4.0
    curve.align_x = "CENTER"
    text = bpy.data.objects.new("Disclaimer", curve)
    text.location = (line.total / 2.0, 0.0, -30.0)
    text.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    text.hide_render = True
    scene.collection.objects.link(text)


def render_pose(scene, path: Path, engine: str = "CYCLES", samples: int = 48):
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.film_transparent = False
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    try:
        scene.render.engine = engine
        if engine == "CYCLES":
            scene.cycles.samples = samples
            scene.cycles.device = "CPU"
            scene.cycles.use_denoising = False
        bpy.ops.render.render(write_still=True)
        return True
    except Exception as error:  # report and fall back
        print(f"[warn] {engine} render failed ({error}); falling back to WORKBENCH")
        try:
            scene.render.engine = "BLENDER_WORKBENCH"
            bpy.ops.render.render(write_still=True)
            return True
        except Exception as error2:
            print(f"[warn] Workbench render failed too: {error2}")
            return False


def export_collection(collection, out_dir: Path, stem: str) -> list[str]:
    """Export one pose as GLB, OBJ and STL. Returns the files written."""
    written = []
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in collection.objects:
        obj.select_set(True)
    glb = out_dir / f"{stem}.glb"
    try:
        bpy.ops.export_scene.gltf(
            filepath=str(glb),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
        )
        written.append(glb.name)
    except Exception as error:
        print(f"[warn] GLB export failed: {error}")
    obj_path = out_dir / f"{stem}.obj"
    try:
        bpy.ops.wm.obj_export(
            filepath=str(obj_path),
            export_selected_objects=True,
            export_materials=True,
            apply_modifiers=True,
        )
        written.append(obj_path.name)
        mtl = obj_path.with_suffix(".mtl")
        if mtl.exists():
            written.append(mtl.name)
    except Exception as error:
        print(f"[warn] OBJ export failed: {error}")
    stl = out_dir / f"{stem}.stl"
    try:
        bpy.ops.wm.stl_export(filepath=str(stl), export_selected_objects=True, apply_modifiers=True)
        written.append(stl.name)
    except Exception as error:
        print(f"[warn] STL export failed: {error}")
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="assets/demo/catheters", help="output directory")
    parser.add_argument("--poses", default="0,90,180", help="deflection angles in degrees")
    parser.add_argument(
        "--shaft-length",
        type=float,
        default=None,
        help="visible shaft length [mm]; default = profile total_length_mm",
    )
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    return parser.parse_args(argv)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    args = parse_args(argv)
    profile = find_profile()
    geometry = profile["geometry"]
    shaft_length = args.shaft_length or (geometry["total_length_mm"] - geometry["tip_length_mm"])
    poses = [float(v) for v in args.poses.split(",") if v.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    scene = setup_scene()
    materials = make_materials()
    collections = []
    _lines = []
    reference_line = None
    for deflection in poses:
        name = f"GenericSteerableRF_deflection_{round(deflection):03d}deg"
        collection = bpy.data.collections.new(name)
        scene.collection.children.link(collection)
        collection["provenance"] = PROVENANCE
        collection["disclaimer"] = DISCLAIMER
        _objects, line = build_pose(profile, deflection, shaft_length, collection, materials)
        collections.append((collection, deflection))
        _lines.append(line)
        reference_line = reference_line or line

    assert reference_line is not None
    add_camera_and_light(scene, reference_line)
    add_disclaimer_text(scene, reference_line)

    # Only the first pose is visible by default; the others are switched on in the outliner.
    for index, (collection, _deflection) in enumerate(collections):
        collection.hide_viewport = index != 0
        collection.hide_render = index != 0

    written: list[str] = []
    if not args.no_render:
        for index, (collection, deflection) in enumerate(collections):
            for other, _ in collections:
                other.hide_render = other is not collection
            # hide_viewport also hides from the evaluated depsgraph for export/render
            for other, _ in collections:
                other.hide_viewport = other is not collection
            for view in ("distal", "tip") + (("handle",) if index == 0 else ()):
                set_view(scene, reference_line if view == "handle" else _lines[index], view)
                png = (
                    out_dir
                    / f"generic-steerable-rf-deflection-{round(deflection):03d}deg-{view}.png"
                )
                if render_pose(scene, png):
                    written.append(png.name)
        set_view(scene, reference_line, "distal")
    if not args.no_export:
        for collection, deflection in collections:
            for other, _ in collections:
                other.hide_viewport = other is not collection
                other.hide_render = other is not collection
            stem = f"generic-steerable-rf-deflection-{round(deflection):03d}deg"
            written.extend(export_collection(collection, out_dir, stem))
        for index, (collection, _deflection) in enumerate(collections):
            collection.hide_viewport = index != 0
            collection.hide_render = index != 0
        blend = out_dir / "generic-steerable-rf.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        written.append(blend.name)

    print("Wrote:", ", ".join(written) if written else "(nothing - scene built only)")
    print(PROVENANCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
