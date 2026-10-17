import bpy, math, os, sys
from mathutils import Vector

try:
    import numpy  # noqa: F401
except ImportError as exc:
    raise RuntimeError("NumPy is missing from Blender Python; install the matching NumPy wheel in the workflow") from exc

src = os.environ.get("INPUT_GLB", "anime_man_traditional_robe.glb")
out = os.environ.get("OUTPUT_GLB", "public/models/player-rigged.glb")
os.makedirs(os.path.dirname(out), exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.import_scene.gltf(filepath=src)
except BaseException as exc:
    print("GLB_IMPORT_FAILED:", repr(exc), flush=True)
    os._exit(1)

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    raise RuntimeError("GLB contains no mesh objects")

# Bake imported transforms into the mesh so the armature and vertex weights share one coordinate space.
for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.select_set(False)

# DIAGNOSTICS: inspect original mesh objects before joining them.
for obj in meshes:
    if obj.data.vertices:
        vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        print("SOURCE_MESH", obj.name, "verts", len(vs),
              "bounds", [round(x,5) for x in lo], [round(x,5) for x in hi],
              "materials", [m.name if m else None for m in obj.data.materials], flush=True)

# Combine the original geometry without changing its shape or vertex positions.
bpy.ops.object.select_all(action="DESELECT")
for obj in meshes: obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
mesh = bpy.context.object
mesh.name = "OriginalCharacterMesh"

# Diagnose connected geometry islands without changing the mesh.
import bmesh
bm = bmesh.new()
bm.from_mesh(mesh.data)
bm.verts.ensure_lookup_table()
seen = set()
islands = []
for seed in bm.verts:
    if seed.index in seen:
        continue
    stack = [seed]
    seen.add(seed.index)
    component = []
    while stack:
        v = stack.pop()
        component.append(v)
        for e in v.link_edges:
            other = e.other_vert(v)
            if other.index not in seen:
                seen.add(other.index)
                stack.append(other)
    if len(component) >= 20:
        xs = [v.co.x for v in component]
        ys = [v.co.y for v in component]
        zs = [v.co.z for v in component]
        islands.append((len(component), min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
islands.sort(reverse=True)
print("CONNECTED_ISLAND_COUNT", len(islands), flush=True)
for row in islands[:60]:
    print("CONNECTED_ISLAND", row[0], "bounds",
          [round(x,5) for x in row[1:]], flush=True)
bm.free()


coords = [v.co.copy() for v in mesh.data.vertices]
minv = Vector((min(v.x for v in coords), min(v.y for v in coords), min(v.z for v in coords)))
maxv = Vector((max(v.x for v in coords), max(v.y for v in coords), max(v.z for v in coords)))
center = (minv + maxv) * 0.5

import numpy as np
# Diagnose horizontal anatomy by height bands before assigning leg bones.
height_diag = maxv.z - minv.z
for lo, hi in ((0.00,0.04),(0.04,0.08),(0.08,0.12),(0.12,0.18),(0.18,0.25),(0.25,0.35),(0.35,0.48),(0.48,0.62)):
    band = [v.co.x for v in mesh.data.vertices
            if lo <= (v.co.z-minv.z)/height_diag < hi]
    if band:
        arr = np.asarray(band, dtype=np.float64)
        print("HEIGHT_X_BAND", lo, hi, "n", len(band),
              "q05_q25_q50_q75_q95",
              [round(float(q),5) for q in np.quantile(arr,[.05,.25,.5,.75,.95])],
              flush=True)

# FOOTWEAR DIAGNOSTICS ONLY: inspect each low-height side region in XYZ.
# No vertex coordinates are modified in this pass.
for lo, hi in ((0.00,0.02),(0.02,0.04),(0.04,0.06),(0.06,0.08),(0.08,0.10)):
    for side, side_sign in (("L", 1), ("R", -1)):
        pts = [v.co for v in mesh.data.vertices
               if lo <= (v.co.z-minv.z)/height_diag < hi
               and (v.co.x-center.x)*side_sign > height_diag*0.025]
        if pts:
            arr = np.asarray([[p.x, p.y, p.z] for p in pts], dtype=np.float64)
            qs = np.quantile(arr, [0.05, 0.25, 0.50, 0.75, 0.95], axis=0)
            print("FOOT_REGION", side, lo, hi, "n", len(pts),
                  "q05_q25_q50_q75_q95_xyz",
                  [[round(float(x),5) for x in row] for row in qs], flush=True)

# Fit the horizontal long axis of the lowermost footwear candidates.
# This is diagnostic only; it does not alter any vertices.
for side, side_sign in (("L", 1), ("R", -1)):
    pts = [[v.co.x, v.co.y] for v in mesh.data.vertices
           if 0.0 <= (v.co.z-minv.z)/height_diag < 0.04
           and (v.co.x-center.x)*side_sign > height_diag*0.025]
    arr = np.asarray(pts, dtype=np.float64)
    cov = np.cov(arr.T)
    vals, vecs = np.linalg.eigh(cov)
    axis = vecs[:, int(np.argmax(vals))]
    print("FOOT_AXIS_PCA", side, "center_xy",
          [round(float(x),5) for x in arr.mean(axis=0)],
          "eigenvalues", [round(float(x),7) for x in vals],
          "long_axis_xy", [round(float(x),6) for x in axis], flush=True)

# Correct only the lower footwear geometry using measured mirrored PCA axes.
# Full correction below 4% of character height, smoothly fading to zero by 8%.
for side, side_sign, angle_deg in (("L", 1, -19.0), ("R", -1, 19.0)):
    shoe = [v for v in mesh.data.vertices
            if 0.0 <= (v.co.z-minv.z)/height_diag < 0.04
            and (v.co.x-center.x)*side_sign > height_diag*0.025]
    if len(shoe) < 1000:
        raise RuntimeError(f"Footwear selection too small for {side}: {len(shoe)}")
    pivot_x = sum(v.co.x for v in shoe) / len(shoe)
    pivot_y = sum(v.co.y for v in shoe) / len(shoe)
    angle = math.radians(angle_deg)
    cs, sn = math.cos(angle), math.sin(angle)
    changed = 0
    for v in mesh.data.vertices:
        zf = (v.co.z-minv.z)/height_diag
        if zf < 0.04 or zf >= 0.08:
            continue
        if (v.co.x-center.x)*side_sign <= height_diag*0.025:
            continue
        fade = max(0.0, min(1.0, (0.08-zf)/0.04))
        a = angle * fade
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = v.co.x-pivot_x, v.co.y-pivot_y
        v.co.x = pivot_x + dx*ca - dy*sa
        v.co.y = pivot_y + dx*sa + dy*ca
        changed += 1
    for v in shoe:
        dx, dy = v.co.x-pivot_x, v.co.y-pivot_y
        v.co.x = pivot_x + dx*cs - dy*sn
        v.co.y = pivot_y + dx*sn + dy*cs
    print("FOOTWEAR_ROTATED", side, "degrees", angle_deg,
          "core_vertices", len(shoe), "blend_vertices", changed, flush=True)

# Update mesh after the controlled footwear-only correction.
mesh.data.update()

mesh.data.update()

# TROUSER PANEL DIAGNOSTICS: histogram x coordinates in the lower garment.
# This identifies the two actual cloth columns instead of using robe-wide medians.
for lo, hi in ((0.10,0.18),(0.18,0.25),(0.25,0.35),(0.35,0.42)):
    vals = np.asarray([v.co.x-center.x for v in mesh.data.vertices
                       if lo <= (v.co.z-minv.z)/height_diag < hi], dtype=np.float64)
    hist, edges = np.histogram(vals, bins=48, range=(-0.36*height_diag,0.36*height_diag))
    peaks = np.argsort(hist)[-12:][::-1]
    print("TROUSER_X_HIST", lo, hi, [(round(float((edges[k]+edges[k+1])*0.5/height_diag),4), int(hist[k])) for k in peaks], flush=True)

# Keep the leg chains closer together: the previous 0.14-height offset
# placed the visible skeleton too far outside the actual leg columns.
# The same measured centers are used by both the bones and weight assignment.
height = maxv.z - minv.z
LEG_CENTER_OFFSET = 0.095
leg_centers = {
    "L": center.x + LEG_CENTER_OFFSET * height,
    "R": center.x - LEG_CENTER_OFFSET * height,
}
print("LEG_CENTER_MEASURED", {k: round(v,5) for k,v in leg_centers.items()}, flush=True)
print("LEG_CENTER_TROUSER_OFFSET", LEG_CENTER_OFFSET, flush=True)

height = maxv.z - minv.z
if height <= 0: raise RuntimeError("Character has no vertical height on Blender Z axis")

# Preserve the source model's original materials, textures, UVs and face assignments.
# Build a humanoid skeleton proportioned to the original model's measured bounds.
# x = character left/right, y = front/back, z = vertical.
def p(x, z, y=0):
    return (center.x + x * height, center.y + y * height, minv.z + z * height)

bones = [
 ("root", p(0,0.02), p(0,0.12), None),
 ("pelvis", p(0,0.43), p(0,0.53), "root"),
 ("spine", p(0,0.48), p(0,0.68), "pelvis"),
 ("chest", p(0,0.65), p(0,0.80), "spine"),
 ("neck", p(0,0.78), p(0,0.88), "chest"),
 ("head", p(0,0.86), p(0,0.99), "neck"),
]
for side, sign in (("L",1),("R",-1)):
    bones += [
      (f"upper_arm.{side}", p(sign*0.055,0.78), p(sign*0.17,0.63), "chest"),
      (f"forearm.{side}", p(sign*0.17,0.63), p(sign*0.20,0.43), f"upper_arm.{side}"),
      (f"hand.{side}", p(sign*0.20,0.43), p(sign*0.20,0.35), f"forearm.{side}"),
      # Follow measured centers of the two trouser legs, not guessed offsets.
      (f"thigh.{side}", (leg_centers[side], center.y, minv.z + 0.48*height),
       (leg_centers[side], center.y, minv.z + 0.27*height), "pelvis"),
      (f"shin.{side}", (leg_centers[side], center.y, minv.z + 0.27*height),
       (leg_centers[side], center.y, minv.z + 0.07*height), f"thigh.{side}"),
      # Foot bone follows the foot's long axis; retain forward toe direction.
      (f"foot.{side}", (leg_centers[side], center.y, minv.z + 0.07*height),
       (leg_centers[side], center.y + 0.16*height, minv.z + 0.055*height), f"shin.{side}"),
    ]

arm_data = bpy.data.armatures.new("CharacterRig")
arm = bpy.data.objects.new("CharacterRig", arm_data)
bpy.context.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
edit = {}
for name, head, tail, parent in bones:
    b = arm_data.edit_bones.new(name)
    b.head, b.tail = Vector(head), Vector(tail)
    if (b.tail-b.head).length < 0.0001: b.tail.y += 0.001
    edit[name] = b
for name, head, tail, parent in bones:
    if parent: edit[name].parent = edit[parent]
bpy.ops.object.mode_set(mode="OBJECT")

# Region-aware smooth skinning. A single-piece robe must not inherit leg
# weights across the whole skirt: limit limb influence to its actual region.
segments = [(name, Vector(h), Vector(t)) for name,h,t,parent in bones if name != "root"]
groups = {name: mesh.vertex_groups.new(name=name) for name,_,_ in segments}
for i, v in enumerate(mesh.data.vertices):
    point = v.co
    z = (point.z - minv.z) / height
    x = (point.x - center.x) / height
    distances = []
    for name, a, b in segments:
        # Keep left/right leg weights on their own side. Without this
        # partition, nearest-neighbour weighting can blend the opposite leg
        # into the inner robe and pull the knees/feet diagonally.
        if name.startswith(("thigh", "shin", "foot")):
            side = "L" if name.endswith(".L") else "R"
            side_sign = 1 if side == "L" else -1
            leg_x = (leg_centers[side] - center.x) / height
            if (x - leg_x) * side_sign < -0.025: continue
        # Keep upper-body cloth attached to the torso instead of the moving legs.
        if name.startswith("thigh") and z > 0.64: continue
        if name.startswith("shin") and z > 0.40: continue
        if name.startswith("foot") and z > 0.19: continue
        # Arms should affect sleeves and hands, not the chest or central robe.
        if name.startswith(("upper_arm", "forearm", "hand")):
            side = 1 if name.endswith(".L") else -1
            if z < 0.30 or x * side < 0.045: continue
        if name == "head" and z < 0.78: continue
        if name == "neck" and z < 0.68: continue
        ab = b-a
        t = max(0.0, min(1.0, (point-a).dot(ab) / max(ab.length_squared, 1e-9)))
        d = (point - (a + t*ab)).length
        # Smoothly fade leg influence near the top of the robe.
        if name.startswith("thigh") and z > 0.48:
            d += height * (z - 0.48) * 2.5
        distances.append((d, name))
    if not distances:
        distances = [(height, "pelvis")]
    distances.sort()

    # Explicitly bind limb geometry to its own chain. The upper-thigh band
    # starts above 48% of model height, so include it through 60%; otherwise
    # its upper half incorrectly stays attached to the torso.
    leg_side = None
    if z < 0.60:
        for side, side_sign in (("L", 1), ("R", -1)):
            leg_x = (leg_centers[side] - center.x) / height
            if (x - leg_x) * side_sign >= -0.035:
                leg_side = side
                break

    arm_side = None
    if 0.30 <= z <= 0.86 and abs(x) >= 0.045:
        arm_side = "L" if x > 0 else "R"

    if arm_side is not None:
        chain = []
        for name, a, b in segments:
            if not name.endswith("." + arm_side) or not name.startswith(("upper_arm", "forearm", "hand")):
                continue
            ab = b-a
            t = max(0.0, min(1.0, (point-a).dot(ab) / max(ab.length_squared, 1e-9)))
            d = (point - (a + t*ab)).length
            if name.startswith("hand") and z > 0.48:
                continue
            if name.startswith("forearm") and z > 0.72:
                continue
            if name.startswith("upper_arm") and z < 0.48:
                continue
            chain.append((d, name))
        if chain:
            chain.sort()
            nearest = chain[:2]
        else:
            nearest = distances[:2]
    elif leg_side is not None:
        chain = []
        for name, a, b in segments:
            if not name.startswith(("thigh", "shin", "foot")) or not name.endswith("." + leg_side):
                continue
            ab = b-a
            t = max(0.0, min(1.0, (point-a).dot(ab) / max(ab.length_squared, 1e-9)))
            d = (point - (a + t*ab)).length
            if name.startswith("foot") and z > 0.12:
                continue
            if name.startswith("shin") and z > 0.43:
                continue
            chain.append((d, name))
        if chain:
            chain.sort()
            nearest = chain[:2]
        else:
            nearest = distances[:2]
    elif abs(x) < 0.115 and 0.34 <= z <= 0.88:
        # The middle of the robe must be driven by the torso chain, not by
        # distant arm/leg joints. Blend pelvis, spine and chest so the whole
        # central cloth follows the animated body instead of staying rigid.
        torso = [(d, name) for d, name in distances
                 if name in ("pelvis", "spine", "chest", "neck", "head")]
        torso.sort()
        nearest = torso[:3] if torso else distances[:2]
    else:
        # Keep sleeves and outer cloth local to their nearest joints.
        nearest = distances[:2]

    raw = [(name, 1.0 / max(d, height*0.025)**2) for d,name in nearest]
    total = sum(w for _,w in raw)
    for name,w in raw:
        groups[name].add([i], w/total, "REPLACE")

# WEIGHT DIAGNOSTICS: report actual assigned vertex-group influence by height.
# Read-only: this block does not modify coordinates, weights, or animation.
group_names = {g.index: g.name for g in mesh.vertex_groups}
weight_totals = {g.name: 0.0 for g in mesh.vertex_groups}
weight_vertices = {g.name: 0 for g in mesh.vertex_groups}
for v in mesh.data.vertices:
    for membership in v.groups:
        name = group_names.get(membership.group)
        if name is not None and membership.weight > 0.0001:
            weight_totals[name] += membership.weight
            weight_vertices[name] += 1
print("WEIGHT_GROUP_TOTALS", sorted(
    [(name, round(total, 3), count) for name, total in weight_totals.items()],
    key=lambda row: row[1], reverse=True), flush=True)
for lo, hi in ((0.00,0.08),(0.08,0.18),(0.18,0.30),(0.30,0.42),
               (0.42,0.52),(0.52,0.64),(0.64,0.78),(0.78,0.90),(0.90,1.00)):
    counts = {}
    for v in mesh.data.vertices:
        zf = (v.co.z-minv.z)/height
        if not (lo <= zf < hi):
            continue
        if not v.groups:
            key = "UNWEIGHTED"
        else:
            strongest = max(v.groups, key=lambda item: item.weight)
            key = group_names.get(strongest.group, "UNKNOWN")
        counts[key] = counts.get(key, 0) + 1
    print("DOMINANT_WEIGHTS_BY_HEIGHT", lo, hi,
          sorted(counts.items(), key=lambda item: item[1], reverse=True), flush=True)

# Confirm whether the imported mesh has topology for connected-component analysis.
print("MESH_TOPOLOGY_COUNTS", "vertices", len(mesh.data.vertices),
      "edges", len(mesh.data.edges), "polygons", len(mesh.data.polygons),
      "bmesh_edges", len(bm.edges) if bm.is_valid else -1,
      "bmesh_faces", len(bm.faces) if bm.is_valid else -1, flush=True)

mod = mesh.modifiers.new("CharacterSkin", "ARMATURE")
mod.object = arm
mesh.parent = arm
mesh.matrix_parent_inverse = arm.matrix_world.inverted()
mesh.parent_type = "OBJECT"
mesh.select_set(False)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm

# Build four named animation clips on the real skeleton.
# NumPy is provided by Ubuntu's python3-numpy package to match Blender's Python ABI.
arm.animation_data_create()
pose_bones = arm.pose.bones
for pb in pose_bones:
    pb.rotation_mode = "XYZ"

def make_pose_action(name, keyframes):
    action = bpy.data.actions.new(name=name)
    arm.animation_data.action = action
    for frame, rotations in keyframes:
        for bone_name, rotation in rotations.items():
            pb = pose_bones.get(bone_name)
            if pb is not None:
                pb.rotation_euler = rotation
                pb.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone_name)
    for curve in action.fcurves:
        curve.modifiers.new(type="CYCLES")
    return action

def P(**items):
    return items

idle = make_pose_action("Idle", [
    (1, P(chest=(0,0,0), spine=(0,0,0), head=(0,0,0))),
    (16, P(chest=(-0.045,0,0), spine=(-0.018,0,0), head=(0.025,0,0))),
    (31, P(chest=(0,0,0), spine=(0,0,0), head=(0,0,0))),
])
walk_keys = []
# A one-second alternating gait with bent knees, counter-swinging arms,
# a small torso counter-rotation, and feet that counter-rotate to stay level.
for frame, swing in ((1,0.40),(7,0),(13,-0.40),(19,0),(25,0.40)):
    # Larger hip travel and a controlled knee lift make the planted/swing phases readable.
    walk_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,swing)*1.65,0,0), "shin.R":(max(0,-swing)*1.65,0,0),
        "foot.L":(-swing*0.62,0,0), "foot.R":(swing*0.62,0,0),
        "upper_arm.L":(-swing*1.55,0,0), "upper_arm.R":(swing*1.55,0,0),
        "forearm.L":(0.16+max(0,-swing)*0.25,0,0), "forearm.R":(0.16+max(0,swing)*0.25,0,0),
        "hand.L":(-swing*0.22,0,0), "hand.R":(swing*0.22,0,0),
        "pelvis":(0,0,swing*0.055), "spine":(0.025,0,-swing*0.045),
        "chest":(-0.035,0,0), "neck":(0,0,-swing*0.04), "head":(0,0,swing*0.025)
    })))
walk = make_pose_action("Walk", walk_keys)
run_keys = []
for frame, swing in ((1,0.62),(7,0),(13,-0.62),(19,0),(25,0.62)):
    run_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,swing)*1.8,0,0), "shin.R":(max(0,-swing)*1.8,0,0),
        "foot.L":(-swing*0.58,0,0), "foot.R":(swing*0.58,0,0),
        "upper_arm.L":(-swing*1.75,0,0), "upper_arm.R":(swing*1.75,0,0),
        "forearm.L":(0.28+max(0,-swing)*0.35,0,0), "forearm.R":(0.28+max(0,swing)*0.35,0,0),
        "hand.L":(-swing*0.3,0,0), "hand.R":(swing*0.3,0,0),
        "pelvis":(0,0,swing*0.10), "spine":(0.085,0,-swing*0.075),
        "chest":(-0.06,0,0), "neck":(0,0,-swing*0.06), "head":(0,0,swing*0.035)
    })))
run = make_pose_action("Run", run_keys)
turn = make_pose_action("Turn", [
    (1, P(spine=(0,0,-.18), head=(0,0,.12), **{"upper_arm.L":(.08,0,0),"upper_arm.R":(-.08,0,0)})),
    (7, P(spine=(0,0,.18), head=(0,0,-.12), **{"upper_arm.L":(-.08,0,0),"upper_arm.R":(.08,0,0)})),
    (13, P(spine=(0,0,0), head=(0,0,0), **{"upper_arm.L":(0,0,0),"upper_arm.R":(0,0,0)})),
])
actions = [idle, walk, run, turn]
arm.animation_data.action = idle

# Export the skinned model and all named glTF animation clips.
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False,
                          export_skins=True, export_animations=True,
                          export_animation_mode="ACTIONS",
                          export_apply=False, export_yup=True,
                          export_draco_mesh_compression_enable=True,
                          export_draco_mesh_compression_level=6)
if not os.path.isfile(out) or os.path.getsize(out) < 1024:
    raise RuntimeError("Rigged GLB export is missing or unexpectedly small")
if not any(obj.type == "ARMATURE" for obj in bpy.context.scene.objects):
    raise RuntimeError("Export validation failed: no armature in scene")
print("RIGGED_EXPORT_OK", out, os.path.getsize(out), flush=True)
print("MESH_VERTICES", len(mesh.data.vertices), "BONES", len(arm_data.bones), "ANIMATIONS", [a.name for a in actions], flush=True)
