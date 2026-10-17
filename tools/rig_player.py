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

# Correct the ankle transition using the original rig's actual foot-bone pivot.
# The source weights let the foot bone influence vertices far above the ankle;
# this broad overlap can pull the lower-leg/boot cuff when the foot rotates.
for obj in skinned_meshes:
    arm_inverse = arm.matrix_world.inverted()
    for side, sign in (("L", 1), ("R", -1)):
        foot_bone = arm.data.bones[f"foot.{side}"]
        foot_group = obj.vertex_groups.get(f"foot.{side}")
        shin_group = obj.vertex_groups.get(f"shin.{side}")
        if foot_group is None or shin_group is None:
            raise RuntimeError(f"Missing foot/shin vertex groups for side {side}")
        ankle_z = foot_bone.head_local.z
        start_z = ankle_z + 0.015
        end_z = ankle_z + 0.115
        changed = 0
        moved_weight = 0.0
        for vertex in obj.data.vertices:
            point_arm = arm_inverse @ (obj.matrix_world @ vertex.co)
            if point_arm.x * sign < 0.04 or point_arm.z <= start_z:
                continue
            try:
                old_foot = foot_group.weight(vertex.index)
            except RuntimeError:
                continue
            if old_foot <= 0.0001:
                continue
            t = max(0.0, min(1.0, (point_arm.z - start_z) / (end_z - start_z)))
            smooth = t * t * (3.0 - 2.0 * t)
            new_foot = old_foot * (1.0 - smooth)
            transfer = old_foot - new_foot
            if transfer <= 0.0001:
                continue
            try:
                old_shin = shin_group.weight(vertex.index)
            except RuntimeError:
                old_shin = 0.0
            if new_foot > 0.0001:
                foot_group.add([vertex.index], new_foot, "REPLACE")
            else:
                foot_group.remove([vertex.index])
            shin_group.add([vertex.index], old_shin + transfer, "REPLACE")
            changed += 1
            moved_weight += transfer
        print("ANKLE_WEIGHT_FIX", side, "PIVOT_Z", round(ankle_z,5),
              "BAND", (round(start_z,5),round(end_z,5)),
              "VERTICES", changed, "TRANSFERRED_WEIGHT", round(moved_weight,2), flush=True)

# Diagnose foot/toe regions from the vertex membership data directly.
# VertexGroup.weight() raises for unassigned vertices, so read vertex.groups instead.
for obj in skinned_meshes:
    arm_inverse = arm.matrix_world.inverted()
    for side in ("L", "R"):
        bone = arm.data.bones[f"foot.{side}"]
        foot_group = obj.vertex_groups.get(f"foot.{side}")
        shin_group = obj.vertex_groups.get(f"shin.{side}")
        if foot_group is None or shin_group is None:
            raise RuntimeError(f"Missing diagnostic groups for {side}")
        axis = bone.tail_local - bone.head_local
        length = axis.length
        if length < 1e-6:
            print("FOOT_DIAGNOSTIC", side, "INVALID_BONE_LENGTH", flush=True)
            continue
        axis.normalize()
        foot_rows = []
        all_projection = []
        for vertex in obj.data.vertices:
            point = arm_inverse @ (obj.matrix_world @ vertex.co)
            along = (point - bone.head_local).dot(axis) / length
            all_projection.append(along)
            fw = 0.0
            sw = 0.0
            for membership in vertex.groups:
                if membership.group == foot_group.index:
                    fw = membership.weight
                elif membership.group == shin_group.index:
                    sw = membership.weight
            if fw > 0.01:
                foot_rows.append((along, fw, sw, point.copy(), vertex.index))
        foot_rows.sort(key=lambda r: r[0])
        projections = np.array([r[0] for r in foot_rows], dtype=float) if foot_rows else np.array([])
        if len(projections):
            quantiles = [round(float(x), 3) for x in np.quantile(projections, [0, .1, .25, .5, .75, .9, 1])]
            extremes = foot_rows[:4] + foot_rows[-4:]
        else:
            quantiles = []
            extremes = []
        allp = np.array(all_projection, dtype=float)
        print("FOOT_DIAGNOSTIC", side,
              "HEAD", tuple(round(v,4) for v in bone.head_local),
              "TAIL", tuple(round(v,4) for v in bone.tail_local),
              "ALL_ALONG_RANGE", (round(float(allp.min()),3), round(float(allp.max()),3)),
              "FOOT_WEIGHTED_VERTICES", len(foot_rows),
              "FOOT_ALONG_QUANTILES", quantiles,
              "FOOT_EXTREMES", [(r[4],round(r[0],3),round(r[1],3),round(r[2],3),
                                  tuple(round(v,3) for v in r[3])) for r in extremes],
              flush=True)

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
