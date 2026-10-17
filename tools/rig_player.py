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

# Align each foot from its toe direction, not PCA's ambiguous principal axis.
# The previous PCA included robe-hem vertices and could select the shoe width.
height0 = maxv.z - minv.z
if height0 > 0:
    for side_sign in (1, -1):
        ankle_x = center.x + side_sign * height0 * 0.035
        ankle_y = center.y
        ankle_z = minv.z + height0 * 0.075

        # Keep only the low vertices in a tight box around this ankle.
        # This excludes the wide robe hem and the opposite shoe.
        foot_vertices = [
            v for v in mesh.data.vertices
            if (v.co.z - minv.z) / height0 < 0.145
            and abs(v.co.x - ankle_x) < height0 * 0.052
            and abs(v.co.x - center.x) > height0 * 0.018
            and v.co.y > center.y - height0 * 0.045
        ]
        if len(foot_vertices) < 30:
            print("FOOT_ALIGNMENT_SKIP", side_sign, len(foot_vertices), flush=True)
            continue

        # The toe is the forward (+Y) end of the shoe. Estimate its lateral
        # offset from the ankle using the foremost 12% of the selected vertices.
        # Center the shoe mesh under its own trouser-leg bone chain.
        # Preserve shoe width and toe direction; translate only its X center.
        shoe_center_x = sum(v.co.x for v in foot_vertices) / len(foot_vertices)
        shoe_shift_x = ankle_x - shoe_center_x
        for v in foot_vertices:
            v.co.x += shoe_shift_x

        ys = sorted(v.co.y for v in foot_vertices)
        toe_threshold = ys[max(0, int(len(ys) * 0.88) - 1)]
        toe_vertices = [v for v in foot_vertices if v.co.y >= toe_threshold]
        toe_x = sum(v.co.x for v in toe_vertices) / len(toe_vertices)
        toe_y = sum(v.co.y for v in toe_vertices) / len(toe_vertices)
        # Rotate around the shoe's own center, not the ankle pivot.
        # Rotating around the ankle shifts the shoe sideways because its
        # geometry center is forward of the ankle, undoing trouser alignment.
        shoe_pivot_x = sum(v.co.x for v in foot_vertices) / len(foot_vertices)
        shoe_pivot_y = sum(v.co.y for v in foot_vertices) / len(foot_vertices)
        dx, dy = toe_x - shoe_pivot_x, toe_y - shoe_pivot_y
        # The toe must point along character-forward (+Y).
        delta = -math.atan2(dx, dy)
        delta = max(-math.radians(40), min(math.radians(40), delta))
        ca, sa = math.cos(delta), math.sin(delta)
        for v in foot_vertices:
            x, y = v.co.x - shoe_pivot_x, v.co.y - shoe_pivot_y
            v.co.x = shoe_pivot_x + x * ca - y * sa
            v.co.y = shoe_pivot_y + x * sa + y * ca
        # Keep the shoe center directly beneath its own trouser leg.
        final_center_x = sum(v.co.x for v in foot_vertices) / len(foot_vertices)
        for v in foot_vertices:
            v.co.x += ankle_x - final_center_x
        print("FOOT_TOE_ALIGNMENT", side_sign, round(math.degrees(delta), 2),
              "vertices", len(foot_vertices), "toe_offset", round(dx / height0, 4), "center_shift", round(shoe_shift_x / height0, 4), flush=True)
    mesh.data.update()

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
      # Keep each leg chain on one straight vertical centerline. The foot
      # extends forward on Y; left/right separation comes only from X.
      (f"thigh.{side}", p(sign*0.035,0.48), p(sign*0.035,0.27), "pelvis"),
      (f"shin.{side}", p(sign*0.035,0.27), p(sign*0.035,0.07), f"thigh.{side}"),
      # Foot bone follows the foot's long axis instead of pointing down.
      (f"foot.{side}", p(sign*0.035,0.07), p(sign*0.035,0.055,0.16), f"shin.{side}"),
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
            side_sign = 1 if name.endswith(".L") else -1
            if x * side_sign < 0.012: continue
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
for frame, swing in ((1,0.14),(7,0),(13,-0.14),(19,0),(25,0.14)):
    # Knees flex on the forward swing; feet counter-rotate to stay level.
    walk_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,swing)*3.0,0,0), "shin.R":(max(0,-swing)*3.0,0,0),
        "foot.L":(-swing*0.42,0,0), "foot.R":(swing*0.42,0,0),
        "upper_arm.L":(-swing*0.48,0,0), "upper_arm.R":(swing*0.48,0,0),
        "forearm.L":(0.06,0,0), "forearm.R":(0.06,0,0),
        "pelvis":(0,0,swing*0.018), "spine":(0.008,0,-swing*0.018),
        "chest":(-0.008,0,0)
    })))
walk = make_pose_action("Walk", walk_keys)
run_keys = []
for frame, swing in ((1,0.28),(7,0),(13,-0.28),(19,0),(25,0.28)):
    run_keys.append((frame, P(**{
        "thigh.L":(swing,0,0), "thigh.R":(-swing,0,0),
        "shin.L":(max(0,swing)*2.5,0,0), "shin.R":(max(0,-swing)*2.5,0,0),
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
print("MESH_VERTICES", len(mesh.data.vertices), "BONES", len(arm_data.bones), "ANIMATIONS", [a.name for a in actions], flush=True)
