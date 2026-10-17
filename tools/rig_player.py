import bpy, math, os, sys
from mathutils import Vector

try:
    import numpy  # noqa: F401
except ImportError as exc:
    raise RuntimeError("NumPy is missing from Blender Python; install the matching NumPy wheel in the workflow") from exc

src = os.environ.get("INPUT_GLB", "player-rigged-beautified.glb")
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

# The input is already rigged. Preserve each mesh's world transform, then remove
# its old skin modifier, parent and groups before rebuilding a clean, extended rig.
old_armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
for obj in meshes:
    world = obj.matrix_world.copy()
    for modifier in list(obj.modifiers):
        if modifier.type == "ARMATURE":
            obj.modifiers.remove(modifier)
    obj.parent = None
    obj.matrix_world = world
for old_arm in old_armatures:
    bpy.data.objects.remove(old_arm, do_unlink=True)

# Bake imported transforms into the mesh so the new armature and weights share one space.
for obj in meshes:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.select_set(False)

# Combine the original geometry without changing its shape or vertex positions.
bpy.ops.object.select_all(action="DESELECT")
for obj in meshes: obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
mesh = bpy.context.object
mesh.name = "OriginalCharacterMesh"

coords = [v.co.copy() for v in mesh.data.vertices]
minv = Vector((min(v.x for v in coords), min(v.y for v in coords), min(v.z for v in coords)))
maxv = Vector((max(v.x for v in coords), max(v.y for v in coords), max(v.z for v in coords)))
center = (minv + maxv) * 0.5

# Establish dimensions before any region/rig calculations.
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
      # A slightly wider, symmetric neutral stance keeps the knees under the hips
      # and the feet parallel instead of letting both legs collapse toward center.
      (f"thigh.{side}", p(sign*0.065,0.48), p(sign*0.075,0.27), "pelvis"),
      (f"shin.{side}", p(sign*0.075,0.27), p(sign*0.065,0.07), f"thigh.{side}"),
      (f"foot.{side}", p(sign*0.065,0.07), p(sign*0.065,0.025,0.07), f"shin.{side}"),
    ]
    # Individually skinned toes, placed across the front of each foot.
    # The big toe is medial; the little toe is lateral on both mirrored feet.
    toe_specs = [
      ("big", -0.023, 0.018),
      ("02", -0.010, 0.009),
      ("03",  0.003, 0.000),
      ("04",  0.016, -0.009),
      ("05",  0.028, -0.018),
    ]
    for toe, offset_x, offset_z in toe_specs:
        root = p(sign*(0.065+offset_x), 0.038+offset_z, 0.065)
        middle = p(sign*(0.065+offset_x*1.05), 0.034+offset_z, 0.112)
        tip = p(sign*(0.065+offset_x*1.10), 0.030+offset_z, 0.151)
        bones.append((f"toe.{toe}.01.{side}", root, middle, f"foot.{side}"))
        bones.append((f"toe.{toe}.02.{side}", middle, tip, f"toe.{toe}.01.{side}"))
    # Five individually skinned fingers per hand, with three connected phalanges.
    finger_specs = [
      ("thumb", 0.032, 0.025, (0.032,0.027,0.022), 0.010),
      ("index", 0.020, -0.010, (0.030,0.027,0.023), 0.004),
      ("middle", 0.006, -0.006, (0.032,0.029,0.025), 0.000),
      ("ring", -0.009, 0.000, (0.030,0.027,0.023), -0.003),
      ("pinky", -0.023, 0.008, (0.026,0.023,0.020), -0.007),
    ]
    for digit, base_x, base_y, lengths, spread in finger_specs:
        points = [
            p(sign*(0.20+base_x), 0.365, base_y),
            p(sign*(0.20+base_x+spread*0.35), 0.365-lengths[0], base_y+0.004),
            p(sign*(0.20+base_x+spread*0.65), 0.365-lengths[0]-lengths[1], base_y+0.008),
            p(sign*(0.20+base_x+spread), 0.365-sum(lengths), base_y+0.012),
        ]
        parents = [f"hand.{side}", f"{digit}.01.{side}", f"{digit}.02.{side}"]
        for segment in range(3):
            bones.append((f"{digit}.{segment+1:02d}.{side}", points[segment], points[segment+1], parents[segment]))

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

# Region-aware smooth skinning. Remove source groups so old hand-only weights
# cannot compete with the new per-finger weights.
while mesh.vertex_groups:
    mesh.vertex_groups.remove(mesh.vertex_groups[0])

# A single-piece robe must not inherit leg weights across the whole skirt.
segments = [(name, Vector(h), Vector(t)) for name,h,t,parent in bones if name != "root"]
groups = {name: mesh.vertex_groups.new(name=name) for name,_,_ in segments}
for i, v in enumerate(mesh.data.vertices):
    point = v.co
    z = (point.z - minv.z) / height
    x = (point.x - center.x) / height
    distances = []
    for name, a, b in segments:
        # Keep upper-body cloth attached to the torso instead of the moving legs.
        if name.startswith("thigh") and z > 0.64: continue
        if name.startswith("shin") and z > 0.40: continue
        if name.startswith("foot") and z > 0.19: continue
        # Keep the shin out of the forefoot and toes; the ankle is the boundary.
        if name.startswith("shin") and z < 0.115: continue
        # Toe bones only affect the low, forward part of their own foot.
        if name.startswith("toe."):
            side = 1 if name.endswith(".L") else -1
            y = (point.y - center.y) / height
            if z > 0.105 or y < 0.045 or x * side < 0.025: continue
        # The foot bone should not pull the separated toe tips backward.
        if name.startswith("foot"):
            y = (point.y - center.y) / height
            if y > 0.105 and z < 0.095: continue
        # Arms should affect sleeves and hands, not the chest or central robe.
        if name.startswith(("upper_arm", "forearm", "hand")):
            side = 1 if name.endswith(".L") else -1
            if z < 0.27 or x * side < 0.045: continue
        # Finger bones only influence the hand-tip region on their own side.
        if name.startswith(("thumb.", "index.", "middle.", "ring.", "pinky.")):
            side = 1 if name.endswith(".L") else -1
            if z > 0.405 or x * side < 0.135: continue
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
    nearest = distances[:4]
    raw = [(name, 1.0 / max(d, height*0.018)**2) for d,name in nearest]
    total = sum(w for _,w in raw)
    for name,w in raw:
        groups[name].add([i], w/total, "REPLACE")

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
    (1, P(chest=(0,0,0), head=(0,0,0))),
    (16, P(chest=(-0.025,0,0), head=(0.015,0,0))),
    (31, P(chest=(0,0,0), head=(0,0,0))),
])
walk_keys = []
# A one-second alternating gait with bent knees, counter-swinging arms,
# a small torso counter-rotation, and feet that counter-rotate to stay level.
for frame, swing in ((1,0.22),(7,0),(13,-0.22),(19,0),(25,0.22)):
    # Knees flex on the forward swing; feet counter-rotate to stay level.
    walk_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,swing)*0.62,0,0), "shin.R":(max(0,-swing)*0.62,0,0),
        "foot.L":(-swing*0.42,0,0), "foot.R":(swing*0.42,0,0),
        "upper_arm.L":(-swing*0.48,0,0), "upper_arm.R":(swing*0.48,0,0),
        "forearm.L":(0.06,0,0), "forearm.R":(0.06,0,0),
        "pelvis":(0,0,swing*0.018), "spine":(0.008,0,-swing*0.018),
        "chest":(-0.008,0,0)
    })))
walk = make_pose_action("Walk", walk_keys)
run_keys = []
for frame, swing in ((1,0.42),(7,0),(13,-0.42),(19,0),(25,0.42)):
    run_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,swing)*0.88,0,0), "shin.R":(max(0,-swing)*0.88,0,0),
        "foot.L":(-swing*0.38,0,0), "foot.R":(swing*0.38,0,0),
        "upper_arm.L":(-swing*0.92,0,0), "upper_arm.R":(swing*0.92,0,0),
        "forearm.L":(0.22,0,0), "forearm.R":(0.22,0,0),
        "pelvis":(0,0,swing*0.055), "spine":(0.055,0,-swing*0.04),
        "chest":(-0.035,0,0)
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
finger_bones = [b.name for b in arm_data.bones if b.name.startswith(("thumb.", "index.", "middle.", "ring.", "pinky."))]
toe_bones = [b.name for b in arm_data.bones if b.name.startswith("toe.")]
if len(finger_bones) != 30:
    raise RuntimeError(f"Finger rig validation failed: expected 30 finger bones, found {len(finger_bones)}")
if len(toe_bones) != 20:
    raise RuntimeError(f"Toe rig validation failed: expected 20 toe bones, found {len(toe_bones)}")
print("MESH_VERTICES", len(mesh.data.vertices), "BONES", len(arm_data.bones), "FINGER_BONES", len(finger_bones), "TOE_BONES", len(toe_bones), "ANIMATIONS", [a.name for a in actions], flush=True)
