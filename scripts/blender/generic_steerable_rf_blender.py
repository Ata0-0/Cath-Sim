#!/usr/bin/env python3
"""Build a Blender model of the GenericSteerableRF catheter, with internals.

Research prototype - Not for clinical use.

What this is
------------
An ILLUSTRATIVE, class-level 3D model of a generic irrigated, contact-force
sensing, point-tip steerable RF ablation catheter, as a cutaway:

* distal assembly - 3.5 mm tip electrode with rows of irrigation ports, magnetic
  transmitter coil, precision spring (the flexure that lets the tip electrode
  deflect slightly for contact-force sensing), three location-sensor coils,
  pull-wire anchor ring, five ring electrodes, irrigation lumen and
  electrode-lead bundle;
* deflectable shaft with two pull wires (bidirectional steering);
* handle - strain relief, rotary deflection knob driving a cam that tensions
  the pull wires, tension ring, ergonomic body, electrical connector and
  cable, irrigation line with luer.

The *arrangement* of the distal components (tip -> transmitter coil ->
precision spring -> location sensors) follows published cutaway illustrations
of this catheter class.  Every internal and handle dimension is a DISPLAY
PLACEHOLDER; outer geometry comes from ``configs/generic-steerable-rf.json``
(8 F, 3.5 mm tip, six electrodes, 115 cm from a public product table; ring spacing
and port layout ESTIMATED_FROM_PRODUCT_PHOTO, +/-0.5 mm).

What this is NOT
----------------
It is not a model of any specific commercial device and must not be presented
as one.  No internal dimension here was measured.  Geometric similarity is not
mechanical accuracy.

Usage
-----
Inside Blender (Scripting tab -> Open -> Run Script), or headless::

    blender -b -P scripts/blender/generic_steerable_rf_blender.py -- --out assets/demo/catheters
    python  scripts/blender/generic_steerable_rf_blender.py --out assets/demo/catheters  # bpy

Options::

    --poses 0,90,180     deflection angles [deg]; one collection each
    --no-cutaway         show the closed shells instead of the cutaway ones
    --no-export          only build the scene
    --no-render          skip the preview renders
    --shaft-length MM    visible shaft length (display only)

Each pose collection holds both the closed shells (``Shaft``, ``HandleBody``,
...) and their ``*_Cutaway`` twins; one set is hidden.  The deflected pose is
a constant-curvature arc over ``active_length_mm`` - exactly the equilibrium
the physics core reaches under uniform steering rest curvature (V2).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from collections.abc import Callable
from pathlib import Path

import bpy  # type: ignore[import-not-found]
from mathutils import Vector  # type: ignore[import-not-found]

DISCLAIMER = "Research prototype - Not for clinical use."
PROVENANCE = (
    "GenericSteerableRF - illustrative class-level cutaway. Outer dimensions from "
    "configs/generic-steerable-rf.json; component ARRANGEMENT follows published "
    "cutaway illustrations of contact-force point-tip catheters as a class; every "
    "internal and handle dimension is a display placeholder (USER_MEASUREMENT_REQUIRED). "
    "Not a model of any specific commercial device. Geometric similarity is not "
    "mechanical accuracy."
)

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

#: Embedded copy of the profile geometry, used only outside the repository.
EMBEDDED_PROFILE = {
    "geometry": {
        "total_length_mm": 1150.0,
        "outer_diameter_mm": 2.667,
        "tip_length_mm": 3.5,
        "active_length_mm": 70.0,
    },
    "electrodes": {
        "count": 6,
        "arclength_from_tip_mm": [1.75, 4.5, 6.0, 7.5, 10.5, 12.0],
        "length_mm": [3.5, 1.0, 1.0, 1.0, 1.0, 1.0],
        "source": "USER_MEASUREMENT_REQUIRED",
    },
}

#: Display placeholders. Arclengths ``s_*`` are measured from the tip apex.
D = {
    # outer
    "ring_outer_diameter_mm": 2.6,
    "irrigation_port_rows_around": 8,
    "irrigation_ports_per_row": 6,
    "irrigation_port_diameter_mm": 0.2,
    "irrigation_port_depth_mm": 0.45,
    "segments_around": 32,
    "sample_mm_bend": 0.5,
    "sample_mm_straight": 5.0,
    # distal internals (class arrangement: tip -> coil -> spring -> sensors)
    "shaft_inner_radius_mm": 0.95,
    "lumen_radius_mm": 0.32,
    "coil_s_mm": (3.8, 6.2),
    "coil_core_radius_mm": 0.42,
    "coil_wind_radius_mm": 0.62,
    "coil_turns": 10,
    "coil_wire_radius_mm": 0.09,
    "spring_s_mm": (6.4, 9.8),
    "spring_radius_mm": 0.78,
    "spring_turns": 5.5,
    "spring_wire_radius_mm": 0.15,
    "spring_collar_len_mm": 0.35,
    "sensor_s_mm": (10.2, 13.8),
    "sensor_count": 3,
    "sensor_offset_mm": 0.52,
    "sensor_tilt_deg": 12.0,
    "sensor_core_radius_mm": 0.16,
    "sensor_wind_radius_mm": 0.27,
    "sensor_turns": 12,
    "sensor_wire_radius_mm": 0.045,
    "anchor_s_mm": (14.6, 15.6),
    "anchor_inner_radius_mm": 0.62,
    "pull_wire_radius_mm": 0.12,
    "pull_wire_offset_mm": 0.72,
    "handle_wire_radius_mm": 0.2,  # display only: thicker so the cam wrap reads
    "lead_bundle_radius_mm": 0.18,
    "lead_bundle_offset_mm": 0.5,
    "hollow_s_mm": (3.5, 45.0),
    "cut_s_mm": (3.9, 30.0),
    "cut_centre_deg": -115.0,  # sector facing the cutaway camera
    "cut_half_deg": 82.0,
    # handle (x <= 0, along -X)
    "strain_relief_len_mm": 32.0,
    "strain_relief_end_radius_mm": 2.6,
    "nose_len_mm": 12.0,
    "knob_x_mm": (-62.0, -48.0),  # (proximal, distal)
    "knob_radius_mm": 12.5,
    "knob_ridges": 24,
    "knob_bore_radius_mm": 7.6,
    "tension_x_mm": (-66.5, -62.5),  # (proximal, distal)
    "tension_radius_mm": 10.6,
    "body_x_mm": (-67.0, -152.0),  # (distal end, proximal end) - the body code reads it that way
    "body_radius_mm": 11.0,
    "shell_thickness_mm": 1.6,
    "cam_x_mm": -55.0,
    "cam_radius_mm": 6.0,
    "cam_thickness_mm": 2.6,
    "cam_shaft_radius_mm": 1.3,
    "handle_cut_x_mm": (-128.0, -38.0),
    "handle_cut_y_mm": -2.5,
    "connector_x_mm": (-174.0, -152.0),
    "connector_radius_mm": 6.0,
    "cable_len_mm": 42.0,
    "cable_radius_mm": 2.3,
    "irrigation_line_radius_mm": 1.5,
    "irrigation_line_offset_z_mm": 5.0,
    "irrigation_line_len_mm": 48.0,
    "luer_radius_mm": 3.2,
    "luer_len_mm": 9.0,
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

Frame = tuple[Vector, Vector, Vector, Vector]  # position, tangent, normal, binormal


class Centreline:
    """Straight proximal shaft + constant-curvature distal arc + rigid tip.

    Shaft axis +X, handle at the origin pointing to -X, tip at +X.  Deflection
    bends the distal ``active_length_mm`` toward +Z.  Units mm.
    """

    def __init__(
        self,
        shaft_length_mm: float,
        active_length_mm: float,
        tip_length_mm: float,
        deflection_deg: float,
    ) -> None:
        self.flexible_start = shaft_length_mm - active_length_mm
        self.flexible_end = shaft_length_mm
        self.tip_length = tip_length_mm
        self.total = shaft_length_mm + tip_length_mm
        self.active = active_length_mm
        self.theta = math.radians(deflection_deg)
        self.radius = self.active / self.theta if abs(self.theta) > 1e-9 else float("inf")

    def point(self, s: float) -> tuple[Vector, Vector]:
        """Position and unit tangent at arclength ``s`` from the handle."""
        if s <= self.flexible_start or self.radius == float("inf"):
            return Vector((s, 0.0, 0.0)), Vector((1.0, 0.0, 0.0))
        u = min(s, self.flexible_end) - self.flexible_start
        phi = u / self.radius
        base = Vector((self.flexible_start, 0.0, 0.0))
        pos = base + Vector((self.radius * math.sin(phi), 0.0, self.radius * (1.0 - math.cos(phi))))
        tan = Vector((math.cos(phi), 0.0, math.sin(phi)))
        if s > self.flexible_end:
            pos = pos + tan * (s - self.flexible_end)
        return pos, tan

    def frame(self, s: float) -> Frame:
        """Frame at ``s``; the bend plane is XZ so the binormal is +Y."""
        pos, tan = self.point(s)
        binormal = Vector((0.0, 1.0, 0.0))
        normal = binormal.cross(tan).normalized()
        return pos, tan, normal, binormal

    def from_tip(self, s_from_tip: float) -> float:
        """Convert an arclength measured from the tip apex to one from the handle."""
        return self.total - s_from_tip


def axis_frame(x: float) -> Frame:
    """Frame on the straight handle axis (+X) at abscissa ``x``."""
    return (
        Vector((x, 0.0, 0.0)),
        Vector((1.0, 0.0, 0.0)),
        Vector((0.0, 0.0, 1.0)),
        Vector((0.0, 1.0, 0.0)),
    )


def offset_frame(frame: Frame, angle_rad: float, radius: float) -> Frame:
    """Shift a frame radially: offset = normal cos(a) + binormal sin(a)."""
    pos, tan, nrm, bin_ = frame
    return (
        pos + nrm * (radius * math.cos(angle_rad)) + bin_ * (radius * math.sin(angle_rad)),
        tan,
        nrm,
        bin_,
    )


def polyline_frames(points: list[Vector]) -> list[Frame]:
    """Parallel-transported frames along an arbitrary polyline."""
    n = len(points)
    tangents = []
    for i in range(n):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, n - 1)]
        tangents.append((b - a).normalized())
    helper = Vector((0.0, 0.0, 1.0)) if abs(tangents[0].z) < 0.9 else Vector((1.0, 0.0, 0.0))
    normal = tangents[0].cross(helper).normalized()
    frames: list[Frame] = []
    for i in range(n):
        if i > 0:
            axis = tangents[i - 1].cross(tangents[i])
            if axis.length > 1e-9:
                normal = normal - (normal.dot(tangents[i])) * tangents[i]
                normal.normalize()
        binormal = tangents[i].cross(normal).normalized()
        frames.append((points[i], tangents[i], normal, binormal))
    return frames


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------

Mesh = tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]


def _needs_flip(frames: list[Frame]) -> bool:
    """True when a sweep along ``frames`` would come out inside-out.

    A swept solid faces outward only when the frame handedness and the travel
    direction agree: ``(n x b) . t`` is +1 for a right-handed frame, and the
    travel sign is ``sign((last - first) . t)``.  Their product is -1 for an
    inside-out result.  Centreline frames are right-handed and travel +t;
    ``axis_frame`` is left-handed and the handle profiles mostly travel -X, so
    both are fine as written - but a left-handed frame travelling +t, or a
    right-handed one travelling -t, must be flipped.  Renders hide an inverted
    solid; EXACT booleans do not (they return empty or unchanged meshes), which
    is how this was found.
    """
    if len(frames) < 2:
        return False
    _pos, tan, nrm, bin_ = frames[0]
    handed = nrm.cross(bin_).dot(tan)
    travel = (frames[-1][0] - frames[0][0]).dot(tan)
    return handed * travel < 0.0


def _flip(faces: list[tuple[int, ...]]) -> list[tuple[int, ...]]:
    return [tuple(reversed(face)) for face in faces]


def sweep(
    frames: list[Frame],
    radii: list[float],
    n_around: int,
    cap_start: bool = True,
    cap_end: bool = True,
    modulation: Callable[[int, int], float] | None = None,
) -> Mesh:
    """Sweep a circle of varying radius along frames; zero radius -> apex."""
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
            r = radius * (modulation(k, n_around) if modulation else 1.0)
            verts.append(
                tuple(pos + normal * (r * math.cos(angle)) + binormal * (r * math.sin(angle)))
            )
        rings.append(list(range(start, start + n_around)))
    for a, b in itertools.pairwise(rings):
        if isinstance(a, int) and isinstance(b, int):
            continue
        if isinstance(a, int):
            faces.extend((a, b[(k + 1) % n_around], b[k]) for k in range(n_around))
        elif isinstance(b, int):
            faces.extend((a[k], a[(k + 1) % n_around], b) for k in range(n_around))
        else:
            for k in range(n_around):
                k2 = (k + 1) % n_around
                faces.append((a[k], a[k2], b[k2], b[k]))
    if cap_start and isinstance(rings[0], list):
        faces.append(tuple(reversed(rings[0])))
    if cap_end and isinstance(rings[-1], list):
        faces.append(tuple(rings[-1]))
    if _needs_flip(frames):
        faces = _flip(faces)
    return verts, faces


def sweep_polygon(frames: list[Frame], polygon_uv: list[tuple[float, float]]) -> Mesh:
    """Sweep a convex 2-D polygon (in normal/binormal coordinates) along frames."""
    # Normalise the winding to counter-clockwise in the (normal, binormal) plane
    # so the result matches sweep()'s ring convention and _needs_flip() applies
    # identically; a clockwise polygon would otherwise sweep an inside-out solid
    # that EXACT booleans silently ignore.
    signed_area = sum(
        u0 * v1 - u1 * v0 for (u0, v0), (u1, v1) in itertools.pairwise([*polygon_uv, polygon_uv[0]])
    )
    if signed_area < 0.0:
        polygon_uv = list(reversed(polygon_uv))
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    m = len(polygon_uv)
    for pos, _tan, normal, binormal in frames:
        for u, v in polygon_uv:
            verts.append(tuple(pos + normal * u + binormal * v))
    for i in range(len(frames) - 1):
        a = i * m
        b = (i + 1) * m
        for k in range(m):
            k2 = (k + 1) % m
            faces.append((a + k, a + k2, b + k2, b + k))
    faces.append(tuple(reversed(range(m))))
    last = (len(frames) - 1) * m
    faces.append(tuple(range(last, last + m)))
    if _needs_flip(frames):
        faces = _flip(faces)
    return verts, faces


def sector_uv(
    radius: float, centre_deg: float, half_deg: float, n_arc: int = 24
) -> list[tuple[float, float]]:
    """Convex circular sector polygon with the apex at the axis."""
    pts: list[tuple[float, float]] = [(0.0, 0.0)]
    for k in range(n_arc + 1):
        a = math.radians(centre_deg - half_deg + 2.0 * half_deg * k / n_arc)
        pts.append((radius * math.cos(a), radius * math.sin(a)))
    return pts


def helix_points(
    base: Frame, radius: float, length: float, turns: float, per_turn: int = 20, phase: float = 0.0
) -> list[Vector]:
    """Helix around the frame's tangent, starting at the frame origin."""
    pos, tan, nrm, bin_ = base
    n = max(2, int(turns * per_turn))
    pts = []
    for i in range(n + 1):
        t = i / n
        a = phase + 2.0 * math.pi * turns * t
        pts.append(
            pos + tan * (length * t) + nrm * (radius * math.cos(a)) + bin_ * (radius * math.sin(a))
        )
    return pts


def sweep_polyline(points: list[Vector], radius: float, n_around: int = 10) -> Mesh:
    frames = polyline_frames(points)
    return sweep(frames, [radius] * len(frames), n_around)


def merge(meshes: list[Mesh]) -> Mesh:
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for v, f in meshes:
        offset = len(verts)
        verts.extend(v)
        faces.extend(tuple(i + offset for i in face) for face in f)
    return verts, faces


def make_object(name: str, mesh: Mesh, material, collection, smooth: bool = True):
    verts, faces = mesh
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    if smooth:
        for polygon in data.polygons:
            polygon.use_smooth = True
    obj = bpy.data.objects.new(name, data)
    obj.data.materials.append(material)
    collection.objects.link(obj)
    return obj


def material(name: str, rgb, metallic: float, roughness: float, alpha: float = 1.0):
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
        if alpha < 1.0:
            bsdf.inputs["Alpha"].default_value = alpha
    mat.diffuse_color = (*rgb, alpha)
    mat.metallic = metallic
    mat.roughness = roughness
    if alpha < 1.0:
        mat.blend_method = "BLEND"
    return mat


def apply_booleans(obj, cutters: list, operation: str = "DIFFERENCE") -> None:
    """Apply boolean cutters to ``obj`` in place and delete the cutters."""
    for index, cutter in enumerate(cutters):
        mod = obj.modifiers.new(f"Boolean_{index}", "BOOLEAN")
        mod.operation = operation
        mod.solver = "EXACT"
        mod.object = cutter
    depsgraph = bpy.context.evaluated_depsgraph_get()
    new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    for mod in list(obj.modifiers):
        obj.modifiers.remove(mod)
    old_mesh = obj.data
    mats = list(old_mesh.materials)
    obj.data = new_mesh
    bpy.data.meshes.remove(old_mesh)
    for mat in mats:
        if mat.name not in obj.data.materials:
            obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    for cutter in cutters:
        cutter_mesh = cutter.data
        bpy.data.objects.remove(cutter)
        bpy.data.meshes.remove(cutter_mesh)


def duplicate(obj, name: str, collection):
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = name
    collection.objects.link(copy)
    return copy


def tag(objects, deflection_deg: float) -> None:
    for obj in objects:
        obj["provenance"] = PROVENANCE
        obj["disclaimer"] = DISCLAIMER
        obj["deflection_deg"] = deflection_deg


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------


def samples_along(line: Centreline, s0: float, s1: float) -> list[float]:
    out: list[float] = []
    s = s0
    while s < s1:
        out.append(s)
        s += D["sample_mm_bend"] if s >= line.flexible_start - 2.0 else D["sample_mm_straight"]
    out.append(s1)
    return out


def build_distal_outer(line: Centreline, profile: dict, mats, col) -> tuple[list, dict]:
    """Shaft, tip electrode with ports, ring electrodes. Returns (objects, named)."""
    n_around = D["segments_around"]
    outer_r = profile["geometry"]["outer_diameter_mm"] / 2.0
    tip_len = profile["geometry"]["tip_length_mm"]
    named: dict = {}
    objects = []

    frames = [line.frame(s) for s in samples_along(line, 0.0, line.flexible_end)]
    shaft = make_object(
        "Shaft", sweep(frames, [outer_r] * len(frames), n_around), mats["shaft"], col
    )
    named["shaft"] = shaft
    objects.append(shaft)

    # tip electrode: cylinder + dome
    dome_r = outer_r
    straight = tip_len - dome_r
    base = line.frame(line.flexible_end)
    tip_frames = [base, (base[0] + base[1] * straight, *base[1:])]
    tip_radii = [outer_r, outer_r]
    for k in range(1, 13):
        a = (math.pi / 2.0) * k / 12.0
        tip_frames.append((base[0] + base[1] * (straight + dome_r * math.sin(a)), *base[1:]))
        tip_radii.append(dome_r * math.cos(a))
    tip = make_object(
        "TipElectrode",
        sweep(tip_frames, tip_radii, n_around, cap_end=False),
        mats["electrode"],
        col,
    )
    # irrigation ports: axial rows of small ports over the tip cylinder and dome
    # (layout ESTIMATED_FROM_PRODUCT_PHOTO via the profile's "irrigation" block)
    irrigation = profile.get("irrigation", {})
    rows_around = int(irrigation.get("port_rows_around", D["irrigation_port_rows_around"]))
    per_row = int(irrigation.get("ports_per_row", D["irrigation_ports_per_row"]))
    port_r = float(irrigation.get("port_diameter_mm", D["irrigation_port_diameter_mm"])) / 2.0
    depth = D["irrigation_port_depth_mm"]
    centre = base[0] + base[1] * straight  # dome centre
    port_meshes = []
    for k in range(rows_around):
        az = 2.0 * math.pi * k / rows_around + (math.pi / rows_around) * (k % 2)
        radial_side = (base[2] * math.cos(az) + base[3] * math.sin(az)).normalized()
        n_dome = 2 if per_row >= 4 else 1
        n_cyl = max(per_row - n_dome, 1)
        stations = []
        for j in range(n_cyl):  # on the cylinder: (position along the axis, radial direction)
            t = 0.45 + (straight - 0.75) * j / max(n_cyl - 1, 1)
            stations.append((base[0] + base[1] * t + radial_side * (dome_r - depth), radial_side))
        for j in range(n_dome):  # on the dome
            lat = math.radians(22.0 + 30.0 * j)
            radial = (radial_side * math.cos(lat) + base[1] * math.sin(lat)).normalized()
            stations.append((centre + radial * (dome_r - depth), radial))
        for inner, radial in stations:
            u = radial.cross(base[1] if abs(radial.dot(base[1])) < 0.9 else base[2]).normalized()
            v = radial.cross(u).normalized()
            outer = inner + radial * (depth + 0.3)
            port_meshes.append(
                sweep([(inner, radial, u, v), (outer, radial, u, v)], [port_r, port_r], 10)
            )
    cutter = make_object("PortCutter", merge(port_meshes), mats["electrode"], col, smooth=False)
    apply_booleans(tip, [cutter])
    named["tip"] = tip
    objects.append(tip)

    # ring electrodes
    ring_r = D["ring_outer_diameter_mm"] / 2.0
    offsets = profile["electrodes"]["arclength_from_tip_mm"]
    lengths = profile["electrodes"].get("length_mm", [tip_len] + [1.0] * (len(offsets) - 1))
    rings = []
    for index, (from_tip, length) in enumerate(zip(offsets, lengths, strict=True)):
        if index == 0:
            continue
        s_c = line.from_tip(from_tip)
        half = length / 2.0
        fr = [line.frame(s_c + t) for t in (-half, -half + 0.1, half - 0.1, half)]
        rr = [outer_r * 1.001, ring_r, ring_r, outer_r * 1.001]
        ring = make_object(
            f"RingElectrode_{index}", sweep(fr, rr, n_around), mats["electrode"], col
        )
        ring["arclength_from_tip_mm"] = from_tip
        rings.append(ring)
        objects.append(ring)
    named["rings"] = rings
    return objects, named


def build_distal_internals(line: Centreline, profile: dict, mats, col) -> list:
    """Coil, spring, sensors, anchor, pull wires, lumen, lead bundle."""
    objects = []
    ft = line.from_tip

    def local(s_from_tip: float) -> Frame:
        return line.frame(ft(s_from_tip))

    # --- irrigation lumen: handle -> tip base, on the axis
    lumen_frames = [line.frame(s) for s in samples_along(line, 0.0, ft(D["hollow_s_mm"][0]) + 0.6)]
    objects.append(
        make_object(
            "IrrigationLumen",
            sweep(lumen_frames, [D["lumen_radius_mm"]] * len(lumen_frames), 14),
            mats["lumen"],
            col,
        )
    )

    # --- transmitter coil: core (also the tip stem) + copper winding
    c0, c1 = D["coil_s_mm"]
    base = local(c1)  # proximal end; frame tangent points distally
    stem_frames = [local(c1 + 0.2), local(profile["geometry"]["tip_length_mm"] - 0.4)]
    objects.append(
        make_object(
            "TransmitterCoilCore",
            sweep(stem_frames, [D["coil_core_radius_mm"]] * 2, 16),
            mats["core"],
            col,
        )
    )
    pts = helix_points(base, D["coil_wind_radius_mm"], c1 - c0, D["coil_turns"], per_turn=16)
    objects.append(
        make_object(
            "TransmitterCoil", sweep_polyline(pts, D["coil_wire_radius_mm"], 8), mats["copper"], col
        )
    )

    # --- precision spring between the coil (tip side) and the sensor housing
    s0, s1 = D["spring_s_mm"]
    base = local(s1)
    pts = helix_points(base, D["spring_radius_mm"], s1 - s0, D["spring_turns"], per_turn=28)
    objects.append(
        make_object(
            "PrecisionSpring",
            sweep_polyline(pts, D["spring_wire_radius_mm"], 10),
            mats["steel_dark"],
            col,
        )
    )
    for name, s_a in (
        ("SpringCollar_Distal", s0 - D["spring_collar_len_mm"]),
        ("SpringCollar_Proximal", s1),
    ):
        fr = [local(s_a + D["spring_collar_len_mm"]), local(s_a)]
        collar = merge([sweep(fr, [D["spring_radius_mm"] + 0.12] * 2, 20)])
        objects.append(make_object(name, collar, mats["steel_light"], col))

    # --- three location-sensor coils, tilted, around the lumen
    e0, e1 = D["sensor_s_mm"]
    for k in range(D["sensor_count"]):
        az = 2.0 * math.pi * k / D["sensor_count"] + math.pi / 2.0
        centre_frame = local((e0 + e1) / 2.0)
        pos, tan, nrm, bin_ = centre_frame
        radial = (nrm * math.cos(az) + bin_ * math.sin(az)).normalized()
        centre = pos + radial * D["sensor_offset_mm"]
        tilt = math.radians(D["sensor_tilt_deg"])
        axis = (tan * math.cos(tilt) + radial * math.sin(tilt)).normalized()
        n2 = axis.cross(radial).normalized()
        b2 = axis.cross(n2).normalized()
        length = e1 - e0
        start = centre - axis * (length / 2.0)
        sensor_frame: Frame = (start, axis, n2, b2)
        end_frame: Frame = (start + axis * length, axis, n2, b2)
        core = sweep([sensor_frame, end_frame], [D["sensor_core_radius_mm"]] * 2, 12)
        objects.append(make_object(f"LocationSensorCore_{k + 1}", core, mats["core"], col))
        pts = helix_points(
            sensor_frame, D["sensor_wind_radius_mm"], length, D["sensor_turns"], per_turn=12
        )
        objects.append(
            make_object(
                f"LocationSensor_{k + 1}",
                sweep_polyline(pts, D["sensor_wire_radius_mm"], 6),
                mats["copper"],
                col,
            )
        )

    # --- pull-wire anchor ring (distal end of the deflectable section)
    a0, a1 = D["anchor_s_mm"]
    fr = [local(a1), local(a0)]
    outer = sweep(fr, [D["shaft_inner_radius_mm"] - 0.02] * 2, 24)
    objects.append(make_object("PullWireAnchor", outer, mats["steel_light"], col))

    # --- two pull wires (+Z / -Z in the bend plane) from the handle to the anchor
    for name, angle in (("PullWire_Up", math.pi), ("PullWire_Down", 0.0)):
        fr = [
            offset_frame(line.frame(s), angle, D["pull_wire_offset_mm"])
            for s in samples_along(line, 0.0, ft(a1) + 0.3)
        ]
        objects.append(
            make_object(
                name, sweep(fr, [D["pull_wire_radius_mm"]] * len(fr), 8), mats["steel_dark"], col
            )
        )

    # --- electrode lead bundle (+Y side, back wall of the cutaway)
    fr = [
        offset_frame(line.frame(s), math.pi / 2.0, D["lead_bundle_offset_mm"])
        for s in samples_along(line, 0.0, ft(profile["electrodes"]["arclength_from_tip_mm"][1]))
    ]
    objects.append(
        make_object(
            "ElectrodeLeadBundle",
            sweep(fr, [D["lead_bundle_radius_mm"]] * len(fr), 8),
            mats["lead"],
            col,
        )
    )
    return objects


def build_distal_cutaway(line: Centreline, named: dict, mats, col) -> list:
    """Cutaway twins of the shaft and rings: hollow tube with a sector window."""
    n_around = D["segments_around"]
    ft = line.from_tip
    shaft_cut = duplicate(named["shaft"], "Shaft_Cutaway", col)
    h0, h1 = D["hollow_s_mm"]
    fr = [line.frame(s) for s in samples_along(line, ft(h1), ft(h0))]
    hollow = make_object(
        "HollowCutter",
        sweep(fr, [D["shaft_inner_radius_mm"]] * len(fr), n_around),
        mats["shaft"],
        col,
        smooth=False,
    )
    c0, c1 = D["cut_s_mm"]
    fr = [line.frame(s) for s in samples_along(line, ft(c1), ft(c0))]
    wedge = make_object(
        "WedgeCutter",
        sweep_polygon(fr, sector_uv(2.2, D["cut_centre_deg"], D["cut_half_deg"])),
        mats["shaft"],
        col,
        smooth=False,
    )
    apply_booleans(shaft_cut, [hollow, wedge])
    objects = [shaft_cut]
    for ring in named["rings"]:
        twin = duplicate(ring, f"{ring.name}_Cutaway", col)
        fr = [line.frame(s) for s in samples_along(line, ft(c1), ft(c0))]
        wedge = make_object(
            "WedgeCutter",
            sweep_polygon(fr, sector_uv(2.2, D["cut_centre_deg"], D["cut_half_deg"])),
            mats["shaft"],
            col,
            smooth=False,
        )
        apply_booleans(twin, [wedge])
        objects.append(twin)
    return objects


def revolve(x_and_r: list[tuple[float, float]], n_around: int, modulation=None) -> Mesh:
    frames = [axis_frame(x) for x, _ in x_and_r]
    return sweep(frames, [r for _, r in x_and_r], n_around, modulation=modulation)


def capsule_profile(
    x0: float, x1: float, radius: float, n: int = 40, waist: float = 0.0
) -> list[tuple[float, float]]:
    """Rounded body from x0 (distal) to x1 (proximal), optional ergonomic waist."""
    out = []
    for k in range(n + 1):
        u = k / n
        x = x0 + (x1 - x0) * u
        d0, d1 = x0 - x, x - x1
        r = radius
        if d0 < radius:
            r = math.sqrt(max(radius**2 - (radius - d0) ** 2, 0.0))
        elif d1 < radius:
            r = math.sqrt(max(radius**2 - (radius - d1) ** 2, 0.0))
        else:
            r = (
                radius
                - waist * math.sin(math.pi * (d0 - radius) / (abs(x1 - x0) - 2 * radius)) ** 2
            )
        out.append((x, max(r, 0.0)))
    return out


def build_handle(mats, col) -> tuple[list, dict]:
    """Handle exterior and its mechanism. Returns (objects, named)."""
    n_around = 48
    objects = []
    named: dict = {}
    r_shaft = 1.25

    # strain relief + conical nose
    sr = D["strain_relief_len_mm"]
    prof = [
        (
            -sr * (k / 12.0),
            r_shaft + (D["strain_relief_end_radius_mm"] - r_shaft) * (k / 12.0) ** 1.6,
        )
        for k in range(13)
    ]
    objects.append(make_object("StrainRelief", revolve(prof, n_around), mats["handle"], col))
    nose_x0, nose_x1 = -sr, -sr - D["nose_len_mm"]
    prof = [
        (
            nose_x0 + (nose_x1 - nose_x0) * (k / 10.0),
            D["strain_relief_end_radius_mm"]
            + (D["knob_radius_mm"] * 0.72 - D["strain_relief_end_radius_mm"]) * (k / 10.0) ** 0.7,
        )
        for k in range(11)
    ]
    objects.append(make_object("HandleNose", revolve(prof, n_around), mats["handle"], col))
    # nose-to-knob neck
    objects.append(
        make_object(
            "Neck",
            revolve(
                [
                    (nose_x1 + 0.5, D["knob_radius_mm"] * 0.72),
                    (D["knob_x_mm"][1] - 0.5, D["knob_radius_mm"] * 0.72),
                ],
                n_around,
            ),
            mats["handle"],
            col,
        )
    )

    # rotary deflection knob (knurled collar, coaxial)
    kx0, kx1 = D["knob_x_mm"]
    kr = D["knob_radius_mm"]
    ridges = D["knob_ridges"]

    def knurl(k: int, n: int) -> float:
        return 1.0 + 0.045 * (1.0 if (k * ridges // n) % 2 == 0 else -1.0)

    prof = [
        (kx1, kr * 0.72),
        (kx1 - 0.1, kr * 0.92),
        (kx1 - 1.2, kr),
        (kx0 + 1.2, kr),
        (kx0 + 0.1, kr * 0.92),
        (kx0, kr * 0.72),
    ]
    knob = make_object(
        "DeflectionKnob", revolve(prof, 2 * ridges * 2, modulation=knurl), mats["knob"], col
    )
    bore_r = D["knob_bore_radius_mm"]
    bore = make_object(
        "KnobBore",
        revolve([(kx1 + 1.0, bore_r), (kx0 - 1.0, bore_r)], 32),
        mats["knob"],
        col,
        smooth=False,
    )
    apply_booleans(knob, [bore])
    named["knob"] = knob
    objects.append(knob)
    # hub: couples the knob collar to the cam shaft
    hub_x = (kx0 + kx1) / 2.0 + 3.0
    objects.append(
        make_object(
            "KnobHub",
            revolve([(hub_x + 1.0, bore_r + 0.05), (hub_x - 1.0, bore_r + 0.05)], 32),
            mats["steel_light"],
            col,
        )
    )

    # tension / friction adjustment ring
    tx0, tx1 = D["tension_x_mm"]
    tr = D["tension_radius_mm"]
    prof = [(tx1, kr * 0.72), (tx1 - 0.05, tr), (tx0 + 0.05, tr), (tx0, kr * 0.72)]
    tension = make_object(
        "TensionRing", revolve(prof, 2 * ridges * 2, modulation=knurl), mats["steel_light"], col
    )
    bore = make_object(
        "TensionBore",
        revolve([(tx1 + 1.0, bore_r), (tx0 - 1.0, bore_r)], 32),
        mats["knob"],
        col,
        smooth=False,
    )
    apply_booleans(tension, [bore])
    named["tension"] = tension
    objects.append(tension)

    # ergonomic body
    bx0, bx1 = D["body_x_mm"]
    body = make_object(
        "HandleBody",
        revolve(capsule_profile(bx0 + 0.6, bx1, D["body_radius_mm"], waist=1.2), n_around),
        mats["handle"],
        col,
    )
    named["body"] = body
    objects.append(body)

    # connector, cable, irrigation line + luer (proximal end)
    cx0, cx1 = D["connector_x_mm"]
    objects.append(
        make_object(
            "Connector",
            revolve(
                [(cx1 + 1.0, D["connector_radius_mm"]), (cx0, D["connector_radius_mm"])], n_around
            ),
            mats["connector"],
            col,
        )
    )
    objects.append(
        make_object(
            "ConnectorKey",
            revolve(
                [
                    (cx0 + 4.0, D["connector_radius_mm"] + 0.8),
                    (cx0 + 1.5, D["connector_radius_mm"] + 0.8),
                ],
                n_around,
            ),
            mats["steel_light"],
            col,
        )
    )
    objects.append(
        make_object(
            "Cable",
            revolve(
                [
                    (cx0 + 0.5, D["cable_radius_mm"]),
                    (cx0 - D["cable_len_mm"], D["cable_radius_mm"]),
                ],
                n_around,
            ),
            mats["cable"],
            col,
        )
    )
    z_irr = D["irrigation_line_offset_z_mm"]
    line_pts = [
        Vector((bx1 + 6.0, 0.0, 1.5)),
        Vector((bx1 - 4.0, 0.0, z_irr)),
        Vector((bx1 - D["irrigation_line_len_mm"], 0.0, z_irr)),
    ]
    objects.append(
        make_object(
            "IrrigationLine",
            sweep_polyline(line_pts, D["irrigation_line_radius_mm"], 16),
            mats["tube"],
            col,
        )
    )
    lx = bx1 - D["irrigation_line_len_mm"]
    luer_frames = [
        (Vector((lx + 1.0, 0.0, z_irr)), Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, 1, 0))),
        (
            Vector((lx - D["luer_len_mm"], 0.0, z_irr)),
            Vector((1, 0, 0)),
            Vector((0, 0, 1)),
            Vector((0, 1, 0)),
        ),
    ]
    objects.append(
        make_object(
            "IrrigationLuer",
            sweep(luer_frames, [D["luer_radius_mm"]] * 2, 20),
            mats["connector"],
            col,
        )
    )

    # --- mechanism: cam on a shaft driven by the knob; pull wires wrap the cam
    cam_x = D["cam_x_mm"]
    cr = D["cam_radius_mm"]
    ct = D["cam_thickness_mm"]
    cam = make_object(
        "DeflectionCam",
        revolve([(cam_x + ct / 2, cr), (cam_x - ct / 2, cr)], 40),
        mats["steel_light"],
        col,
    )
    objects.append(cam)
    objects.append(
        make_object(
            "CamShaft",
            revolve(
                [(kx1 + 2.0, D["cam_shaft_radius_mm"]), (tx0 - 1.0, D["cam_shaft_radius_mm"])], 16
            ),
            mats["steel_dark"],
            col,
        )
    )
    # wire termination pins on the cam rim
    for name, sign in (("CamPin_Up", 1.0), ("CamPin_Down", -1.0)):
        pin_frames = [
            (
                Vector((cam_x, 0.0, sign * (cr - 0.8))),
                Vector((0, 0, sign)),
                Vector((1, 0, 0)),
                Vector((0, 1, 0)),
            ),
            (
                Vector((cam_x, 0.0, sign * (cr + 0.9))),
                Vector((0, 0, sign)),
                Vector((1, 0, 0)),
                Vector((0, 1, 0)),
            ),
        ]
        objects.append(
            make_object(name, sweep(pin_frames, [0.5, 0.5], 10), mats["steel_dark"], col)
        )
    # handle-side pull wires: shaft exit -> guide -> wrap ~110 deg around the cam -> pin
    for name, sign in (("PullWire_Up_Handle", 1.0), ("PullWire_Down_Handle", -1.0)):
        pts = [
            Vector((0.5, 0.0, sign * D["pull_wire_offset_mm"])),
            Vector((nose_x0, 0.0, sign * D["pull_wire_offset_mm"])),
            Vector((nose_x1, 0.0, sign * 2.0)),
        ]
        a_start = math.radians(0.0)  # tangent point on the +X side of the cam
        for k in range(15):
            a = a_start + math.radians(110.0) * k / 14.0
            pts.append(Vector((cam_x + cr * math.cos(a), 0.0, sign * cr * math.sin(a))))
        # straight run from the neck to the cam tangent point
        pts.insert(3, Vector((cam_x + cr + 6.0, 0.0, sign * 2.6)))
        objects.append(
            make_object(
                name, sweep_polyline(pts, D["handle_wire_radius_mm"], 8), mats["steel_dark"], col
            )
        )
    # electrode leads and irrigation lumen continue through the handle
    objects.append(
        make_object(
            "ElectrodeLeadBundle_Handle",
            revolve(
                [
                    (0.5, D["lead_bundle_radius_mm"] * 2.2),
                    (cx1 + 2.0, D["lead_bundle_radius_mm"] * 2.2),
                ],
                10,
            ),
            mats["lead"],
            col,
        )
    )
    lumen_pts = [
        Vector((0.5, 0.0, 0.0)),
        Vector((bx1 + 14.0, 0.0, 0.0)),
        Vector((bx1 + 6.0, 0.0, 1.5)),
    ]
    objects.append(
        make_object(
            "IrrigationLumen_Handle",
            sweep_polyline(lumen_pts, D["lumen_radius_mm"], 12),
            mats["lumen"],
            col,
        )
    )
    return objects, named


def build_handle_cutaway(named: dict, mats, col) -> list:
    """Shell twins of body, knob and tension ring with a window on the -Y side."""
    objects = []
    hx0, hx1 = D["handle_cut_x_mm"]
    y_cut = D["handle_cut_y_mm"]

    def slab(name: str) -> object:
        frames = [axis_frame(hx1), axis_frame(hx0)]
        return make_object(
            name,
            sweep_polygon(frames, [(-40.0, y_cut), (40.0, y_cut), (40.0, -40.0), (-40.0, -40.0)]),
            mats["handle"],
            col,
            smooth=False,
        )

    body = duplicate(named["body"], "HandleBody_Cutaway", col)
    bx0, bx1 = D["body_x_mm"]
    inner = make_object(
        "BodyHollowCutter",
        revolve(
            capsule_profile(
                bx0 + 0.6 - D["shell_thickness_mm"],
                bx1 + D["shell_thickness_mm"],
                D["body_radius_mm"] - D["shell_thickness_mm"],
                waist=1.2,
            ),
            48,
        ),
        mats["handle"],
        col,
        smooth=False,
    )
    apply_booleans(body, [inner, slab("BodySlab")])
    objects.append(body)
    knob = duplicate(named["knob"], "DeflectionKnob_Cutaway", col)
    apply_booleans(knob, [slab("KnobSlab")])
    objects.append(knob)
    tension = duplicate(named["tension"], "TensionRing_Cutaway", col)
    apply_booleans(tension, [slab("TensionSlab")])
    objects.append(tension)
    return objects


def build_pose(
    profile: dict, deflection_deg: float, shaft_length_mm: float, col, mats, cutaway: bool
):
    geometry = profile["geometry"]
    line = Centreline(
        shaft_length_mm, geometry["active_length_mm"], geometry["tip_length_mm"], deflection_deg
    )
    outer, named = build_distal_outer(line, profile, mats, col)
    internals = build_distal_internals(line, profile, mats, col)
    outer_cut = build_distal_cutaway(line, named, mats, col)
    handle, hnamed = build_handle(mats, col)
    handle_cut = build_handle_cutaway(hnamed, mats, col)

    closed = [named["shaft"], *named["rings"], hnamed["body"], hnamed["knob"], hnamed["tension"]]
    for obj in closed:
        obj.hide_viewport = cutaway
        obj.hide_render = cutaway
    for obj in outer_cut + handle_cut:
        obj.hide_viewport = not cutaway
        obj.hide_render = not cutaway
    everything = outer + internals + outer_cut + handle + handle_cut
    tag(everything, deflection_deg)
    return everything, line


# ---------------------------------------------------------------------------
# Scene, views, export
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
        "copper": material("Coil_Copper", (0.85, 0.42, 0.12), 0.9, 0.35),
        "core": material("Coil_Core", (0.45, 0.45, 0.48), 0.6, 0.5),
        "steel_dark": material("Steel_Dark", (0.25, 0.26, 0.28), 1.0, 0.4),
        "steel_light": material("Steel_Light", (0.70, 0.71, 0.73), 1.0, 0.3),
        "lumen": material("Irrigation_Lumen", (0.55, 0.78, 0.95), 0.0, 0.2, alpha=0.75),
        "tube": material("Irrigation_Tube", (0.80, 0.90, 0.97), 0.0, 0.25, alpha=0.8),
        "lead": material("Electrode_Leads", (0.16, 0.35, 0.22), 0.0, 0.6),
        "handle": material("Handle_Polymer", (0.20, 0.22, 0.26), 0.0, 0.5),
        "knob": material("Knob_Polymer", (0.08, 0.08, 0.09), 0.0, 0.55),
        "connector": material("Connector", (0.35, 0.36, 0.38), 0.3, 0.5),
        "cable": material("Cable", (0.10, 0.10, 0.11), 0.0, 0.7),
    }


VIEWS = {
    # name: (target(line), distance mm, lens mm, direction from target)
    "distal": (
        lambda line: (line.point(line.flexible_start - 15.0)[0] + line.point(line.total)[0]) / 2.0,
        250.0,
        50.0,
        Vector((-0.25, -1.0, 0.35)),
    ),
    "tip": (lambda line: line.point(line.total - 8.0)[0], 55.0, 85.0, Vector((0.85, -0.75, 0.45))),
    "internals": (
        lambda line: line.point(line.total - 13.0)[0],
        62.0,
        100.0,
        Vector((-0.3, -1.0, 0.55)),
    ),
    "handle": (lambda _line: Vector((-100.0, 0.0, 0.0)), 400.0, 50.0, Vector((0.35, -1.0, 0.45))),
    "mechanism": (lambda _line: Vector((-58.0, 0.0, 0.0)), 150.0, 85.0, Vector((0.25, -1.0, 0.7))),
}


def add_camera_and_light(scene, line: Centreline):
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
    for name, energy, rot in (
        ("KeyLight", 3.0, (50.0, 10.0, -35.0)),
        ("FillLight", 1.2, (-60.0, -20.0, 140.0)),
        ("RimLight", 0.8, (30.0, 40.0, 60.0)),
    ):
        light_data = bpy.data.lights.new(name, "SUN")
        light_data.energy = energy
        light_data.angle = math.radians(8.0)
        light = bpy.data.objects.new(name, light_data)
        light.rotation_euler = tuple(math.radians(v) for v in rot)
        scene.collection.objects.link(light)


def set_view(scene, line: Centreline, view: str) -> None:
    target_fn, distance, lens, direction = VIEWS[view]
    target = bpy.data.objects["CameraTarget"]
    target.location = target_fn(line)
    scene.camera.data.lens = lens
    scene.camera.location = target.location + direction.normalized() * distance


def add_disclaimer_text(scene, line: Centreline):
    curve = bpy.data.curves.new("Disclaimer", "FONT")
    curve.body = (
        f"{DISCLAIMER}\n"
        "GenericSteerableRF - illustrative class-level cutaway, not a specific device."
    )
    curve.size = 4.0
    curve.align_x = "CENTER"
    text = bpy.data.objects.new("Disclaimer", curve)
    text.location = (line.total / 2.0, 0.0, -30.0)
    text.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    text.hide_render = True
    scene.collection.objects.link(text)


def render(scene, path: Path, samples: int = 48) -> bool:
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(path)
    for engine in ("CYCLES", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = engine
            if engine == "CYCLES":
                scene.cycles.samples = samples
                scene.cycles.device = "CPU"
                scene.cycles.use_denoising = False
            bpy.ops.render.render(write_still=True)
            return True
        except Exception as error:
            print(f"[warn] {engine} render failed ({error})")
    return False


def export_collection(collection, out_dir: Path, stem: str) -> list[str]:
    written = []
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    for obj in collection.objects:
        if not obj.hide_viewport:
            obj.select_set(True)
    for suffix, op, kwargs in (
        (
            ".glb",
            "export_scene.gltf",
            {
                "export_format": "GLB",
                "use_selection": True,
                "export_apply": True,
                "export_yup": True,
            },
        ),
        (
            ".obj",
            "wm.obj_export",
            {"export_selected_objects": True, "export_materials": True, "apply_modifiers": True},
        ),
        (".stl", "wm.stl_export", {"export_selected_objects": True, "apply_modifiers": True}),
    ):
        path = out_dir / f"{stem}{suffix}"
        try:
            module, name = op.split(".")
            getattr(getattr(bpy.ops, module), name)(filepath=str(path), **kwargs)
            written.append(path.name)
            if suffix == ".obj" and path.with_suffix(".mtl").exists():
                written.append(path.with_suffix(".mtl").name)
        except Exception as error:
            print(f"[warn] {suffix} export failed: {error}")
    return written


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="assets/demo/catheters")
    parser.add_argument("--poses", default="0,90,180")
    parser.add_argument("--shaft-length", type=float, default=None)
    parser.add_argument("--no-cutaway", action="store_true")
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
    cutaway = not args.no_cutaway

    scene = setup_scene()
    mats = make_materials()
    collections = []
    lines = []
    for deflection in poses:
        col = bpy.data.collections.new(f"GenericSteerableRF_deflection_{round(deflection):03d}deg")
        scene.collection.children.link(col)
        col["provenance"] = PROVENANCE
        col["disclaimer"] = DISCLAIMER
        _objects, line = build_pose(profile, deflection, shaft_length, col, mats, cutaway)
        collections.append((col, deflection))
        lines.append(line)

    add_camera_and_light(scene, lines[0])
    add_disclaimer_text(scene, lines[0])

    def show_only(active) -> None:
        for col, _ in collections:
            col.hide_viewport = col is not active
            col.hide_render = col is not active

    written: list[str] = []
    if not args.no_render:
        for index, (col, deflection) in enumerate(collections):
            show_only(col)
            views = ("distal", "tip", "internals") + (("handle", "mechanism") if index == 0 else ())
            for view in views:
                set_view(scene, lines[index], view)
                png = (
                    out_dir
                    / f"generic-steerable-rf-deflection-{round(deflection):03d}deg-{view}.png"
                )
                if render(scene, png):
                    written.append(png.name)
        set_view(scene, lines[0], "distal")
    if not args.no_export:
        for col, deflection in collections:
            show_only(col)
            written.extend(
                export_collection(
                    col, out_dir, f"generic-steerable-rf-deflection-{round(deflection):03d}deg"
                )
            )
        show_only(collections[0][0])
        blend = out_dir / "generic-steerable-rf.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        written.append(blend.name)

    print("Wrote:", ", ".join(written) if written else "(scene built only)")
    print(PROVENANCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
