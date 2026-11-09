#!/usr/bin/env python3
"""Renders Java Edition GUI item icons from the client assets, the way Java draws them in
inventories and on advancement frames.

- Item model definitions (assets/*/items/*.json): model, select/condition/range_dispatch (the
  fallback / default case), composite (all parts), special (skipped: block-entity renderers).
- Model files with parent chains, texture variables, display.gui and gui_light.
- builtin/generated items: the layer sprites stacked, with their tints, drawn flat (16x16).
- Block-style models: every element face rasterised with the gui display transform, Java's
  orthographic GUI projection, nearest-neighbour texturing, alpha cutout and Java's item
  lighting (Lighting.ITEMS_3D + light.glsl), at 4x resolution (64x64).

usage: render_icons.py <unpacked client jar dir> <out dir>      -> <out>/<namespace>_<item>.png,
       writes <out>/index.json  {"minecraft:stone": "stone", ...} (file names without .png)
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

SIZE_3D = 64  # pixels for 16 GUI pixels

# ------------------------------------------------------------------ Java lighting (Lighting + light.glsl)


def _rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def _yxz(y, x, z):
    return _rot_y(y) @ _rot_x(x) @ _rot_z(z)


def _norm(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


L0 = _norm([0.2, 1.0, -0.7])
L1 = _norm([-0.2, 1.0, 0.7])
_M3D = np.diag([1.0, -1.0, 1.0]) @ _yxz(1.0821041, 3.2375858, 0.0) @ _yxz(-0.3926991, 2.3561945, 0.0)
LIGHTS_3D = (_M3D @ L0, _M3D @ L1)
_MFLAT = _rot_y(-0.3926991) @ _rot_x(2.3561945)
LIGHTS_FLAT = (_MFLAT @ L0, _MFLAT @ L1)


def light(normal, lights):
    a = max(0.0, float(np.dot(lights[0], normal)))
    b = max(0.0, float(np.dot(lights[1], normal)))
    return min(1.0, (a + b) * 0.6 + 0.4)


# ------------------------------------------------------------------ assets


class Assets:
    def __init__(self, root):
        self.root = os.path.join(root, "assets")
        self.models = {}
        self.textures = {}
        self.colormaps = {}

    @staticmethod
    def split(rid):
        if ":" in rid:
            ns, path = rid.split(":", 1)
        else:
            ns, path = "minecraft", rid
        return ns, path

    def model(self, rid):
        if rid in self.models:
            return self.models[rid]
        ns, path = self.split(rid)
        p = os.path.join(self.root, ns, "models", path + ".json")
        m = json.load(open(p)) if os.path.exists(p) else None
        self.models[rid] = m
        return m

    def texture(self, rid):
        if rid in self.textures:
            return self.textures[rid]
        ns, path = self.split(rid)
        p = os.path.join(self.root, ns, "textures", path + ".png")
        if not os.path.exists(p):
            self.textures[rid] = None
            return None
        im = Image.open(p).convert("RGBA")
        if im.height > im.width and os.path.exists(p + ".mcmeta"):
            im = im.crop((0, 0, im.width, im.width))  # first animation frame
        arr = np.asarray(im, dtype=np.float32) / 255.0
        self.textures[rid] = arr
        return arr

    def grass_color(self, temperature, downfall):
        # GrassColor.get: colormap/grass.png at (1-temp)*255, (1-downfall*temp)*255
        if "grass" not in self.colormaps:
            self.colormaps["grass"] = Image.open(os.path.join(self.root, "minecraft", "textures", "colormap", "grass.png")).convert("RGB")
        t = max(0.0, min(1.0, temperature))
        d = max(0.0, min(1.0, downfall)) * t
        cm = self.colormaps["grass"]
        x, y = int((1 - t) * 255), int((1 - d) * 255)
        r, g, b = cm.getpixel((x, y))
        return (r / 255, g / 255, b / 255)


def resolve_model(assets, rid):
    """Flattens the parent chain: (textures, elements, gui display, gui_light, generated?)."""
    textures, elements, gui, gui_light, generated = {}, None, None, None, False
    chain, seen = [], set()
    cur = rid
    while cur and cur not in seen:
        seen.add(cur)
        if cur.replace("minecraft:", "") == "builtin/generated":
            generated = True
            break
        m = assets.model(cur)
        if m is None:
            break
        chain.append(m)
        cur = m.get("parent")
    for m in reversed(chain):  # parent first, child overrides
        textures.update(m.get("textures", {}))
        if "elements" in m:
            elements = m["elements"]
        d = m.get("display", {}).get("gui")
        if d is not None:
            gui = d
        if "gui_light" in m:
            gui_light = m["gui_light"]
    if generated:
        elements = None
    return textures, elements, gui, gui_light or "side", generated


def texture_ref(textures, ref, depth=0):
    """Follows #variables; 26.x entries may be {"sprite": ..., "force_translucent": ...}."""
    while depth < 16:
        if isinstance(ref, dict):
            ref = ref.get("sprite")
        if not (isinstance(ref, str) and ref.startswith("#")):
            break
        ref = textures.get(ref[1:])
        depth += 1
    return ref if isinstance(ref, str) else None


# ------------------------------------------------------------------ tints (item model definitions)


def tint_color(assets, t):
    typ = t.get("type", "").replace("minecraft:", "")
    if typ == "grass":
        return assets.grass_color(t.get("temperature", 0.5), t.get("downfall", 1.0))
    if typ == "constant":
        v = t.get("value", -1)
    else:  # dye, potion, firework, map_color, team, custom_model_data: their default
        v = t.get("default", -1)
    if isinstance(v, list):
        return tuple(v[:3])
    v &= 0xFFFFFF
    return ((v >> 16 & 255) / 255, (v >> 8 & 255) / 255, (v & 255) / 255)


def pick_models(defn):
    """Model references (with tints) a GUI render of this item definition would use."""
    typ = defn.get("type", "").replace("minecraft:", "")
    if typ == "model":
        return [(defn["model"], defn.get("tints", []))]
    if typ == "composite":
        out = []
        for m in defn.get("models", []):
            out += pick_models(m)
        return out
    if typ == "select":
        if defn.get("property", "").replace("minecraft:", "") == "display_context":
            for case in defn.get("cases", []):
                when = case.get("when")
                if when == "gui" or (isinstance(when, list) and "gui" in when):
                    return pick_models(case["model"])
        if "fallback" in defn:
            return pick_models(defn["fallback"])
        cases = defn.get("cases", [])
        return pick_models(cases[0]["model"]) if cases else []
    if typ == "condition":
        return pick_models(defn["on_false"])
    if typ == "range_dispatch":
        if "fallback" in defn:
            return pick_models(defn["fallback"])
        entries = sorted(defn.get("entries", []), key=lambda e: e.get("threshold", 0))
        return pick_models(entries[0]["model"]) if entries else []
    if typ == "special":
        return [("SPECIAL", defn.get("model", {}))]
    return []


# ------------------------------------------------------------------ flat (builtin/generated)


def render_generated(assets, textures, tints):
    out = None
    i = 0
    while f"layer{i}" in textures:
        ref = texture_ref(textures, textures[f"layer{i}"])
        tex = assets.texture(ref) if ref else None
        if tex is not None:
            layer = tex.copy()
            if i < len(tints):
                layer[..., :3] *= np.array(tint_color(assets, tints[i]), dtype=np.float32)
            if out is None:
                out = np.zeros_like(layer)
            if layer.shape != out.shape:
                layer = np.asarray(Image.fromarray((layer * 255).astype(np.uint8)).resize(out.shape[1::-1], Image.NEAREST),
                                   dtype=np.float32) / 255
            a = layer[..., 3:4]
            out[..., :3] = layer[..., :3] * a + out[..., :3] * (1 - a)
            out[..., 3:4] = a + out[..., 3:4] * (1 - a)
        i += 1
    return out


# ------------------------------------------------------------------ 3D (element models)

# For each face: (corner at texture top-left, "right" axis, "down" axis), in block units 0..16
# as seen from outside the face; matches FaceBakery's default UVs.
def face_frame(face, f, t):
    x0, y0, z0 = f
    x1, y1, z1 = t
    if face == "north":
        return (x1, y1, z0), (x0 - x1, 0, 0), (0, y0 - y1, 0), (0, 0, -1)
    if face == "south":
        return (x0, y1, z1), (x1 - x0, 0, 0), (0, y0 - y1, 0), (0, 0, 1)
    if face == "west":
        return (x0, y1, z0), (0, 0, z1 - z0), (0, y0 - y1, 0), (-1, 0, 0)
    if face == "east":
        return (x1, y1, z1), (0, 0, z0 - z1), (0, y0 - y1, 0), (1, 0, 0)
    if face == "up":
        return (x0, y1, z0), (x1 - x0, 0, 0), (0, 0, z1 - z0), (0, 1, 0)
    if face == "down":
        return (x0, y0, z1), (x1 - x0, 0, 0), (0, 0, z0 - z1), (0, -1, 0)
    raise ValueError(face)


def default_uv(face, f, t):
    x0, y0, z0 = f
    x1, y1, z1 = t
    return {
        "down": [x0, 16 - z1, x1, 16 - z0], "up": [x0, z0, x1, z1],
        "north": [16 - x1, 16 - y1, 16 - x0, 16 - y0], "south": [x0, 16 - y1, x1, 16 - y0],
        "west": [z0, 16 - y1, z1, 16 - y0], "east": [16 - z1, 16 - y1, 16 - z0, 16 - y0],
    }[face]


def element_rotation(el):
    """Returns (matrix, origin) for the element's rotation, or None."""
    r = el.get("rotation")
    if not r:
        return None
    origin = np.array(r.get("origin", [8, 8, 8]), dtype=float)
    if "axis" in r:
        ang = math.radians(r.get("angle", 0))
        m = {"x": _rot_x, "y": _rot_y, "z": _rot_z}[r["axis"]](ang)
        if r.get("rescale"):
            s = 1 / math.cos(ang) if abs(math.cos(ang)) > 1e-6 else 1
            scale = {"x": [1, s, s], "y": [s, 1, s], "z": [s, s, 1]}[r["axis"]]
            m = m @ np.diag(scale)
    else:  # newer format: x/y/z angles
        m = _rot_x(math.radians(r.get("x", 0))) @ _rot_y(math.radians(r.get("y", 0))) @ _rot_z(math.radians(r.get("z", 0)))
    return m, origin


def gui_transform(gui):
    gui = gui or {}
    rx, ry, rz = (math.radians(a) for a in gui.get("rotation", [0, 0, 0]))
    rot = _rot_x(rx) @ _rot_y(ry) @ _rot_z(rz)  # Quaternionf.rotationXYZ
    scale = np.array(gui.get("scale", [1, 1, 1]), dtype=float)
    trans = np.array(gui.get("translation", [0, 0, 0]), dtype=float) / 16
    return rot, scale, trans


def render_elements(assets, textures, elements, gui, gui_light, tints):
    n = SIZE_3D
    color = np.zeros((n, n, 3), dtype=np.float32)
    alpha = np.zeros((n, n), dtype=np.float32)
    depth = np.full((n, n), -1e9, dtype=np.float32)
    rot, scale, trans = gui_transform(gui)
    lights = LIGHTS_3D if gui_light != "front" else LIGHTS_FLAT
    flip = np.diag([1.0, -1.0, 1.0])  # GUI pose: scale(16, -16, 16)

    def to_screen(p):
        v = np.asarray(p, dtype=float) / 16 - 0.5
        v = rot @ (scale * v) + trans
        # 16 GUI px per block, centred in the 16x16 slot; screen y grows downwards
        return np.array([(8 + 16 * v[0]) * n / 16, (8 - 16 * v[1]) * n / 16, v[2]])

    faces = []
    for el in elements:
        f, t = el["from"], el["to"]
        er = element_rotation(el)
        for face, fd in el.get("faces", {}).items():
            ref = el["_texture"] if "_texture" in el else texture_ref(textures, fd.get("texture"))
            tex = assets.texture(ref) if ref else None
            if tex is None:
                continue
            c0, right, down, normal = face_frame(face, f, t)
            c0, right, down, normal = (np.array(c0, float), np.array(right, float), np.array(down, float), np.array(normal, float))
            if er:
                m, o = er
                c0 = m @ (c0 - o) + o
                right, down, normal = m @ right, m @ down, m @ normal
            nv = _norm(flip @ (rot @ normal)) if np.linalg.norm(normal) else normal
            if nv[2] <= 1e-6:
                continue  # back face (Java culls them)
            p0 = to_screen(c0)
            pr = to_screen(c0 + right) - p0
            pd = to_screen(c0 + down) - p0
            uv = fd.get("uv") or default_uv(face, f, t)
            shade = el.get("shade", True) and fd.get("shade", True)
            lv = (light(-nv if el.get("_flip_light") else nv, lights)) if shade else 1.0
            tint = el.get("_tint")
            ti = fd.get("tintindex", -1)
            if ti is not None and 0 <= ti < len(tints):
                tint = tint_color(assets, tints[ti])
            faces.append((p0, pr, pd, tex, uv, fd.get("rotation", 0), lv, tint))

    # back to front, so translucent faces blend over what is behind them
    faces.sort(key=lambda fc: fc[0][2] + (fc[1][2] + fc[2][2]) / 2)
    for p0, pr, pd, tex, uv, uvrot, lv, tint in faces:
        corners = [p0, p0 + pr, p0 + pd, p0 + pr + pd]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        x_lo, x_hi = max(0, int(math.floor(min(xs)))), min(n, int(math.ceil(max(xs))))
        y_lo, y_hi = max(0, int(math.floor(min(ys)))), min(n, int(math.ceil(max(ys))))
        if x_lo >= x_hi or y_lo >= y_hi:
            continue
        a = np.array([[pr[0], pd[0]], [pr[1], pd[1]]])
        if abs(np.linalg.det(a)) < 1e-9:
            continue
        inv = np.linalg.inv(a)
        gx, gy = np.meshgrid(np.arange(x_lo, x_hi) + 0.5, np.arange(y_lo, y_hi) + 0.5)
        dx, dy = gx - p0[0], gy - p0[1]
        s = inv[0, 0] * dx + inv[0, 1] * dy
        tt = inv[1, 0] * dx + inv[1, 1] * dy
        inside = (s >= 0) & (s < 1) & (tt >= 0) & (tt < 1)
        if not inside.any():
            continue
        z = p0[2] + s * pr[2] + tt * pd[2]
        if uvrot == 90:
            su, sv = tt, 1 - s
        elif uvrot == 180:
            su, sv = 1 - s, 1 - tt
        elif uvrot == 270:
            su, sv = 1 - tt, s
        else:
            su, sv = s, tt
        h, w = tex.shape[:2]
        u = (uv[0] + su * (uv[2] - uv[0])) / 16 * w
        v = (uv[1] + sv * (uv[3] - uv[1])) / 16 * h
        ui = np.clip(np.floor(u).astype(int), 0, w - 1)
        vi = np.clip(np.floor(v).astype(int), 0, h - 1)
        texel = tex[vi, ui]
        ta = texel[..., 3]
        ok = inside & (ta >= 0.1) & (z > depth[y_lo:y_hi, x_lo:x_hi] - 1e-6)
        if not ok.any():
            continue
        rgb = texel[..., :3] * lv
        if tint is not None:
            rgb = rgb * np.array(tint, dtype=np.float32)
        reg_c = color[y_lo:y_hi, x_lo:x_hi]
        reg_a = alpha[y_lo:y_hi, x_lo:x_hi]
        reg_d = depth[y_lo:y_hi, x_lo:x_hi]
        aa = np.where(ok, ta, 0)[..., None]
        reg_c[...] = rgb * aa + reg_c * (1 - aa)
        reg_a[...] = np.where(ok, ta + reg_a * (1 - ta), reg_a)
        reg_d[...] = np.where(ok & (ta > 0.99), z, reg_d)
    # colour was composited onto transparent black (premultiplied): back to straight alpha
    straight = np.where(alpha[..., None] > 0, color / np.maximum(alpha[..., None], 1e-6), 0)
    return np.concatenate([straight, alpha[..., None]], axis=-1)


# ------------------------------------------------------------------ block-entity items (special renderers)


def box(frm, size, uv, texture, tex_size, inflate=0.0, flip_tb=False, tint=None, front="south",
        scale=1.0, offset=(0, 0, 0), flip_light=False):
    """A model-part cube as a block-model element, with Java's box UV layout
    (ModelPart.Cube): the front texture on the south face, the top region's lower edge at the front."""
    (x, y, z), (w, h, d), (u, v), (tw, th) = frm, size, uv, tex_size

    def r(u0, v0, u1, v1):
        return [u0 * 16 / tw, v0 * 16 / th, u1 * 16 / tw, v1 * 16 / th]
    faces = {
        "south": r(u + d, v + d, u + d + w, v + d + h),
        "west": r(u, v + d, u + d, v + d + h),
        "east": r(u + d + w, v + d, u + 2 * d + w, v + d + h),
        "north": r(u + 2 * d + w, v + d, u + 2 * d + 2 * w, v + d + h),
        "up": r(u + d, v, u + d + w, v + d),
        "down": r(u + d + w, v, u + d + 2 * w, v + d),
    }
    if front == "north":  # the part faces -z (turned around)
        faces["south"], faces["north"] = faces["north"], faces["south"]
        faces["east"], faces["west"] = faces["west"], faces["east"]
    if flip_tb:  # chest textures are laid out upside down
        faces["up"], faces["down"] = faces["down"], faces["up"]
    lo = [(c - inflate) * scale + o for c, o in zip((x, y, z), offset)]
    hi = [(c + e + inflate) * scale + o for c, e, o in zip((x, y, z), (w, h, d), offset)]
    el = {"from": lo, "to": hi,
          "faces": {f: {"texture": "#t", "uv": uvs} for f, uvs in faces.items()}, "_texture": texture}
    if tint:
        el["_tint"] = tint
    if flip_light:
        el["_flip_light"] = True
    return el


DYES = {"white": 0xF9FFFE, "orange": 0xF9801D, "magenta": 0xC74EBD, "light_blue": 0x3AB3DA, "yellow": 0xFED83D,
        "lime": 0x80C71F, "pink": 0xF38BAA, "gray": 0x474F52, "light_gray": 0x9D9D97, "cyan": 0x169C9C,
        "purple": 0x8932B8, "blue": 0x3C44AA, "brown": 0x835432, "green": 0x5E7C16, "red": 0xB02E26,
        "black": 0x1D1D21}  # DyeColor texture diffuse colours


HEADS = {  # kind: (texture, head width, hat layer?)
    "skeleton": ("minecraft:entity/skeleton/skeleton", 8, False),
    "wither_skeleton": ("minecraft:entity/skeleton/wither_skeleton", 8, False),
    "zombie": ("minecraft:entity/zombie/zombie", 8, True),
    "creeper": ("minecraft:entity/creeper/creeper", 8, False),
    "piglin": ("minecraft:entity/piglin/piglin", 10, False),
    "player": ("minecraft:entity/player/wide/steve", 8, True),
}
SKULL_GUI = {"rotation": [30, 45, 0], "translation": [0, 3, 0], "scale": [1, 1, 1]}   # item/template_skull
CHEST_GUI = {"rotation": [30, 45, 0], "translation": [0, 0, 0], "scale": [0.625, 0.625, 0.625]}  # template_chest/_shulker_box
# item/shield and item/template_banner. Their item transformations scale by -1 on two axes, and Java
# ends up lighting them with the opposite normals (flip_light), which is why their fronts look bright.
SHIELD_GUI = {"rotation": [15, 25, 5],  # mirrored vs item/shield, matches Java's icon
              "translation": [2, 3, 0], "scale": [0.65, 0.65, 0.65]}
BANNER_GUI = {"rotation": [30, 20, 0], "translation": [0, -3.25, 0], "scale": [0.5325] * 3}


def special_model(assets, spec):
    """(elements, gui) for the block-entity item renderers that are plain boxes, else None."""
    typ = spec.get("type", "").replace("minecraft:", "")
    if typ == "head" and spec.get("kind") == "dragon":  # DragonHeadModel: the 16px head box and the snout
        tex = "minecraft:entity/enderdragon/dragon"
        ts = (256, 256)
        # item/dragon_head is [30, 45, 0] at 0.6; smaller here, the snout is drawn full length
        gui = {"rotation": [30, 45, 0], "translation": [1, 2, 0], "scale": [0.42, 0.42, 0.42]}
        return [box((0, 0, -8), (16, 16, 16), (112, 30), tex, ts),
                box((2, 4, 8), (12, 5, 16), (176, 44), tex, ts),
                box((2, 0, 8), (12, 4, 16), (176, 65), tex, ts)], gui
    if typ in ("head", "player_head"):
        kind = "player" if typ == "player_head" else spec.get("kind", "")
        if kind not in HEADS:
            return None
        tex, w, hat = HEADS[kind]
        size = assets.texture(tex).shape
        ts = (size[1], size[0])
        x0 = 8 - w / 2
        els = [box((x0, 0, 4), (w, 8, 8), (0, 0), tex, ts)]
        if hat:
            els.append(box((x0, 0, 4), (w, 8, 8), (32, 0), tex, ts, inflate=0.25))
        return els, SKULL_GUI
    if typ == "conduit":  # the closed shell (ConduitRenderer shell 6x6x6)
        tex = "minecraft:entity/conduit/base"
        return [box((5, 5, 5), (6, 6, 6), (0, 0), tex, (32, 16))], {"rotation": [30, 45, 0], "scale": [1, 1, 1]}
    if typ == "copper_golem_statue":
        tex = spec.get("texture", "minecraft:textures/entity/copper_golem/copper_golem.png")
        tex = "minecraft:" + tex.split(":")[-1].replace("textures/", "", 1).rsplit(".png", 1)[0]
        eyes = tex.replace("copper_golem/copper_golem", "copper_golem/copper_golem_eyes")
        ts = (64, 64)
        parts = []  # CopperGolemModel.createBodyLayer: (texOffs, box min, size, part offset), model y down, root +24
        for (u, v), (x, y, z), (w, h, d), (ox, oy, oz) in (
                ((0, 15), (-4, -6, -3), (8, 6, 6), (0, 19, 0)),       # body
                ((0, 0), (-4, -5, -5), (8, 5, 10), (0, 13, 0)),       # head
                ((56, 0), (-1, -2, -6), (2, 3, 2), (0, 13, 0)),       # nose
                ((37, 8), (-1, -9, -1), (2, 4, 2), (0, 13, 0)),       # antenna
                ((37, 0), (-2, -13, -2), (4, 4, 4), (0, 13, 0)),      # antenna knob
                ((36, 16), (-3, -1, -2), (3, 10, 4), (-4, 13, 0)),    # right arm
                ((50, 16), (0, -1, -2), (3, 10, 4), (4, 13, 0)),      # left arm
                ((0, 27), (-4, 0, -2), (4, 5, 4), (0, 19, 0)),        # right leg
                ((16, 27), (0, 0, -2), (4, 5, 4), (0, 19, 0))):       # left leg
            # flipped upright about X (front to +z), centred on the block
            fx, fy, fz = x + ox + 8, 24 - (y + oy + h), -(z + oz + d) + 8
            parts.append(box((fx, fy, fz), (w, h, d), (u, v), tex, ts))
            if (u, v) == (0, 0):
                parts.append(box((fx, fy, fz), (w, h, d), (u, v), eyes, ts, inflate=0.01))
        # item/template_copper_golem_statue: [30, 45, 180] on the y-down model (face front-left, like heads)
        return parts, {"rotation": [30, 45, 0], "translation": [0, -0.7, 0], "scale": [0.55, 0.55, 0.55]}
    if typ == "shulker_box":
        tex = "minecraft:entity/shulker/" + spec.get("texture", "minecraft:shulker").split(":")[-1]
        ts = (64, 64)
        base = box((0, 0, 0), (16, 8, 16), (0, 28), tex, ts)
        lid = box((0, 4, 0), (16, 12, 16), (0, 0), tex, ts)
        return [base, lid], CHEST_GUI
    if typ == "chest":
        tex = "minecraft:entity/chest/" + spec.get("texture", "minecraft:normal").split(":")[-1]
        ts = (64, 64)
        return [box((1, 0, 1), (14, 10, 14), (0, 19), tex, ts, flip_tb=True),
                box((1, 9, 1), (14, 5, 14), (0, 0), tex, ts, flip_tb=True),
                box((7, 7, 15), (2, 4, 1), (0, 0), tex, ts, flip_tb=True)], CHEST_GUI
    if typ == "shield":
        tex = "minecraft:entity/shield/shield_base_nopattern"
        ts = (64, 64)
        # ShieldModel plate 12x22x1 and handle 2x6x6, centred in the block like the item shows it
        return [box((2, -3, 8), (12, 22, 1), (0, 0), tex, ts, flip_light=True),
                box((7, 5, 2), (2, 6, 6), (26, 0), tex, ts, flip_light=True)], SHIELD_GUI
    if typ == "banner":
        color = DYES.get(spec.get("color", "white"), 0xFFFFFF)
        rgb = ((color >> 16 & 255) / 255, (color >> 8 & 255) / 255, (color & 255) / 255)
        base, cloth = "minecraft:entity/banner/banner_base", "minecraft:entity/banner/base"
        ts = (64, 64)
        # BannerFlagModel, flipped upright, scaled 2/3 about the item origin and moved to (8, 0, 8)
        k, o = 2 / 3, (8, 8, 8)  # pole stands on the ground: model y + 12, times 2/3
        flag = (-10, -10, 1), (20, 40, 1)
        kw = dict(scale=k, offset=o, flip_light=True)
        return [box((-1, -12, -1), (2, 42, 2), (44, 0), base, ts, **kw),
                box((-10, 30, -1), (20, 2, 2), (0, 42), base, ts, **kw),
                box(flag[0], flag[1], (0, 0), base, ts, **kw),
                box(flag[0], flag[1], (0, 0), cloth, ts, inflate=0.01, tint=rgb, **kw)], BANNER_GUI
    return None


def render_special(assets, spec):
    m = special_model(assets, spec)
    if m is None:
        return None
    elements, gui = m
    return render_elements(assets, {}, elements, gui, "side", [])


def _over(top, bottom):
    a = top[..., 3:4]
    return np.concatenate([top[..., :3] * a + bottom[..., :3] * (1 - a), a + bottom[..., 3:4] * (1 - a)], axis=-1)


# ------------------------------------------------------------------ driver


def render_item(assets, defn):
    """Returns an RGBA float array, or None (special renderer / missing)."""
    parts = pick_models(defn["model"])
    if not parts:
        return None
    result = None
    for ref, tints in parts:
        if ref == "SPECIAL":
            return render_special(assets, tints)
        textures, elements, gui, gui_light, generated = resolve_model(assets, ref)
        if generated:
            img = render_generated(assets, textures, tints)
        elif elements:
            img = render_elements(assets, textures, elements, gui, gui_light, tints)
        else:
            img = None
        if img is None:
            continue
        if result is None:
            result = img
        else:  # composite: draw over (bring both to the larger size)
            if img.shape != result.shape:
                big = max(img.shape[0], result.shape[0])
                rs = lambda a: np.asarray(Image.fromarray((a * 255).astype(np.uint8)).resize((big, big), Image.NEAREST), dtype=np.float32) / 255
                img, result = (rs(img) if img.shape[0] != big else img), (rs(result) if result.shape[0] != big else result)
            a = img[..., 3:4]
            result = np.concatenate([img[..., :3] * a + result[..., :3] * (1 - a), a + result[..., 3:4] * (1 - a)], axis=-1)
    return result


def main():
    render_all(sys.argv[1], sys.argv[2])


def render_all(root, out):
    os.makedirs(out, exist_ok=True)
    assets = Assets(root)
    index, skipped = {}, []
    base = os.path.join(root, "assets")
    for ns in sorted(os.listdir(base)):
        items_dir = os.path.join(base, ns, "items")
        if not os.path.isdir(items_dir):
            continue
        for fn in sorted(os.listdir(items_dir)):
            if not fn.endswith(".json"):
                continue
            item = fn[:-5]
            try:
                img = render_item(assets, json.load(open(os.path.join(items_dir, fn))))
            except Exception as e:  # keep going; report at the end
                skipped.append(f"{ns}:{item} ({e})")
                continue
            if img is None or img[..., 3].max() <= 0:
                skipped.append(f"{ns}:{item}")
                continue
            name = item if ns == "minecraft" else f"{ns}_{item}"
            Image.fromarray(np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8), "RGBA").save(os.path.join(out, name + ".png"))
            index[f"{ns}:{item}"] = name
    json.dump(index, open(os.path.join(out, "index.json"), "w"), indent=0, sort_keys=True)
    print(f"rendered {len(index)} icons, skipped {len(skipped)}")
    if skipped:
        print("skipped:", ", ".join(skipped))


if __name__ == "__main__":
    main()
