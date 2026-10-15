import bpy, math, os, sys
from mathutils import Vector

try:
    import numpy  # noqa: F401
except ImportError as exc:
    raise RuntimeError("NumPy is missing from Blender Python; install the matching NumPy wheel in the workflow") from exc

src = os.environ.get("INPUT_GLB", "20261015073811_7513e2ed.glb")
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
# Blender uses Z-up internally. The glTF importer converts the original Y-up
# character into Blender coordinates, so the character's vertical axis here is Z.
height = maxv.z - minv.z
if height <= 0: raise RuntimeError("Character has no vertical height on Blender Z axis")

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
      (f"thigh.{side}", p(sign*0.045,0.48), p(sign*0.05,0.27), "pelvis"),
      (f"shin.{side}", p(sign*0.05,0.27), p(sign*0.05,0.07), f"thigh.{side}"),
      (f"foot.{side}", p(sign*0.05,0.07), p(sign*0.05,0.025,0.07), f"shin.{side}"),
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

# Smooth distance-based skinning is robust on this single-piece, watertight character mesh.
segments = [(name, Vector(h), Vector(t)) for name,h,t,parent in bones if name != "root"]
groups = {name: mesh.vertex_groups.new(name=name) for name,_,_ in segments}
for i, v in enumerate(mesh.data.vertices):
    point = v.co
    distances = []
    for name, a, b in segments:
        ab = b-a
        t = max(0.0, min(1.0, (point-a).dot(ab) / max(ab.length_squared, 1e-9)))
        d = (point - (a + t*ab)).length
        distances.append((d, name))
    distances.sort()
    nearest = distances[:4]
    raw = [(name, 1.0 / max(d, height*0.012)**2) for d,name in nearest]
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
for frame, swing in ((1,.38),(9,0),(17,-.38),(25,0),(33,.38)):
    walk_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,-swing)*.75,0,0), "shin.R":(max(0,swing)*.75,0,0),
        "upper_arm.L":(-swing*.75,0,0), "upper_arm.R":(swing*.75,0,0),
        "forearm.L":(.08,0,0), "forearm.R":(.08,0,0), "spine":(.025,0,0)
    })))
walk = make_pose_action("Walk", walk_keys)
run_keys = []
for frame, swing in ((1,.68),(7,0),(13,-.68),(19,0),(25,.68)):
    run_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,-swing)*1.15,0,0), "shin.R":(max(0,swing)*1.15,0,0),
        "upper_arm.L":(-swing,0,0), "upper_arm.R":(swing,0,0),
        "forearm.L":(.28,0,0), "forearm.R":(.28,0,0), "spine":(.07,0,0)
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
                          export_apply=False, export_yup=True)
if not os.path.isfile(out) or os.path.getsize(out) < 1024:
    raise RuntimeError("Rigged GLB export is missing or unexpectedly small")
if not any(obj.type == "ARMATURE" for obj in bpy.context.scene.objects):
    raise RuntimeError("Export validation failed: no armature in scene")
print("RIGGED_EXPORT_OK", out, os.path.getsize(out), flush=True)
print("MESH_VERTICES", len(mesh.data.vertices), "BONES", len(arm_data.bones), "ANIMATIONS", [a.name for a in actions], flush=True)
