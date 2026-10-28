"""C.H.A.M.B.E.R stage clips, rendered in Blender.

Clips (24 fps) chain seamlessly through two shared states:
  HUB      man stands relaxed holding the frisbee; dog stands at its start spot
           facing the field (-Y).
  ARRIVED  dog sits right in front of the man, frisbee in its mouth, facing him.

  throw_s / throw_m / throw_l   HUB -> ARRIVED   (short / medium / long throw)
  pet                           ARRIVED -> HUB   (kneel, pet, take it, stand up)
  finish                        HUB -> rest      (dog sits, he kneels, puts the
                                                  frisbee down and pets the dog)

Both characters face -Y; the camera is on the -X side, so -Y is screen right.
usage: python scene2.py -- <human.glb> <dog.glb> <out_dir> <clip> [still frames]
"""
import bpy, sys, math, os
from mathutils import Vector, Quaternion, Matrix

argv = sys.argv[sys.argv.index("--") + 1:]
HUMAN, DOG, OUT, CLIP = argv[:4]
STILLS = [int(x) for x in argv[4].split(",")] if len(argv) > 4 else None
RES = tuple(int(x) for x in os.environ.get("RES", "900x225").split("x"))
SAMPLES = int(os.environ.get("SAMPLES", "16"))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
sc = bpy.context.scene
sc.render.fps = 24
A = bpy.data.actions


def ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def import_glb(path, ctl_name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in list(new):
        if o.name.startswith("Icosphere"):
            new.remove(o); bpy.data.objects.remove(o)
    ctl = bpy.data.objects.new(ctl_name, None)
    sc.collection.objects.link(ctl)
    for o in new:
        if o.parent is None:
            o.parent = ctl
    return ctl, [o for o in new if o.type == "ARMATURE"][0], new


hctl, harm, hobjs = import_glb(HUMAN, "HumanCtl")
dctl, darm, dobjs = import_glb(DOG, "DogCtl")
for o in dobjs:
    if o.name.startswith("Lamp"):
        o.hide_render = True
dctl.scale = (0.085,) * 3
P = harm.pose.bones
MW = harm.matrix_world


def vl_update():
    bpy.context.view_layer.update()


def nla_reset(arm):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    for t in list(ad.nla_tracks):
        ad.nla_tracks.remove(t)
    return ad


def strip(ad, action, start, a0, a1, repeat=1.0, blend=4, hold=False, name=None):
    tr = ad.nla_tracks.new()
    s = tr.strips.new(name or (action.name + str(start)), int(start), action)
    s.action_frame_start, s.action_frame_end = a0, a1
    s.repeat = repeat
    s.frame_end = start + (a1 - a0) * repeat
    s.blend_in = s.blend_out = blend
    s.use_auto_blend = False
    s.extrapolation = "HOLD_FORWARD" if hold else "NOTHING"
    return s


def bone_w(n, tail=False):
    return MW @ (P[n].tail if tail else P[n].head)


def set_world(n, M):
    P[n].matrix = MW.inverted() @ M
    vl_update()


def rotate_about(n, R, pivot):
    M = MW @ P[n].matrix
    T = Matrix.Translation(pivot) @ R.to_matrix().to_4x4() @ Matrix.Translation(-pivot)
    set_world(n, T @ M)


def dbone(n, tail=False):
    pb = darm.pose.bones[n]
    return darm.matrix_world @ (pb.tail if tail else pb.head)


def mouth_point():
    return dbone("SnoutUpper_metarig", True) * 0.4 + dbone("SnoutLower_metarig", True) * 0.6


def ears_point():
    return (dbone("Ear.L_metarig") + dbone("Ear.R_metarig")) / 2


def hand_point():
    m = MW @ P["RightHand_037"].matrix
    return m @ Vector((0, 0.09 / MW.to_scale()[0], 0))


# ====================== the man's relaxed pose ======================
# (recorded throw for the throw only; relaxed stance otherwise)
had = nla_reset(harm)
A_START, A_END = 6, 58
strip(had, A["Animation"], 0, 0, 62, blend=0, hold=True)
sc.frame_set(A_START); q_start = {pb.name: pb.rotation_quaternion.copy() for pb in P}
sc.frame_set(A_END); q_end = {pb.name: pb.rotation_quaternion.copy() for pb in P}
sc.frame_set(58)
snap = {pb.name: (pb.location.copy(), pb.rotation_quaternion.copy(), pb.scale.copy()) for pb in P}
nla_reset(harm)
for pb in P:
    pb.rotation_mode = "QUATERNION"
    pb.location, pb.rotation_quaternion, pb.scale = snap[pb.name]
vl_update()
RIGHT = Vector((-1, 0, 0))                       # his right side (he faces -Y)
hip_c = (bone_w("LeftUpLeg_057") + bone_w("RightUpLeg_062")) / 2
for side, sx in (("Left", 1), ("Right", -1)):
    up = f"{side}UpLeg_0{'57' if side == 'Left' else '62'}"
    ft = f"{side}Foot_0{'59' if side == 'Left' else '64'}"
    lg = f"{side}Leg_0{'58' if side == 'Left' else '63'}"
    H, F = bone_w(up), bone_w(ft)
    foot_rot = (MW @ P[ft].matrix).to_quaternion()
    want = Vector((hip_c.x + sx * 0.30, F.y * 0.6 + H.y * 0.4, F.z))
    rotate_about(up, (F - H).normalized().rotation_difference((want - H).normalized()), H)
    a = (bone_w(ft) - H).normalized(); k = bone_w(lg) - H
    k_perp = (k - a * k.dot(a)).normalized()
    d = Vector((sx * 0.12, -1.0, 0.0)); d_perp = (d - a * d.dot(a)).normalized()
    rotate_about(up, Quaternion(a, math.atan2(a.dot(k_perp.cross(d_perp)), k_perp.dot(d_perp))), H)
    set_world(ft, Matrix.Translation(bone_w(ft)) @ foot_rot.to_matrix().to_4x4() @
              Matrix.Diagonal((MW @ P[ft].matrix).to_scale()).to_4x4())
for side, sx in (("Left", 1), ("Right", -1)):
    ua = f"{side}Arm_0{'11' if side == 'Left' else '35'}"
    fa = f"{side}ForeArm_0{'12' if side == 'Left' else '36'}"
    H = bone_w(ua)
    rotate_about(ua, (bone_w(ua, True) - H).normalized().rotation_difference(Vector((sx * 0.20, -0.04, -1.0)).normalized()), H)
    E = bone_w(fa)
    rotate_about(fa, (bone_w(fa, True) - E).normalized().rotation_difference(Vector((sx * 0.10, -0.32, -1.0)).normalized()), E)
dg = bpy.context.evaluated_depsgraph_get()
hm = [o for o in hobjs if o.type == "MESH"][0]
e = hm.evaluated_get(dg); me = e.to_mesh()
low = min((e.matrix_world @ v.co).z for v in me.vertices); e.to_mesh_clear()
set_world("Hips_01", Matrix.Translation((0, 0, -low)) @ (MW @ P["Hips_01"].matrix))
idle_pose = {pb.name: (pb.location.copy(), pb.rotation_quaternion.copy(), pb.scale.copy()) for pb in P}
# idle reference points (man standing at the origin)
IDLE_L_ANKLE = bone_w("LeftFoot_059"); IDLE_R_ANKLE = bone_w("RightFoot_064")
IDLE_L_FOOT_Q = (MW @ P["LeftFoot_059"].matrix).to_quaternion()
IDLE_R_FOOT_Q = (MW @ P["RightFoot_064"].matrix).to_quaternion()
IDLE_HAND = bone_w("RightForeArm_036", True)
IDLE_L_HAND = bone_w("LeftForeArm_012", True)
IDLE_HIPS = bone_w("Hips_01")


def idle_action(name, ref):
    act = bpy.data.actions.new(name)
    harm.animation_data.action = act
    for pb in P:
        loc, q, scl = idle_pose[pb.name]; q = q.copy()
        if q.dot(ref[pb.name]) < 0:
            q.negate()                      # same rotation, sign matched to the throw it blends with
        pb.location, pb.rotation_quaternion, pb.scale = loc, q, scl
        for path in ("location", "rotation_quaternion", "scale"):
            pb.keyframe_insert(path, frame=0, group=pb.name)
    harm.animation_data.action = None
    return act


idle_a, idle_b = idle_action("IdleA", q_start), idle_action("IdleB", q_end)

# ====================== places ======================
X_LANE, Y_HOME = -0.75, -2.3                    # dog's start spot (HUB)
KNEEL_BACK = 0.62                               # he kneels by stepping back with the right leg
X_PET = -0.70                                   # diagonal, on his right (camera) side
HIPS_KNEEL = Vector((IDLE_HIPS.x, IDLE_L_ANKLE.y + KNEEL_BACK, 0.84))
EARS_AT = Vector((X_PET, HIPS_KNEEL.y - 0.47, 0.95))          # dog's head-top when sitting (within his reach)
Y_PET = EARS_AT.y - 0.44                        # dog root (it faces +Y, toward him)
RUN_SPEED, WALK_SPEED = 0.155, 0.05

# ====================== dog helpers ======================
dad = nla_reset(darm)
base = dad.nla_tracks.new()
bs = base.strips.new("Base", 0, A["RunCycle"])     # full-channel base pose (walk lacks 6 channels)
bs.action_frame_start, bs.action_frame_end = 0, 1
bs.frame_end = 1; bs.extrapolation = "HOLD"
dog_keys = {}


def key_dog(f, x, y, lift=0.0, yaw=0.0):
    dog_keys[int(f)] = (x, y, lift, yaw)


def bake_dog_root():
    for f in sorted(dog_keys):
        x, y, up, yaw = dog_keys[f]
        dctl.location = (x, y, up)
        dctl.rotation_euler = (0, 0, math.radians(yaw))
        dctl.keyframe_insert("location", frame=f)
        dctl.keyframe_insert("rotation_euler", frame=f)


jaw = darm.pose.bones["SnoutLower_metarig"]
jaw.rotation_mode = "XYZ"
JAW_OPEN = math.radians(-28)


def jaw_keys(points):
    act = bpy.data.actions.new("Jaw")
    darm.animation_data.action = act
    for f, ang in points:
        jaw.rotation_euler = (ang, 0, 0)
        jaw.keyframe_insert("rotation_euler", frame=f, group="jaw")
    darm.animation_data.action = None
    s = dad.nla_tracks.new().strips.new("Jaw", 0, act)
    s.blend_type = "ADD"; s.extrapolation = "HOLD"


# ====================== man: IK rig for kneeling and petting ======================
def empty(name, loc=(0, 0, 0)):
    o = bpy.data.objects.new(name, None); o.location = loc
    o.rotation_mode = "QUATERNION"
    sc.collection.objects.link(o); return o


ik = {}


def add_ik(bone, target, pole, pole_angle, chain=2):
    c = P[bone].constraints.new("IK")
    c.target = target; c.pole_target = pole; c.pole_angle = math.radians(pole_angle)
    c.chain_count = chain; c.use_stretch = False
    c.influence = 0.0
    ik[bone] = c
    return c


def copy_rot(bone, target):
    c = P[bone].constraints.new("COPY_ROTATION")
    c.target = target; c.target_space = "WORLD"; c.owner_space = "WORLD"
    c.influence = 0.0
    ik[bone + "_rot"] = c
    return c


T_LF, T_RF = empty("IK_LFoot", IDLE_L_ANKLE), empty("IK_RFoot", IDLE_R_ANKLE)
R_LF, R_RF = empty("Rot_LFoot"), empty("Rot_RFoot")
R_LF.rotation_quaternion, R_RF.rotation_quaternion = IDLE_L_FOOT_Q, IDLE_R_FOOT_Q
P_LK = empty("Pole_LKnee", IDLE_L_ANKLE + Vector((0, -1.5, 0.9)))
P_RK = empty("Pole_RKnee", IDLE_R_ANKLE + Vector((0, -1.5, 0.6)))
T_RH, P_RE = empty("IK_RHand", IDLE_HAND), empty("Pole_RElbow", IDLE_HAND + Vector((-0.6, 0.6, -0.3)))
T_LH, P_LE = empty("IK_LHand", IDLE_L_HAND), empty("Pole_LElbow", IDLE_L_HAND + Vector((0.6, 0.6, -0.3)))
# pole angles measured so the IK reproduces the plain pose exactly (probe_pole.py)
add_ik("LeftLeg_058", T_LF, P_LK, 90); add_ik("RightLeg_063", T_RF, P_RK, 90)
copy_rot("LeftFoot_059", R_LF); copy_rot("RightFoot_064", R_RF)
add_ik("RightForeArm_036", T_RH, P_RE, -60); add_ik("LeftForeArm_012", T_LH, P_LE, 15)


def kneel_targets():
    """World targets when fully kneeling on the right knee, left foot planted."""
    hy = HIPS_KNEEL.y
    knee_r = Vector((IDLE_R_ANKLE.x + 0.02, hy + 0.10, 0.08))
    return {
        "body": Vector((0, HIPS_KNEEL.y - IDLE_HIPS.y, HIPS_KNEEL.z - IDLE_HIPS.z)),   # HumanCtl offset
        "lf": IDLE_L_ANKLE.copy(),
        "rf": knee_r + Vector((0, 0.70, 0.09)),
        "rf_q": Quaternion((1, 0, 0), math.radians(-95)) @ IDLE_R_FOOT_Q,              # toes down behind him
        "lknee_top": Vector((IDLE_L_ANKLE.x, IDLE_L_ANKLE.y - 0.04, 0.80)),
    }


KT = kneel_targets()


def key_obj(o, f, loc=None, rot=None):
    if loc is not None:
        o.location = loc; o.keyframe_insert("location", frame=f)
    if rot is not None:
        o.rotation_quaternion = rot; o.keyframe_insert("rotation_quaternion", frame=f)


def kneel_path(f0, f1, down=True):
    """Keys for going down (f0->f1) or standing up. Body lowers, right foot
    lifts and swings back, left foot stays planted."""
    n = f1 - f0
    for i in range(n + 1):
        u = ease(i / n) if down else 1 - ease(i / n)
        f = f0 + i
        key_obj(hctl, f, loc=KT["body"] * u)
        rf = IDLE_R_ANKLE.lerp(KT["rf"], u) + Vector((0, 0, 0.18 * math.sin(math.pi * u)))
        key_obj(T_RF, f, loc=rf, rot=IDLE_R_FOOT_Q.slerp(KT["rf_q"], u))
        key_obj(R_RF, f, rot=IDLE_R_FOOT_Q.slerp(KT["rf_q"], u))


def key_influence(c, points):
    for f, v in points:
        c.influence = v
        c.keyframe_insert("influence", frame=f)


# ====================== frisbee, ground, lights, camera ======================
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.24, depth=0.04)
disc = bpy.context.object; disc.name = "Frisbee"
bpy.ops.object.shade_smooth()
bev = disc.modifiers.new("bev", "BEVEL"); bev.width = 0.015; bev.segments = 3
mat = bpy.data.materials.new("FrisbeeMat"); mat.use_nodes = True
b = mat.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (1.0, 0.18, 0.55, 1)
b.inputs["Roughness"].default_value = 0.35
b.inputs["Emission Color"].default_value = (1.0, 0.25, 0.6, 1)
b.inputs["Emission Strength"].default_value = 3.0
disc.data.materials.append(mat)
disc.rotation_mode = "QUATERNION"
HELD_Q = Quaternion((0, 1, 0), math.radians(90)) @ Quaternion((0, 0, 1), math.radians(15))
RIM = Vector((0, -0.03, -0.19))                 # held by the rim, hanging at his side

bpy.ops.mesh.primitive_plane_add(size=80, location=(0, -6, 0))
bpy.context.object.is_shadow_catcher = True
key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "SUN"))
key.data.energy = 3.2; key.data.angle = math.radians(8)
key.rotation_euler = (math.radians(28), 0, math.radians(-125)); sc.collection.objects.link(key)
rim = bpy.data.objects.new("Rim", bpy.data.lights.new("Rim", "SUN"))
rim.data.energy = 2.2; rim.data.color = (0.35, 0.85, 1.0); rim.data.use_shadow = False   # no stray second shadow
rim.rotation_euler = (math.radians(70), 0, math.radians(60)); sc.collection.objects.link(rim)
sc.world = bpy.data.worlds.new("World"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.32, 0.34, 0.42, 1)
sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 85; cam.data.sensor_fit = "HORIZONTAL"
target = Vector((0, -7.4, 1.25)); dv = Vector((-1.0, -0.30, 0.13)).normalized()
cam.location = target + dv * 46
if os.environ.get("CLOSE"):                      # inspection close-up (not used for the app)
    target = Vector((0, -0.6, 0.85)); cam.location = target + dv * 13
cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()

# ====================== clips ======================
LOOK_SMOOTH = 0.25
ARM_SWING = float(os.environ.get('ARM_SWING', '5.0'))     # degrees, shoulder pendulum
ARM_ELBOW = float(os.environ.get('ARM_ELBOW', '9.0'))     # degrees, elbow flex


def bake_life(L, idle_w, extra=None, look=True):
    """COMBINE layer on the man: breathing, head following the dog, plus any
    clip-specific deltas from extra(f, add). Baked against the layers below."""
    keep = harm.animation_data.action            # IK influence keys live here; keep it active
    life = bpy.data.actions.new("Life")
    bake = {}; look_yaw = None
    for f in range(L):
        sc.frame_set(f)
        w = idle_w(f)
        env = min(1.0, f / 12.0, (L - 1 - f) / 12.0)        # breathing fades at clip joins
        deltas = {}

        def add(n, Rw):
            Wq = (MW @ P[n].matrix).to_quaternion()
            d = Wq.inverted() @ Rw @ Wq
            deltas[n] = deltas[n] @ d if n in deltas else d
        br = math.sin(2 * math.pi * f / 72.0)
        add("Spine1_03", Quaternion(RIGHT, math.radians(1.3 * br * w * env)))
        # loose, natural arms: a slow pendulum swing, a little out-and-in, elbows
        # that soften and straighten, and a gentle torso twist (only while idle)
        ph = 2 * math.pi * f / 96.0
        for sx, ua, fa in ((1, "LeftArm_011", "LeftForeArm_012"), (-1, "RightArm_035", "RightForeArm_036")):
            side_ph = 0.0 if sx > 0 else math.pi * 0.8                 # arms never move in lockstep
            fwd = math.sin(ph + side_ph)
            add(ua, Quaternion(RIGHT, math.radians(ARM_SWING * fwd * w * env)))
            add(ua, Quaternion((0, 1, 0), math.radians(sx * 2.0 * math.sin(ph * 0.7 + side_ph + 1.0) * w * env)))
            add(fa, Quaternion(RIGHT, math.radians(ARM_ELBOW * (0.5 + 0.5 * math.sin(ph + side_ph + 0.9)) * w * env)))
        add("Spine1_03", Quaternion((0, 0, 1), math.radians(2.0 * math.sin(ph * 0.5) * w * env)))
        if extra:
            extra(f, add)
        if look:
            h = bone_w("Head_06")
            v = ears_point() - h
            yaw = max(-1.1, min(1.1, math.atan2(v.x, -v.y)))
            look_yaw = yaw if look_yaw is None else look_yaw + (yaw - look_yaw) * LOOK_SMOOTH
            pitch = max(-0.6, min(0.2, math.atan2(v.z, max(0.3, v.xy.length)))) * 0.7
            for n, share in (("Neck_05", 0.4), ("Head_06", 0.6)):
                r_axis = Quaternion((0, 0, 1), look_yaw * share) @ RIGHT
                add(n, Quaternion((0, 0, 1), look_yaw * share * w) @ Quaternion(r_axis, pitch * share * w))
        bake[f] = deltas
    harm.animation_data.action = life
    for f, ds in bake.items():
        for n, q in ds.items():
            P[n].rotation_quaternion = q
            P[n].keyframe_insert("rotation_quaternion", frame=f, group=n)
    harm.animation_data.action = keep
    # add the layer only now: a strip made from a still-empty action never gets
    # bound to the armature in Blender 5 (it would silently do nothing)
    ls = had.nla_tracks.new().strips.new("Life", 0, life)
    ls.blend_type = "COMBINE"; ls.extrapolation = "HOLD"
    ls.action_frame_start, ls.action_frame_end = 0, L - 1
    ls.frame_end = L - 1
    if ls.action_slot is None and life.slots:
        ls.action_slot = life.slots[0]
    assert ls.action_slot is not None, "life layer not bound"


def bake_frisbee(L, where):
    for f in range(L):
        sc.frame_set(f)
        p, q = where(f)
        disc.location = p; disc.rotation_quaternion = q
        disc.keyframe_insert("location", frame=f); disc.keyframe_insert("rotation_quaternion", frame=f)


def spin(f):
    return Quaternion((0, 0, 1), math.radians(f * 38))


ARM_SETTLE = 22.0        # degrees, first back-swing as the arm drops after the throw
ARM_SWAY_R = 9.0         # degrees, relaxed forward/back sway of his right arm (faces the camera)
ARM_REST_BEND = 16.0     # degrees, soft elbow at rest
# gesture keys: (frame offset, shoulder raise deg, elbow bend deg, weight 0..1)
PUMP = [(0, 0, 0, 0), (8, 135, 40, 1), (11, 118, 62, 1), (14, 138, 36, 1), (17, 118, 62, 1),
        (21, 135, 40, 1), (26, 130, 44, 1), (38, 0, 16, 0)]   # fist raised high, two little pumps
PATS = [(0, 0, 16, 0), (5, 24, 42, 1), (9, 3, 10, 1), (13, 22, 40, 1), (17, 3, 10, 1), (26, 0, 16, 0)]


def sample_keys(keys, t):
    """Smoothly interpolate (shoulder, elbow, weight) from gesture keys at time t."""
    if t <= keys[0][0] or t >= keys[-1][0]:
        return 0.0, 0.0, 0.0
    for (a, s0, e0, g0), (b, s1, e1, g1) in zip(keys, keys[1:]):
        if a <= t <= b:
            u = (t - a) / (b - a); u = u * u * (3 - 2 * u)
            return s0 + (s1 - s0) * u, e0 + (e1 - e0) * u, g0 + (g1 - g0) * u
    return 0.0, 0.0, 0.0


def clip_throw(run_frames):
    T_THROW = 10
    T_RELEASE = T_THROW + (24 - A_START)
    T_RUN = T_RELEASE - 10
    T_JUMP = T_RUN + run_frames
    J0, J_CATCH, J_LAND, J_END = 8, 16, 36, 44
    T_CATCH = T_JUMP + (J_CATCH - J0); T_SETTLE = T_JUMP + (J_END - J0)
    T_TURN_END = T_SETTLE + 14
    # --- dog path ---
    key_dog(0, X_LANE, Y_HOME); key_dog(T_RUN, X_LANE, Y_HOME)
    y_jump = Y_HOME - RUN_SPEED * (T_JUMP - T_RUN)
    key_dog(T_JUMP, X_LANE, y_jump)
    for f in range(T_JUMP, T_SETTLE + 1):
        t = f - T_JUMP
        fwd = 0.17 * min(t, J_LAND - J0) + 0.08 * max(0, t - (J_LAND - J0))
        up = 0.85 * math.sin(math.pi * min(1.0, (t / (J_LAND - J0)) ** 0.75)) if t <= J_LAND - J0 else 0.0
        key_dog(f, X_LANE, y_jump - fwd, up)
    y_far = dog_keys[T_SETTLE][1]
    for f in range(T_SETTLE, T_TURN_END + 1):
        u = ease((f - T_SETTLE) / (T_TURN_END - T_SETTLE))
        key_dog(f, X_LANE, y_far + 0.25 * math.sin(math.pi * u), 0.0, 180.0 * u)
    walk_in = 0.6                                       # last bit at walking pace
    run_back = int(round((abs(Y_PET - walk_in - y_far)) / RUN_SPEED))
    T_SLOW = T_TURN_END + run_back
    T_ARRIVE = T_SLOW + int(round(walk_in / WALK_SPEED))
    key_dog(T_SLOW, X_LANE + (X_PET - X_LANE) * 0.6, Y_PET - walk_in, 0.0, 180.0)
    key_dog(T_ARRIVE, X_PET, Y_PET, 0.0, 180.0)
    T_SITDONE = T_ARRIVE + 30
    L = T_SITDONE + 10
    key_dog(L - 1, X_PET, Y_PET, 0.0, 180.0)
    bake_dog_root()
    strip(dad, A["Idle1"], 0, 0, 20, repeat=(T_RUN + 4) / 20, blend=0)
    strip(dad, A["RunCycle"], T_RUN - 2, 0, 24, repeat=(T_JUMP - T_RUN + 4) / 24)
    strip(dad, A["Jump"], T_JUMP, J0, J_END, blend=3)
    strip(dad, A["WalkCycle"], T_SETTLE - 2, 0, 24, repeat=(T_TURN_END - T_SETTLE + 4) / 24)
    strip(dad, A["RunCycle"], T_TURN_END - 2, 0, 24, repeat=(T_SLOW - T_TURN_END + 6) / 24)
    strip(dad, A["WalkCycle"], T_SLOW - 2, 0, 24, repeat=(T_ARRIVE - T_SLOW + 4) / 24)
    strip(dad, A["SitDown"], T_ARRIVE, 0, 30, blend=4)
    strip(dad, A["IdleSit"], T_SITDONE - 2, 0, 20, blend=2, hold=True)
    jaw_keys([(0, 0), (T_CATCH - 7, 0), (T_CATCH - 2, JAW_OPEN), (T_CATCH + 1, JAW_OPEN), (T_CATCH + 4, 0)])
    # --- man ---
    ia = had.nla_tracks.new().strips.new("IdleA", 0, idle_a)
    T_MID = T_THROW + 12
    ia.frame_end = T_MID; ia.extrapolation = "NOTHING"
    ib = had.nla_tracks.new().strips.new("IdleB", T_MID, idle_b)
    ib.frame_end = T_MID + 1; ib.extrapolation = "HOLD_FORWARD"
    ts = strip(had, A["Animation"], T_THROW, A_START, A_END, blend=0)
    ts.blend_in, ts.blend_out = 8, 12
    T_THROW_END = ts.frame_end

    def throw_w(f):
        if f <= T_THROW or f >= T_THROW_END:
            return 0.0
        w = min(1.0, (f - T_THROW) / 8, (T_THROW_END - f) / 12)
        return w * w * (3 - 2 * w)
    sc.frame_end = L - 1
    # --- his right arm after the throw: settle, sway, fist pump, thigh pats ---
    T_SET = T_THROW_END - 8                             # arm starts dropping out of the follow-through
    T_LAND = T_JUMP + (J_LAND - J0)                     # dog lands with the frisbee -> fist pump
    p1 = max(T_TURN_END + 6, T_LAND + 36)                     # after the fist pump is over
    pats = [p1, max(p1 + 26, T_SLOW - 34)]                      # "come on!" as it runs back
    pats = [p for p in pats if p + 26 < T_ARRIVE]
    gestures = [(T_LAND, PUMP)] + [(p, PATS) for p in pats]

    def right_arm(f, add):
        w = (1 - throw_w(f)) * min(1.0, f / 12.0, (L - 1 - f) / 12.0)
        if w <= 0:
            return
        t = f - T_SET
        settle = -ARM_SETTLE * math.exp(-t / 22.0) * math.sin(2 * math.pi * t / 26.0) if t > 0 else 0.0
        sway = ARM_SWAY_R * math.sin(2 * math.pi * f / 96.0 + 2.5)
        sh = settle + sway
        el = ARM_REST_BEND + 6.0 * (0.5 + 0.5 * math.sin(2 * math.pi * f / 96.0 + 3.4))
        for g0, keys in gestures:
            g_sh, g_el, g = sample_keys(keys, f - g0)
            if g > 0:
                sh = sh * (1 - g) + g_sh * g
                el = el * (1 - g) + g_el * g
        add("RightArm_035", Quaternion(RIGHT, math.radians(sh * w)))
        add("RightForeArm_036", Quaternion(RIGHT, math.radians(el * w)))
    bake_life(L, lambda f: 1 - throw_w(f), extra=right_arm)
    # --- frisbee ---
    sc.frame_set(T_RELEASE); p_rel = hand_point()
    sc.frame_set(T_CATCH); p_catch = mouth_point()
    peak = max(p_rel.z, p_catch.z) + 0.9 + 0.06 * abs(p_catch.y - p_rel.y)

    def where(f):
        if f < T_RELEASE:
            return hand_point() + RIM * (1 - throw_w(f)), HELD_Q
        if f <= T_CATCH:
            u = (f - T_RELEASE) / (T_CATCH - T_RELEASE)
            p = p_rel.lerp(p_catch, u)
            p.z = (1 - u) ** 2 * p_rel.z + 2 * (1 - u) * u * peak + u ** 2 * p_catch.z
            return p, Quaternion((1, 0, 0), math.radians(-12 + 18 * u)) @ spin(f)
        return mouth_point(), (darm.matrix_world @ darm.pose.bones["SnoutLower_metarig"].matrix).to_quaternion() @ Quaternion((0, 1, 0), math.radians(90))
    bake_frisbee(L, where)
    return L, dict(release=T_RELEASE, catch=T_CATCH, arrive=T_ARRIVE, sat=T_SITDONE)


def pet_strokes(f0, n_strokes, stroke_len=24):
    """Hand target along the dog's head: forehead -> back of the head, twice."""
    keys = []
    for s in range(n_strokes):
        for i in range(stroke_len):
            u = i / stroke_len
            fwd = 0.5 - 0.5 * math.cos(2 * math.pi * u)      # 0 -> 1 -> 0
            keys.append((f0 + s * stroke_len + i, fwd, 0.04 * math.sin(math.pi * u) if u > 0.5 else 0.0))
    return keys


def pet_target(fwd, lift):
    head = ears_point() + Vector((0, 0, 0.08 + lift))
    neck = dbone("spine.009_metarig") + Vector((0, 0, 0.16 + lift))
    return head.lerp(neck, 0.10 + 0.30 * fwd)


def clip_pet():
    K0, K1 = 4, 28                  # kneel down
    PET0 = 34; N = 2; SL = 24       # two strokes
    PET1 = PET0 + N * SL            # 82
    TAKE = PET1 + 12                # 94: hand on the frisbee
    S0, S1 = TAKE + 4, TAKE + 28    # stand up
    D_UP = TAKE + 2                 # dog stands
    D_TURN0, D_TURN1 = D_UP + 30, D_UP + 30 + 32
    L = D_TURN1 + 8
    # --- dog: sits, gets petted, lets go of the frisbee, trots back to its spot ---
    key_dog(0, X_PET, Y_PET, 0, 180); key_dog(D_TURN0, X_PET, Y_PET, 0, 180)
    for f in range(D_TURN0, D_TURN1 + 1):
        u = ease((f - D_TURN0) / (D_TURN1 - D_TURN0))
        key_dog(f, X_PET + (X_LANE - X_PET) * u, Y_PET + (Y_HOME - Y_PET) * u
                + 0.35 * math.sin(math.pi * u), 0, 180 + 180 * u)
    key_dog(L - 1, X_LANE, Y_HOME, 0, 360)
    bake_dog_root()
    strip(dad, A["IdleSit"], 0, 0, 20, repeat=(D_UP + 2) / 20, blend=0)
    strip(dad, A["StandUp"], D_UP, 0, 30, blend=4)
    strip(dad, A["WalkCycle"], D_TURN0 - 2, 0, 24, repeat=(D_TURN1 - D_TURN0 + 4) / 24)
    strip(dad, A["Idle1"], D_TURN1 - 2, 0, 20, blend=3, hold=True)
    jaw_keys([(0, 0), (TAKE - 4, 0), (TAKE, JAW_OPEN), (TAKE + 6, 0)])
    # --- man ---
    ib = had.nla_tracks.new().strips.new("IdleB", 0, idle_b)
    ib.frame_end = 1; ib.extrapolation = "HOLD"
    for c in ("LeftLeg_058", "RightLeg_063", "LeftFoot_059_rot", "RightFoot_064_rot"):
        key_influence(ik[c], [(0, 1.0), (L - 1, 1.0)])
    key_obj(T_LF, 0, loc=IDLE_L_ANKLE); key_obj(R_LF, 0, rot=IDLE_L_FOOT_Q)
    kneel_path(K0, K1, down=True)
    kneel_path(S0, S1, down=False)
    key_obj(hctl, 0, loc=Vector()); key_obj(hctl, L - 1, loc=Vector())
    # right arm: reach to the dog's head, stroke, take the frisbee, back to his side
    key_influence(ik["RightForeArm_036"], [(0, 0), (K0 + 8, 0), (PET0 - 2, 1), (TAKE + 2, 1), (S1 - 4, 1), (S1 + 6, 0)])
    key_influence(ik["LeftForeArm_012"], [(0, 0), (K1 - 10, 0), (K1, 1), (S0, 1), (S0 + 12, 0)])
    strokes = dict((f, (fw, lf)) for f, fw, lf in pet_strokes(PET0, N, SL))
    sc.frame_end = L - 1
    for f in range(L):
        sc.frame_set(f)
        if f < PET0:
            u = ease((f - (K0 + 8)) / (PET0 - (K0 + 8)))
            p = hand_point_idle(f).lerp(pet_target(0, 0), u)
        elif f < PET1:
            fw, lf = strokes[f]; p = pet_target(fw, lf)
        elif f <= TAKE:
            u = ease((f - PET1) / (TAKE - PET1))
            p = pet_target(0, 0).lerp(mouth_point() + Vector((0, 0.02, 0.04)), u)
        else:
            u = ease((f - TAKE) / (S1 + 6 - TAKE))
            p = (frisbee_grab_point(TAKE)).lerp(hand_point_idle(f), u)
        key_obj(T_RH, f, loc=p)
        key_obj(P_RE, f, loc=p + Vector((-0.6, 0.6, -0.3)))
        knee = Vector((IDLE_L_ANKLE.x - 0.02, IDLE_L_ANKLE.y - 0.08, 0.82)) + hctl.location * 0.0
        key_obj(T_LH, f, loc=knee)
        key_obj(P_LE, f, loc=knee + Vector((0.6, 0.6, -0.3)))
    lean = lambda f: ease((f - K0) / (K1 - K0)) * (1 - ease((f - S0) / (S1 - S0)))
    bend = lambda f: math.exp(-((f - TAKE) / 9.0) ** 2)          # bends lower to take it

    def extra(f, add):
        a = math.radians(40) * lean(f) + math.radians(14) * bend(f)
        tw = math.radians(-16) * lean(f)                        # shoulders turn toward the dog
        for n, share in (("Spine_02", 0.35), ("Spine1_03", 0.35), ("Spine2_04", 0.3)):
            add(n, Quaternion((0, 0, 1), tw * share) @ Quaternion(RIGHT, -a * share))
    bake_life(L, lambda f: 1.0, extra)

    def where(f):
        if f < TAKE:
            return mouth_point(), (darm.matrix_world @ darm.pose.bones["SnoutLower_metarig"].matrix).to_quaternion() @ Quaternion((0, 1, 0), math.radians(90))
        u = ease((f - TAKE) / (S1 + 6 - TAKE))
        return hand_point() + RIM * u, HELD_Q.slerp(HELD_Q, 1.0)
    bake_frisbee(L, where)
    return L, dict(take=TAKE, kneel=K1, stand=S1)


_grab = {}


def frisbee_grab_point(f):
    if f not in _grab:
        cur = sc.frame_current
        sc.frame_set(f); _grab[f] = mouth_point() + Vector((0, 0.02, 0.04)); sc.frame_set(cur)
    return _grab[f]


def hand_point_idle(f):
    """Where his right hand rests at his side (follows the body as it moves)."""
    return IDLE_HAND + hctl.location


def clip_finish():
    W0, W1 = 4, 36                  # dog turns and walks to him
    SIT = W1                        # 36..66 sits
    K0, K1 = 30, 54                 # he kneels
    DROP, LAND = K1 + 2, K1 + 12    # lets the frisbee drop beside him
    PET0 = LAND + 10; N = 3; SL = 26
    L = PET0 + N * SL + 1
    key_dog(0, X_LANE, Y_HOME, 0, 0); key_dog(W0, X_LANE, Y_HOME, 0, 0)
    for f in range(W0, W1 + 1):
        u = ease((f - W0) / (W1 - W0))
        key_dog(f, X_LANE + (X_PET - X_LANE) * u, Y_HOME + (Y_PET - Y_HOME) * u + 0.35 * math.sin(math.pi * u), 0, 180 * u)
    key_dog(L - 1, X_PET, Y_PET, 0, 180)
    bake_dog_root()
    strip(dad, A["Idle1"], 0, 0, 20, repeat=(W0 + 2) / 20, blend=0)
    strip(dad, A["WalkCycle"], W0 - 2, 0, 24, repeat=(W1 - W0 + 4) / 24)
    strip(dad, A["SitDown"], SIT, 0, 30, blend=4)
    strip(dad, A["IdleSit"], SIT + 28, 0, 20, blend=2, hold=True)
    jaw_keys([(0, 0)])
    ib = had.nla_tracks.new().strips.new("IdleB", 0, idle_b)
    ib.frame_end = 1; ib.extrapolation = "HOLD"
    for c in ("LeftLeg_058", "RightLeg_063", "LeftFoot_059_rot", "RightFoot_064_rot"):
        key_influence(ik[c], [(0, 1.0), (L - 1, 1.0)])
    key_obj(T_LF, 0, loc=IDLE_L_ANKLE); key_obj(R_LF, 0, rot=IDLE_L_FOOT_Q)
    key_obj(hctl, 0, loc=Vector())
    kneel_path(K0, K1, down=True)
    key_influence(ik["RightForeArm_036"], [(0, 0), (DROP + 2, 0), (PET0, 1), (L - 1, 1)])
    key_influence(ik["LeftForeArm_012"], [(0, 0), (K1 - 10, 0), (K1, 1), (L - 1, 1)])
    strokes = dict((f, (fw, lf)) for f, fw, lf in pet_strokes(PET0, N, SL))
    sc.frame_end = L - 1
    for f in range(L):
        sc.frame_set(f)
        if f < PET0:
            u = ease((f - (DROP + 2)) / (PET0 - (DROP + 2)))
            p = hand_point_idle(f).lerp(pet_target(0, 0), u)
        else:
            fw, lf = strokes.get(f, (0, 0)); p = pet_target(fw, lf)
        key_obj(T_RH, f, loc=p); key_obj(P_RE, f, loc=p + Vector((-0.6, 0.6, -0.3)))
        knee = Vector((IDLE_L_ANKLE.x - 0.02, IDLE_L_ANKLE.y - 0.08, 0.82))
        key_obj(T_LH, f, loc=knee); key_obj(P_LE, f, loc=knee + Vector((0.6, 0.6, -0.3)))
    lean = lambda f: ease((f - K0) / (K1 - K0))

    def extra(f, add):
        a = math.radians(40) * lean(f)
        tw = math.radians(-16) * lean(f)
        for n, share in (("Spine_02", 0.35), ("Spine1_03", 0.35), ("Spine2_04", 0.3)):
            add(n, Quaternion((0, 0, 1), tw * share) @ Quaternion(RIGHT, -a * share))
    bake_life(L, lambda f: 1.0, extra)
    flat = Quaternion()
    ground = Vector((IDLE_R_ANKLE.x - 0.40, HIPS_KNEEL.y + 0.35, 0.025))   # beside his right knee
    sc.frame_set(DROP); p_drop = hand_point() + RIM

    def where(f):
        if f < DROP:
            return hand_point() + RIM, HELD_Q
        if f < LAND:
            u = (f - DROP) / (LAND - DROP)
            p = p_drop.lerp(ground, u)
            p.z = p_drop.z + (ground.z - p_drop.z) * u * u + 0.12 * math.sin(math.pi * u)
            return p, HELD_Q.slerp(flat, ease(u)) @ Quaternion((0, 0, 1), math.radians(40 * u))
        bounce = 0.02 * math.exp(-(f - LAND) / 3.0) * abs(math.sin((f - LAND) * 1.3))
        return ground + Vector((0, 0, bounce)), Quaternion((0, 0, 1), math.radians(40))
    bake_frisbee(L, where)
    return L, dict(kneel=K1, drop=DROP, pet=PET0)


# ====================== build + render ======================
if CLIP.startswith("throw_"):
    L, info = clip_throw({"throw_s": 24, "throw_m": 40, "throw_l": 52}[CLIP])
elif CLIP == "pet":
    L, info = clip_pet()
elif CLIP == "finish":
    L, info = clip_finish()
else:
    raise SystemExit("unknown clip " + CLIP)
sc.frame_start, sc.frame_end = 0, L - 1
print("CLIP", CLIP, "frames", L, info)

sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"
sc.cycles.samples = SAMPLES; sc.cycles.use_denoising = True
sc.render.use_persistent_data = True
sc.render.film_transparent = True
sc.render.resolution_x, sc.render.resolution_y = RES; sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "AgX"
frames = STILLS if STILLS is not None else list(range(L))
os.makedirs(OUT, exist_ok=True)
skip = os.environ.get("SKIP_EXISTING") == "1"      # resume: keep frames already rendered
for f in frames:
    path = f"{OUT}/f{f:04d}.png"
    if skip and os.path.exists(path) and os.path.getsize(path) > 0:
        continue
    sc.frame_set(f)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
print("DONE", len(frames))
