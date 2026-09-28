"""Precise product renders of the LVC Dream Cube for Kickstarter rewards and items.

Everything is real 3D geometry built from code (no AI): each tile carries its exact
moulded texture, lit in a small virtual studio with a soft gradient backdrop.

Run with Blender (headless):
  /Applications/Blender.app/Contents/MacOS/Blender -b -P kickstarter/render/lvc_render.py -- <scene> [samples]
Scenes are listed in SCENES at the bottom. Output: kickstarter/reward-images/<scene>.jpg (1536x1024).
"""
import bpy, bmesh, math, random, sys, pathlib
from mathutils import Vector, Euler

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "kickstarter" / "reward-images"
S = 0.01  # model in centimetres, Blender in metres

HEX = {"white": "#f4f1ea", "green": "#1f9d55", "orange": "#f07a1a", "red": "#d7263d", "blue": "#1f6fd1", "yellow": "#f5c518"}
TEX = {"white": "smooth", "green": "frame", "orange": "ridges", "red": "rings", "blue": "dots", "yellow": "dome"}
ORDER = list(HEX)

def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (1.0,)

# ---------------------------------------------------------------- materials
MATS = {}
def mat(name, color, rough=0.35, coat=0.0, sheen=0.0, spec=0.5):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(color) if isinstance(color, str) else color
    b.inputs["Roughness"].default_value = rough
    for key, val in (("Coat Weight", coat), ("Sheen Weight", sheen), ("Specular IOR Level", spec)):
        if key in b.inputs:
            b.inputs[key].default_value = val
    if sheen and "Sheen Tint" in b.inputs:
        b.inputs["Sheen Tint"].default_value = (1, 0.85, 1, 1)
    MATS[name] = m
    return m

def plastic(c):
    return mat(f"plastic-{c}", HEX[c], rough=0.28, coat=0.35)

# ---------------------------------------------------------------- mesh helpers
def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj

def rbox(name, sx, sy, sz, bevel, m, segs=4, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= sx; v.co.y *= sy; v.co.z *= sz
    bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=bevel, segments=segs, affect="EDGES", profile=0.5)
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); o.location = loc
    me.materials.append(m)
    return o

def sphere(name, r, m, loc=(0, 0, 0), scale=(1, 1, 1), segs=24):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=r)
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); o.location = loc; o.scale = scale
    me.materials.append(m)
    return o

def torus(name, R, r, m, loc=(0, 0, 0), zscale=1.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    seg, ring = 64, 14
    verts = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        row = []
        for j in range(ring):
            b = 2 * math.pi * j / ring
            x = (R + r * math.cos(b)) * math.cos(a)
            y = (R + r * math.cos(b)) * math.sin(a)
            z = r * math.sin(b) * zscale
            row.append(bm.verts.new((x, y, z)))
        verts.append(row)
    for i in range(seg):
        for j in range(ring):
            bm.faces.new((verts[i][j], verts[(i + 1) % seg][j], verts[(i + 1) % seg][(j + 1) % ring], verts[i][(j + 1) % ring]))
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); o.location = loc
    me.materials.append(m)
    return o

def join(objs, name):
    """Join temporary objects into one mesh (applies transforms) and return it unlinked."""
    tmp = bpy.data.collections.new("tmp"); bpy.context.scene.collection.children.link(tmp)
    for o in objs: tmp.objects.link(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(objs) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    tmp.objects.unlink(o)
    bpy.data.collections.remove(tmp)
    return o

# ---------------------------------------------------------------- tiles & cubes (cm units, scaled by S)
TILE = 1.62      # coloured tile width
TILE_T = 0.10    # tile thickness above the cubie face
CUBIE = 1.86     # cubie size (1.9 pitch, small gap)
PITCH = 1.9

def tile_proto(c, textured=True):
    """One moulded tile, top surface at z=0, centred at origin, in metres."""
    m = plastic(c)
    parts = [rbox("t", TILE * S, TILE * S, TILE_T * S, 0.14 * S, m, loc=(0, 0, -TILE_T / 2 * S))]
    t = TEX[c] if textured else "smooth"
    h = 0.09
    if t == "frame":
        o, w = 1.22, 0.2
        for x, y, sx, sy in ((0, (o - w) / 2, o, w), (0, -(o - w) / 2, o, w), ((o - w) / 2, 0, w, o - 2 * w), (-(o - w) / 2, 0, w, o - 2 * w)):
            parts.append(rbox("f", sx * S, sy * S, h * 2 * S, 0.035 * S, m, segs=2, loc=(x * S, y * S, 0)))
    elif t == "ridges":
        half = 0.64
        for d in [k * 0.3 for k in range(-3, 4)]:
            L = (2 * half - abs(d)) * math.sqrt(2) * 0.92
            if L < 0.3: continue
            b = rbox("r", L * S, 0.11 * S, h * 2 * S, 0.04 * S, m, segs=2, loc=(d / 2 * S, d / 2 * S, 0))
            b.rotation_euler = (0, 0, -math.pi / 4)
            parts.append(b)
    elif t == "rings":
        for R in (0.17, 0.36, 0.55):
            parts.append(torus("ring", R * S, 0.055 * S, m, loc=(0, 0, 0), zscale=1.3))
    elif t == "dots":
        for i in range(4):
            for j in range(4):
                parts.append(sphere("d", 0.085 * S, m, loc=((-0.45 + i * 0.3) * S, (-0.45 + j * 0.3) * S, 0), scale=(1, 1, 1.1), segs=16))
    elif t == "dome":
        parts.append(sphere("dome", 0.46 * S, m, loc=(0, 0, 0), scale=(1, 1, 0.62), segs=40))
    o = join(parts, f"tile-{c}-{'tex' if textured else 'flat'}")
    o.hide_render = True
    return o

PROTOS = {}
def proto(key, builder):
    if key not in PROTOS:
        PROTOS[key] = builder()
    return PROTOS[key]

BLACK = None
def cubie_proto():
    return join([rbox("cubie", CUBIE * S, CUBIE * S, CUBIE * S, 0.2 * S, mat("cube-body", "#141218", rough=0.32, coat=0.2))], "cubie")

NORMALS = {(0, 0, 1): (0, 0, 0), (0, 0, -1): (math.pi, 0, 0), (1, 0, 0): (0, math.pi / 2, 0),
           (-1, 0, 0): (0, -math.pi / 2, 0), (0, 1, 0): (-math.pi / 2, 0, 0), (0, -1, 0): (math.pi / 2, 0, 0)}

def scramble(seed):
    r = random.Random(seed)
    cols = [c for c in ORDER for _ in range(9)]
    r.shuffle(cols)
    return cols

def dream_cube(loc=(0, 0, 0), rot_z=0.0, seed=1, textured=True, colours=None, coll=None, tilt=(0, 0)):
    """A full 3x3 cube sitting on the floor at loc (cm). Returns its parent empty."""
    root = bpy.data.objects.new("cube", None)
    link(root, coll)
    half = 1.5 * PITCH
    root.location = Vector(loc) * S + Vector((0, 0, half * S + (TILE_T - 0.02) * S))
    root.rotation_euler = (tilt[0], tilt[1], rot_z)
    cols = colours or scramble(seed)
    cub = proto("cubie", cubie_proto)
    k = 0
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for z in (-1, 0, 1):
                c = cub.copy(); c.hide_render = False
                c.location = (i * PITCH * S, j * PITCH * S, z * PITCH * S); c.parent = root
                link(c, coll)
                for n, rot in NORMALS.items():
                    if (n[0] and n[0] == i) or (n[1] and n[1] == j) or (n[2] and n[2] == z):
                        colour = cols[k % 54]; k += 1
                        t = proto(("tile", colour, textured), lambda: tile_proto(colour, textured)).copy()
                        t.hide_render = False
                        t.location = (Vector((i, j, z)) * PITCH + Vector(n) * (CUBIE / 2 + TILE_T)) * S
                        t.rotation_euler = rot
                        t.parent = root
                        link(t, coll)
    return root

def loose_tile(c, loc, rot=0.0, textured=True):
    t = proto(("tile", c, textured), lambda: tile_proto(c, textured)).copy()
    t.hide_render = False
    t.location = Vector(loc) * S + Vector((0, 0, TILE_T * S))
    t.rotation_euler = (0, 0, rot)
    return link(t)

# ---------------------------------------------------------------- props
def revolve(name, prof, m, wave=lambda z, t: 0.0, seg=96, solid=0.0):
    """Revolve a (radius, height) profile in cm around Z; wave(z, theta) adds radial wrinkles."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rows = []
    for r, z in prof:
        row = []
        for i in range(seg):
            t = 2 * math.pi * i / seg
            rr = r + wave(z, t)
            row.append(bm.verts.new((rr * math.cos(t) * S, rr * math.sin(t) * S, z * S)))
        rows.append(row)
    for k in range(len(rows) - 1):
        for i in range(seg):
            bm.faces.new((rows[k][i], rows[k][(i + 1) % seg], rows[k + 1][(i + 1) % seg], rows[k + 1][i]))
    if prof[0][0] < 0.01:
        pass
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); me.materials.append(m)
    if solid:
        so = o.modifiers.new("solid", "SOLIDIFY"); so.thickness = solid * S
    sub = o.modifiers.new("sub", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    return link(o)

def pouch(loc, scale=1.0):
    velvet = mat("velvet", "#5b2a86", rough=0.7, sheen=1.0, spec=0.2)
    gold = mat("cord", "#f5c518", rough=0.45)
    body_prof = [(0.0, 0.0), (2.2, 0.02), (3.1, 0.35), (3.6, 1.2), (3.75, 2.4), (3.55, 3.8), (3.0, 5.0), (2.1, 6.0), (1.35, 6.7), (1.2, 7.0)]
    body = revolve("pouch-body", body_prof, velvet,
                   wave=lambda z, t: (0.10 * math.sin(7 * t + z) + 0.05 * math.sin(13 * t)) * min(1, z / 5) + 0.18 * max(0, (z - 5.2) / 1.8) * math.sin(16 * t))
    frill_prof = [(1.2, 7.0), (1.25, 7.4), (1.5, 7.9), (2.0, 8.4), (2.5, 8.7)]
    frill = revolve("pouch-frill", frill_prof, velvet, solid=0.12,
                    wave=lambda z, t: max(0, (z - 7.2)) * 0.28 * math.sin(11 * t) + max(0, (z - 7.6)) * 0.12 * math.sin(23 * t + 1))
    cord = torus("pouch-cord", 1.3 * S, 0.13 * S, gold, loc=(0, 0, 7.05 * S)); link(cord)
    parts = [body, frill, cord]
    for side in (-1, 1):
        cu = bpy.data.curves.new("tail", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.12 * S; cu.bevel_resolution = 4
        sp = cu.splines.new("BEZIER"); sp.bezier_points.add(2)
        pts = [(side * 0.9, -1.0, 7.0), (side * 1.9, -3.2, 5.6), (side * 1.6, -3.9, 3.4)]
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = Vector(p) * S; bp.handle_left_type = bp.handle_right_type = "AUTO"
        tail = bpy.data.objects.new("pouch-tail", cu); cu.materials.append(gold); link(tail)
        knot = sphere("pouch-knot", 0.3 * S, gold, loc=(side * 1.6 * S, -3.9 * S, 3.3 * S)); link(knot)
        parts += [tail, knot]
    grp = bpy.data.objects.new("pouch-root", None); link(grp)
    for o in parts: o.parent = grp
    grp.location = Vector(loc) * S; grp.scale = (scale,) * 3
    return grp

BRAILLE = "⠇⠧⠉⠙⠗⠑⠁⠍⠉⠥⠃⠑"  # "lvc dream cube" pattern, dots only
def braille_card(loc, rot=(0, 0, 0)):
    paper = mat("paper", "#cfc9bf", rough=0.8, spec=0.3)
    plum = mat("plum-ink", "#5b2a86", rough=0.5)
    W, H = 5.6, 7.6
    parts = [rbox("card", W * S, H * S, 0.06 * S, 0.03 * S, paper, segs=2)]
    cells = [[1, 0, 1, 1, 0, 0], [1, 1, 0, 0, 1, 0], [0, 1, 1, 0, 1, 1], [1, 0, 0, 1, 1, 0], [1, 1, 1, 0, 0, 1], [0, 1, 0, 1, 1, 1],
             [1, 0, 1, 0, 1, 0], [0, 1, 1, 1, 0, 1], [1, 1, 0, 1, 0, 0], [0, 0, 1, 1, 1, 0], [1, 0, 0, 0, 1, 1], [0, 1, 1, 0, 0, 1]]
    for k, cell in enumerate(cells):
        cx = -1.8 + (k % 4) * 1.2; cy = 2.6 - (k // 4) * 1.5
        for dd, on in enumerate(cell):
            if on:
                parts.append(sphere("bd", 0.1 * S, paper, loc=((cx + (dd % 2) * 0.3) * S, (cy - (dd // 2) * 0.3) * S, 0.03 * S), scale=(1, 1, 0.85), segs=14))
    card = join(parts, "braille-card"); link(card)
    # speaker icon, printed in plum
    me = bpy.data.meshes.new("spk"); bm = bmesh.new()
    pts = [(0, 0.22), (0.32, 0.22), (0.72, 0.58), (0.72, -0.58), (0.32, -0.22), (0, -0.22)]
    bm.faces.new([bm.verts.new(((x - 0.9) * S, (y - 2.7) * S, 0.035 * S)) for x, y in pts])
    bm.to_mesh(me); bm.free(); me.materials.append(plum)
    spk = bpy.data.objects.new("spk", me); spk.modifiers.new("t", "SOLIDIFY").thickness = 0.01 * S; link(spk); spk.parent = card
    for r in (0.5, 0.85):
        cu = bpy.data.curves.new("wave", "CURVE"); cu.bevel_depth = 0.05 * S
        sp = cu.splines.new("POLY"); n = 14; sp.points.add(n - 1)
        for i in range(n):
            a_ = -0.75 + 1.5 * i / (n - 1)
            sp.points[i].co = (math.cos(a_) * r * S, math.sin(a_) * r * S, 0, 1)
        w = bpy.data.objects.new("wave", cu); cu.materials.append(plum); w.location = (-0.1 * S, -2.7 * S, 0.04 * S); link(w)
        w.parent = card
    card.location = Vector(loc) * S; card.rotation_euler = rot
    return card

def booklet(loc, rot=(0, 0, 0), open_=False):
    plum = mat("booklet", "#5b2a86", rough=0.55)
    page = mat("pages", "#f7f2ea", rough=0.85)
    W, H = 10.5, 14.8
    parts = [rbox("cover", W * S, H * S, 0.5 * S, 0.12 * S, plum, segs=3),
             rbox("pagesedge", (W - 0.4) * S, (H - 0.4) * S, 0.42 * S, 0.02 * S, page, segs=1, loc=(0.25 * S, 0, 0))]
    b = join(parts, "booklet"); link(b)
    for i, c in enumerate(ORDER):
        t = proto(("tile", c, True), lambda: tile_proto(c, True)).copy(); t.hide_render = False
        t.scale = (1.15,) * 3
        t.location = ((-2.4 + (i % 3) * 2.4) * S, (3.4 - (i // 3) * 2.4) * S, 0.27 * S)
        t.parent = b; link(t)
    for k, wdt in enumerate((6.5, 4.2)):
        line = rbox("line", wdt * S, 0.45 * S, 0.02 * S, 0.1 * S, mat("cream-print", "#fff4c7", rough=0.6), segs=2,
                    loc=((-3.5 + wdt / 2) * S, (-1.6 - k * 1.0) * S, 0.26 * S)); line.parent = b; link(line)
    b.location = Vector(loc) * S + Vector((0, 0, 0.25 * S)); b.rotation_euler = rot
    return b

def heart_mesh(size, m, thick=0.08):
    cu = bpy.data.curves.new("heart", "CURVE"); cu.dimensions = "2D"; cu.extrude = thick * S; cu.fill_mode = "BOTH"
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(3); sp.use_cyclic_u = True
    pts = [((0, -1.0), (-0.5, -0.5), (0.5, -0.5)), ((1.0, 0.35), (0.9, -0.2), (1.1, 1.0)),
           ((0, 0.45), (0.5, 1.1), (-0.5, 1.1)), ((-1.0, 0.35), (-1.1, 1.0), (-0.9, -0.2))]
    for bp, (co, hl, hr) in zip(sp.bezier_points, pts):
        bp.co = (co[0] * size * S, co[1] * size * S, 0); bp.handle_left = (hl[0] * size * S, hl[1] * size * S, 0); bp.handle_right = (hr[0] * size * S, hr[1] * size * S, 0)
    o = bpy.data.objects.new("heart", cu); cu.materials.append(m)
    return link(o)

def kraft_card(loc, rot=(0, 0, 0), w=6.0, h=8.0):
    kraft = mat("kraft", "#c89b6a", rough=0.85, spec=0.25)
    c = rbox("kraft-card", w * S, h * S, 0.08 * S, 0.04 * S, kraft, segs=2); link(c)
    hrt = heart_mesh(0.9, mat("heart-red", "#d7263d", rough=0.35)); hrt.location = (0, 0.4 * S, 0.06 * S); hrt.parent = c
    c.location = Vector(loc) * S; c.rotation_euler = rot
    return c

def gift_box(loc, rot_z=0.0):
    kraft = mat("kraft", "#c89b6a", rough=0.85, spec=0.25)
    red = mat("ribbon", "#d7263d", rough=0.35, coat=0.3)
    L = 8.0
    base = rbox("gbox", L * S, L * S, 3.0 * S, 0.1 * S, kraft, segs=2, loc=(0, 0, 1.5 * S)); link(base)
    inner = rbox("ginner", (L - 0.5) * S, (L - 0.5) * S, 0.3 * S, 0.05 * S, mat("tissue", "#fff4c7", rough=0.9), segs=1, loc=(0, 0, 2.9 * S)); link(inner)
    band = rbox("band", (L + 0.05) * S, 1.0 * S, 3.05 * S, 0.02 * S, red, segs=1, loc=(0, 0, 1.5 * S)); link(band)
    grp = bpy.data.objects.new("gift", None); link(grp)
    for o in (base, inner, band): o.parent = grp
    grp.location = Vector(loc) * S; grp.rotation_euler = (0, 0, rot_z)
    return grp

def ribbon_on_cube(cube_root, loc):
    red = mat("ribbon", "#d7263d", rough=0.35, coat=0.3)
    side = 3 * PITCH + 0.3
    for rz in (0, math.pi / 2):
        b = rbox("rib", (side + 0.06) * S, 0.7 * S, (side + 0.06) * S, 0.05 * S, red, segs=1)
        b.rotation_euler = (0, 0, rz); b.parent = cube_root; link(b)
    for s_ in (-1, 1):
        loop = torus("bow", 0.9 * S, 0.22 * S, red, zscale=0.5)
        loop.location = (s_ * 0.8 * S, 0, (side / 2 + 0.35) * S); loop.rotation_euler = (math.pi / 2, s_ * 0.5, 0); loop.scale = (1, 0.6, 1)
        loop.parent = cube_root; link(loop)
    k = sphere("bowknot", 0.35 * S, red, loc=(0, 0, (side / 2 + 0.3) * S)); k.parent = cube_root; link(k)

def carton(loc, size=(30, 22, 18), rot_z=0.0, open_=False):
    kraft = mat("carton", "#c28f58", rough=0.8, spec=0.25)
    tape = mat("tape", "#e9d3ab", rough=0.3)
    x, y, z = size
    grp = bpy.data.objects.new("carton", None); link(grp)
    if open_:
        th = 0.35
        for px, py, sx, sy in ((0, y / 2, x, th), (0, -y / 2, x, th), (x / 2, 0, th, y), (-x / 2, 0, th, y)):
            w = rbox("wall", sx * S, sy * S, z * S, 0.05 * S, kraft, segs=1, loc=(px * S, py * S, z / 2 * S)); w.parent = grp; link(w)
        fl = rbox("floor", x * S, y * S, th * S, 0.05 * S, kraft, segs=1, loc=(0, 0, th / 2 * S)); fl.parent = grp; link(fl)
        # flaps hinged on the rim, folded open outwards (the front one is left off so the cubes show)
        t = 0.42  # lean away from vertical, radians
        L = y / 2
        back = rbox("flap", x * S, L * S, th * S, 0.05 * S, kraft, segs=1)
        back.location = (0, (y / 2 + math.sin(t) * L / 2) * S, (z + math.cos(t) * L / 2) * S)
        back.rotation_euler = (math.pi / 2 - t, 0, 0); back.parent = grp; link(back)
        Ls = y / 2.4
        for sgn in (-1, 1):
            side = rbox("flap", Ls * S, (y - 0.4) * S, th * S, 0.05 * S, kraft, segs=1)
            side.location = (sgn * (x / 2 + math.sin(t + 0.25) * Ls / 2) * S, 0, (z + math.cos(t + 0.25) * Ls / 2) * S)
            side.rotation_euler = (0, -sgn * (math.pi / 2 - t - 0.25), 0); side.parent = grp; link(side)
    else:
        b = rbox("box", x * S, y * S, z * S, 0.12 * S, kraft, segs=2, loc=(0, 0, z / 2 * S)); b.parent = grp; link(b)
        t = rbox("tape", (x + 0.02) * S, 4.5 * S, 0.05 * S, 0.02 * S, tape, segs=1, loc=(0, 0, (z + 0.01) * S)); t.parent = grp; link(t)
        t2 = rbox("tape2", 4.5 * S, 0.05 * S, 6 * S, 0.02 * S, tape, segs=1, loc=(0, -(y / 2 + 0.02) * S, (z - 3) * S)); t2.parent = grp; link(t2)
    grp.location = Vector(loc) * S; grp.rotation_euler = (0, 0, rot_z)
    return grp

def tray(loc, rows=6, cols=9):
    wood = mat("tray", "#e8d2b0", rough=0.55)
    W, H = cols * 2.0 + 1.2, rows * 2.0 + 1.2
    base = rbox("tray", W * S, H * S, 0.5 * S, 0.3 * S, wood, segs=3, loc=(0, 0, 0.25 * S)); link(base)
    rim = []
    for px, py, sx, sy in ((0, H / 2, W, 0.4), (0, -H / 2, W, 0.4), (W / 2, 0, 0.4, H), (-W / 2, 0, 0.4, H)):
        r = rbox("rim", sx * S, sy * S, 1.0 * S, 0.15 * S, wood, segs=2, loc=(px * S, py * S, 0.5 * S)); link(r); r.parent = base
    base.location = Vector(loc) * S + Vector((0, 0, 0.25 * S))
    return base, W, H

# ---------------------------------------------------------------- studio
def studio(gradient=("#fff3e2", "#ecd9f7"), warm_sun=False, cam=(0, -52, 24), target=(0, 0, 3), lens=70, fstop=11):
    sc = bpy.context.scene
    for o in list(sc.objects): bpy.data.objects.remove(o, do_unlink=True)
    # seamless sweep backdrop with a soft vertical gradient
    prof = [(y, 0.0) for y in (-120, -40, 0, 20)] + [(20 + 25 * math.sin(a), 25 - 25 * math.cos(a)) for a in [i * math.pi / 2 / 12 for i in range(1, 13)]] + [(45, z) for z in (50, 120)]
    me = bpy.data.meshes.new("sweep"); bm = bmesh.new()
    rows = []
    for x in (-150, 150):
        rows.append([bm.verts.new((x * S, y * S, z * S)) for y, z in prof])
    for k in range(len(prof) - 1):
        bm.faces.new((rows[0][k], rows[1][k], rows[1][k + 1], rows[0][k + 1]))
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    sweep = bpy.data.objects.new("sweep", me); link(sweep)
    m = bpy.data.materials.new("backdrop"); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes["Principled BSDF"]; bsdf.inputs["Roughness"].default_value = 0.9
    if "Specular IOR Level" in bsdf.inputs: bsdf.inputs["Specular IOR Level"].default_value = 0.15
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); mr = nt.nodes.new("ShaderNodeMapRange")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    mr.inputs["From Min"].default_value = -0.1; mr.inputs["From Max"].default_value = 0.9
    nt.links.new(tc.outputs["Object"], sep.inputs[0]); nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"]); nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    dim = lambda c, k: tuple(x * k for x in lin(c)[:3]) + (1.0,)  # the studio light brightens the sweep, so keep its albedo low
    ramp.color_ramp.elements[0].color = dim(gradient[0], 0.58); ramp.color_ramp.elements[1].color = dim(gradient[1], 0.66)
    ramp.color_ramp.interpolation = "EASE"
    me.materials.append(m)
    # lights: big soft key, fill, rim
    def area(name, loc, power, size, color=(1, 1, 1)):
        l = bpy.data.lights.new(name, "AREA"); l.energy = power; l.size = size; l.color = color
        o = bpy.data.objects.new(name, l); o.location = loc; link(o)
        d = Vector(target) * S - o.location; o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return o
    area("key", (-0.45, -0.45, 0.6), 38, 0.6, (1, 0.97, 0.92))
    area("fill", (0.55, -0.35, 0.25), 9, 0.8, (0.95, 0.95, 1))
    area("rim", (0.2, 0.6, 0.45), 22, 0.5, (1, 0.95, 1))
    if warm_sun:
        l = bpy.data.lights.new("sun", "SUN"); l.energy = 1.6; l.color = (1, 0.72, 0.42); l.angle = 0.08
        o = bpy.data.objects.new("sun", l); o.rotation_euler = Euler((math.radians(72), 0, math.radians(-55))); link(o)
    world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = lin("#fff8ee")
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12
    # camera
    cd = bpy.data.cameras.new("cam"); cd.lens = lens
    cd.dof.use_dof = True; cd.dof.aperture_fstop = fstop
    co = bpy.data.objects.new("cam", cd); co.location = Vector(cam) * S; link(co)
    d = Vector(target) * S - co.location; co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cd.dof.focus_distance = d.length
    sc.camera = co
    return co

def render(name, samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"; prefs.get_devices()
        for d in prefs.devices: d.use = True
        sc.cycles.device = "GPU"
    except Exception:
        pass
    sc.cycles.samples = samples; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1536, 1024, 100
    try:
        # "Standard" keeps the exact brand colours (AgX desaturates reds and yellows)
        sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"; sc.view_settings.exposure = -1.25
    except Exception:
        pass
    sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 94
    OUT.mkdir(parents=True, exist_ok=True)
    sc.render.filepath = str(OUT / f"{name}.jpg")
    bpy.ops.render.render(write_still=True)

# ---------------------------------------------------------------- scenes (cm)
def s_dream_cube():
    studio(cam=(2, -40, 17), target=(0, 1, 3.6), lens=58)
    dream_cube((0, 0, 0), rot_z=math.radians(38), seed=11)
    pouch((-10.5, 4, 0), 0.95)
    braille_card((9.8, 2.5, 3.8), rot=(math.radians(74), 0, math.radians(-22)))

def s_early_bird():
    studio(gradient=("#fff3dc", "#ffd9a8"), warm_sun=True, cam=(2, -40, 17), target=(0, 1, 3.6), lens=58)
    dream_cube((0, 0, 0), rot_z=math.radians(38), seed=11)
    pouch((-10.5, 4, 0), 0.95)
    braille_card((9.8, 2.5, 3.8), rot=(math.radians(74), 0, math.radians(-22)))

def s_item_dream_cube():
    studio(cam=(0, -40, 22), target=(0, 0, 3.0), lens=70)
    dream_cube((0, 0, 0), rot_z=math.radians(40), seed=11)

def s_supporter():
    studio(gradient=("#fff8ee", "#fde3e6"), cam=(3, -44, 20), target=(1, 0, 3.2), lens=62)
    dream_cube((-3, 0, 0), rot_z=math.radians(30), seed=5)
    kraft_card((6.5, 1.0, 3.6), rot=(math.radians(74), 0, math.radians(-20)))

def s_give_a_cube():
    studio(gradient=("#fff8ee", "#fde3e6"), cam=(0, -46, 24), target=(0, 0, 3.0), lens=60)
    gift_box((0, 0, 0), rot_z=math.radians(20))
    dream_cube((0, 0, 3.0), rot_z=math.radians(38), seed=23)
    h = heart_mesh(1.4, mat("heart-red", "#d7263d", rough=0.35), thick=0.3)
    h.location = Vector((8.5, -3, 0.2)) * S; h.rotation_euler = (0, 0, math.radians(-15))

def s_buy_one_give_one():
    studio(cam=(0, -38, 16), target=(0, 0, 3.4), lens=58)
    dream_cube((-5.5, 0, 0), rot_z=math.radians(30), seed=11)
    r = dream_cube((5.5, 0, 0), rot_z=math.radians(-20), seed=29)
    ribbon_on_cube(r, (6.5, 0, 0))

def s_chip_kit():
    studio(cam=(-2, -44, 34), target=(-1, 1, 1), lens=48, fstop=11)
    base, W, H = tray((5, 1, 0))
    for row, c in enumerate(ORDER):
        for k in range(9):
            loose_tile(c, (5 - W / 2 + 1.6 + k * 2.0, 1 + H / 2 - 1.6 - row * 2.0, 0.5), rot=random.Random(row * 9 + k).uniform(-0.06, 0.06))
    plain = [c for c in ORDER for _ in range(9)]; random.Random(4).shuffle(plain)
    dream_cube((-14.5, 3, 0), rot_z=math.radians(30), textured=False, colours=plain)

def s_item_chip_kit():
    studio(cam=(0, -30, 36), target=(0, 0, 0), lens=55, fstop=8)
    base, W, H = tray((0, 0, 0))
    for row, c in enumerate(ORDER):
        for k in range(9):
            loose_tile(c, (-W / 2 + 1.6 + k * 2.0, H / 2 - 1.6 - row * 2.0, 0.5), rot=random.Random(row * 9 + k).uniform(-0.06, 0.06))

def s_school_starter():
    studio(gradient=("#fff3e2", "#dbe8fb"), cam=(4, -100, 62), target=(4, 4, 2), lens=55, fstop=11)
    for r in range(4):
        for c in range(5):
            dream_cube((-17 + c * 8.8, 14 - r * 8.8, 0), rot_z=math.radians(random.Random(r * 5 + c).choice([5, 15, 25, 35])), seed=100 + r * 5 + c)
    booklet((33, -4, 0), rot=(0, 0, math.radians(-12)))

def s_school_ngo_pack():
    studio(gradient=("#fff3e2", "#dbe8fb"), cam=(4, -100, 58), target=(4, 5, 12), lens=50, fstop=11)
    carton((-30, 14, 0), rot_z=math.radians(8))
    carton((-30, 14, 18), size=(28, 21, 16), rot_z=math.radians(-4))
    box = carton((8, 6, 0), open_=True, rot_z=math.radians(-6))
    # cubes packed in a 4 x 3 grid inside the open carton, in the carton's own frame so they never cross its walls
    for r in range(3):
        for c in range(4):
            cube = dream_cube((-10.5 + c * 7.0, -7 + r * 7.0, 12.2), rot_z=0, seed=300 + r * 4 + c)
            cube.parent = box
    dream_cube((30, -8, 0), rot_z=math.radians(25), seed=9)
    booklet((31, 8, 0), rot=(0, 0, math.radians(14)))

def s_item_teaching_guide():
    studio(cam=(3, -48, 32), target=(3, 0, 1.5), lens=55)
    booklet((-4, 0, 0), rot=(0, 0, math.radians(-10)))
    dream_cube((10, -2, 0), rot_z=math.radians(35), seed=11)

SCENES = {
    "dream-cube": s_dream_cube, "early-bird": s_early_bird, "supporter": s_supporter, "give-a-cube": s_give_a_cube,
    "buy-one-give-one": s_buy_one_give_one, "chip-kit": s_chip_kit, "school-starter": s_school_starter,
    "school-ngo-pack": s_school_ngo_pack, "item-dream-cube": s_item_dream_cube, "item-chip-kit": s_item_chip_kit,
    "item-teaching-guide": s_item_teaching_guide,
}

if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = argv[0] if argv else "dream-cube"
    samples = int(argv[1]) if len(argv) > 1 else 256
    bpy.ops.wm.read_factory_settings(use_empty=True)
    SCENES[name]()
    render(name, samples)
    print("RENDERED", name)
