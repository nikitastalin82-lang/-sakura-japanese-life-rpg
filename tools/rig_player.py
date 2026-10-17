import bpy, os
from mathutils import Vector

src = os.environ.get("INPUT_GLB", "player-rigged-beautified.glb")
out = os.environ.get("OUTPUT_GLB", "public/models/player-rigged.glb")
os.makedirs(os.path.dirname(out), exist_ok=True)

# IMPORTANT: the source GLB already contains a working 18-bone skin.
# Keep its original armature, inverse bind matrices, mesh, vertex groups and
# armature modifiers. Rebuilding weights from guessed positions caused the
# fingers/toes to stretch because those weights did not match the real mesh.

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.import_scene.gltf(filepath=src)
except BaseException as exc:
    print("GLB_IMPORT_FAILED:", repr(exc), flush=True)
    os._exit(1)

armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if len(armatures) != 1:
    raise RuntimeError(f"Expected the source GLB's one original armature, found {len(armatures)}")
if not meshes:
    raise RuntimeError("GLB contains no mesh objects")

arm = armatures[0]
if len(arm.data.bones) < 18:
    raise RuntimeError(f"Source skeleton is incomplete: only {len(arm.data.bones)} bones")
for required in ("root", "pelvis", "spine", "chest", "head",
                 "upper_arm.L", "forearm.L", "hand.L",
                 "upper_arm.R", "forearm.R", "hand.R",
                 "thigh.L", "shin.L", "foot.L",
                 "thigh.R", "shin.R", "foot.R"):
    if arm.data.bones.get(required) is None:
        raise RuntimeError(f"Source skeleton is missing required bone: {required}")

# Verify the original skinning remains connected. Do not clear or replace groups.
skinned_meshes = []
for mesh in meshes:
    has_armature_modifier = any(m.type == "ARMATURE" and m.object == arm for m in mesh.modifiers)
    is_parented = mesh.parent == arm
    has_weights = len(mesh.vertex_groups) > 0
    if has_armature_modifier and has_weights:
        skinned_meshes.append(mesh)
if not skinned_meshes:
    raise RuntimeError("Original mesh weights/armature connection were not preserved")

# Diagnostics: inspect the original foot/ankle skinning and disconnected mesh islands.
for obj in skinned_meshes:
    verts = obj.data.vertices
    print("DIAG_MESH", obj.name, "VERTICES", len(verts), "GROUPS", len(obj.vertex_groups), flush=True)
    group_by_index = {g.index: g.name for g in obj.vertex_groups}
    for group in obj.vertex_groups:
        if group.name.lower().startswith(("foot", "shin", "thigh", "toe")):
            weighted = []
            total_weight = 0.0
            for v in verts:
                for a in v.groups:
                    if a.group == group.index and a.weight > 0.02:
                        weighted.append(v.co)
                        total_weight += a.weight
            if weighted:
                xs = [v.x for v in weighted]; ys = [v.y for v in weighted]; zs = [v.z for v in weighted]
                print("DIAG_GROUP", group.name, "COUNT", len(weighted), "WEIGHT_SUM", round(total_weight,2),
                      "BOUNDS", tuple(round(min(a),4) for a in (xs,ys,zs)),
                      tuple(round(max(a),4) for a in (xs,ys,zs)), flush=True)
            else:
                print("DIAG_GROUP", group.name, "COUNT", 0, flush=True)

    # Union-find over polygon edges reveals detached shoe/sole/toe geometry islands.
    parent = list(range(len(verts)))
    rank = bytearray(len(verts))
    def find_root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    def join_vertices(a,b):
        ra, rb = find_root(a), find_root(b)
        if ra == rb: return
        if rank[ra] < rank[rb]: ra,rb = rb,ra
        parent[rb] = ra
        if rank[ra] == rank[rb]: rank[ra] += 1
    for poly in obj.data.polygons:
        ids = poly.vertices
        for k in range(1, len(ids)):
            join_vertices(ids[0], ids[k])
    components = {}
    for v in verts:
        root = find_root(v.index)
        components.setdefault(root, []).append(v.index)
    major = sorted((ids for ids in components.values() if len(ids) >= 30), key=len, reverse=True)
    print("DIAG_COMPONENTS", "TOTAL", len(components), "OVER_30_VERTS", len(major), flush=True)
    for ci, ids in enumerate(major[:35]):
        points = [verts[i].co for i in ids]
        xs = [v.x for v in points]; ys = [v.y for v in points]; zs = [v.z for v in points]
        sums = {}
        for vi in ids:
            for a in verts[vi].groups:
                name = group_by_index.get(a.group, "")
                if name: sums[name] = sums.get(name, 0.0) + a.weight
        dominant = sorted(sums.items(), key=lambda x:x[1], reverse=True)[:5]
        print("DIAG_ISLAND", ci, "VERTS", len(ids),
              "BOUNDS", tuple(round(min(a),4) for a in (xs,ys,zs)),
              tuple(round(max(a),4) for a in (xs,ys,zs)),
              "GROUPS", [(n,round(w,1)) for n,w in dominant], flush=True)


# Compare skin weights at coincident triangle-soup vertices. These duplicates
# should deform identically across polygon boundaries, including UV seams.
for obj in skinned_meshes:
    buckets = {}
    for v in obj.data.vertices:
        key = (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
        weights = {a.group: a.weight for a in v.groups}
        item = buckets.setdefault(key, {"ids": [], "sum": {}, "count": 0, "minmax": {}})
        item["ids"].append(v.index)
        item["count"] += 1
        for gi, w in weights.items():
            item["sum"][gi] = item["sum"].get(gi, 0.0) + w
            lo, hi = item["minmax"].get(gi, (w,w))
            item["minmax"][gi] = (min(lo,w), max(hi,w))
    repeated = [v for v in buckets.values() if v["count"] > 1]
    mismatched = []
    for item in repeated:
        divergence = max((hi-lo for lo,hi in item["minmax"].values()), default=0.0)
        if divergence > 0.05:
            mismatched.append((item, divergence))
    print("DIAG_DUPLICATE_POSITIONS", "UNIQUE", len(buckets), "REPEATED_GROUPS", len(repeated),
          "VERTICES_IN_REPEATS", sum(x["count"] for x in repeated),
          "WEIGHT_MISMATCH_GROUPS", len(mismatched), flush=True)
    for item, divergence in sorted(mismatched, key=lambda x:x[1], reverse=True)[:20]:
        avg = {group_by_index.get(gi,str(gi)): round(w/item["count"],3) for gi,w in item["sum"].items()}
        print("DIAG_WEIGHT_SEAM", "COUNT", item["count"], "MAX_DELTA", round(divergence,3),
              "AVERAGE", avg, flush=True)

# Create animation clips on the original bones. Fingers and toes remain part
# of their correctly weighted original hand/foot regions instead of being
# assigned speculative extra bones that stretch the mesh.
arm.animation_data_create()
pose_bones = arm.pose.bones
for pb in pose_bones:
    pb.rotation_mode = "XYZ"

def make_action(name, keyframes):
    action = bpy.data.actions.new(name=name)
    arm.animation_data.action = action
    for frame, rotations in keyframes:
        for pb in pose_bones:
            pb.rotation_euler = (0.0, 0.0, 0.0)
        for bone_name, rotation in rotations.items():
            pb = pose_bones.get(bone_name)
            if pb is not None:
                pb.rotation_euler = rotation
                pb.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone_name)
    for curve in action.fcurves:
        curve.modifiers.new(type="CYCLES")
    return action

idle = make_action("Idle", [
    (1, {"chest": (0,0,0), "head": (0,0,0)}),
    (16, {"chest": (-0.018,0,0), "head": (0.012,0,0)}),
    (31, {"chest": (0,0,0), "head": (0,0,0)}),
])

walk_keys = []
for frame, swing in ((1,0.22),(7,0),(13,-0.22),(19,0),(25,0.22)):
    walk_keys.append((frame, {
        "thigh.L": (swing,0,0), "thigh.R": (-swing,0,0),
        "shin.L": (max(0,swing)*0.52,0,0),
        "shin.R": (max(0,-swing)*0.52,0,0),
        "foot.L": (-swing*0.30,0,0), "foot.R": (swing*0.30,0,0),
        "upper_arm.L": (-swing*0.42,0,0),
        "upper_arm.R": (swing*0.42,0,0),
        "forearm.L": (0.045,0,0), "forearm.R": (0.045,0,0),
        "pelvis": (0,0,swing*0.012), "spine": (0.006,0,-swing*0.012),
        "chest": (-0.006,0,0)
    }))
walk = make_action("Walk", walk_keys)

run_keys = []
for frame, swing in ((1,0.38),(7,0),(13,-0.38),(19,0),(25,0.38)):
    run_keys.append((frame, {
        "thigh.L": (swing,0,0), "thigh.R": (-swing,0,0),
        "shin.L": (max(0,swing)*0.72,0,0),
        "shin.R": (max(0,-swing)*0.72,0,0),
        "foot.L": (-swing*0.28,0,0), "foot.R": (swing*0.28,0,0),
        "upper_arm.L": (-swing*0.72,0,0),
        "upper_arm.R": (swing*0.72,0,0),
        "forearm.L": (0.16,0,0), "forearm.R": (0.16,0,0),
        "pelvis": (0,0,swing*0.035), "spine": (0.035,0,-swing*0.03),
        "chest": (-0.022,0,0)
    }))
run = make_action("Run", run_keys)

turn = make_action("Turn", [
    (1, {"spine": (0,0,-0.16), "head": (0,0,0.10),
         "upper_arm.L": (0.06,0,0), "upper_arm.R": (-0.06,0,0)}),
    (7, {"spine": (0,0,0.16), "head": (0,0,-0.10),
         "upper_arm.L": (-0.06,0,0), "upper_arm.R": (0.06,0,0)}),
    (13, {"spine": (0,0,0), "head": (0,0,0),
          "upper_arm.L": (0,0,0), "upper_arm.R": (0,0,0)}),
])
actions = [idle, walk, run, turn]
arm.animation_data.action = idle

bpy.ops.object.select_all(action="DESELECT")
for obj in bpy.context.scene.objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = arm

bpy.ops.export_scene.gltf(
    filepath=out, export_format="GLB", use_selection=False,
    export_skins=True, export_animations=True,
    export_animation_mode="ACTIONS", export_apply=False,
    export_yup=True, export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=6
)
if not os.path.isfile(out) or os.path.getsize(out) < 1024:
    raise RuntimeError("Rigged GLB export is missing or unexpectedly small")
print("RIGGED_EXPORT_OK", out, os.path.getsize(out), flush=True)
print("PRESERVED_SOURCE_BONES", len(arm.data.bones), flush=True)
print("PRESERVED_SKINNED_MESHES", len(skinned_meshes), flush=True)
print("PRESERVED_VERTEX_GROUPS", sum(len(m.vertex_groups) for m in skinned_meshes), flush=True)
print("ANIMATIONS", [a.name for a in actions], flush=True)
