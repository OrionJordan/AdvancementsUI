#!/usr/bin/env python3
"""Builds the "Advancements UI" Bedrock resource pack.

The pack restyles one specific Geyser form (title starting with ADVGUI:) into a copy of the
Java Edition advancements screen. All layout data comes from the AdvancementsUI Geyser
extension, encoded in each button's text (see extension Item.java for the format).

usage: build_pack.py [--java-icons] <unpacked Java client jar dir> <output dir> [version, default 1.0.0]

Item icons are drawn by the Bedrock client's own item renderer. --java-icons also renders Java's GUI
icons into the pack (render_icons.py, about 2.5 MB more); the extension then prefers those.
"""
import json
import os
import shutil
import sys

from PIL import Image, ImageDraw

NUMBERS = 8         # must match Item.NUMBERS
KIND = 1 + 4 * NUMBERS + 1      # kind letter (after 'Q', the numbers and 'Z')
FLAG = KIND + 1                 # first of seven flag letters (Item.FLAGS)
ICON = FLAG + 7                 # '1': the image path is a Bedrock item (Item.withIcon)
HEADER = ICON + 1               # must match Item.HEADER
LINE_H = 9          # glyph height incl. shadow (Java's line height)
TEXT_LINE = 10      # distance between lines of a multi-line Bedrock label (Java: 9); must match
                    # AdvancementScreen.LINE
VIEW_W, VIEW_H = 234, 113   # Java's inner window (AdvancementsScreen.WINDOW_INSIDE_*)
MAX_TABS = 26       # Java: 8 above + 8 below + 5 left + 5 right per page
# ADV_DEBUG_TIPS=1: show every tooltip permanently (to check layout in one screenshot)
DEBUG_TIPS = os.environ.get("ADV_DEBUG_TIPS") == "1"
NS = 'adv_gui'
TEX = 'textures/ui/adv_gui/'
T = '#form_button_text'

HEADER_UUID = 'e23151e7-32b2-4d63-a75f-4680da652f53'
MODULE_UUID = 'e25f16bb-26b8-4497-8229-ceefb3657c0b'


# ------------------------------------------------------------------ expression helpers
#
# Button text layout (see Item.java):  Q n0..n7 Z k abcdef i <payload>
#   0     'Q'. JSON UI evaluates any string that starts with digits as a number, so the text must
#         start with a letter for slicing ('%.Ns' prefixes, string subtraction) to stay textual.
#   1..32 eight 4-digit numbers, cut out by subtracting prefixes and made numeric with "+ 0"
#         (x, y; nodes: tooltip x, tooltip y, description box height, description y, tooltip
#         width, description clip height)
#   33    'Z', 34 kind (KIND), 35..41 flags (FLAG), 42 icon kind (ICON), 43.. payload


def number(i):
    return f"((('%.{5 + 4 * i}s' * {T}) - ('%.{1 + 4 * i}s' * {T})) + 0)"


NX, NY = number(0), number(1)
NTX, NTY, NBH, NDY, NTW, NDH = number(2), number(3), number(4), number(5), number(6), number(7)
BIAS = 1000     # Item: possibly negative numbers are sent + 1000
POS_BIAS = 5000     # AdvancementScreen.POS_BIAS: the drag range box position is sent + 5000
POS_SHIFT = 8192    # spacers can't be negative: the box's stacks start this far up/left


def ch(i):
    """JSON UI expression for the i-th character of the button text."""
    return f"(('%.{i + 1}s' * {T}) - ('%.{i}s' * {T}))"


def is_char(i, c):
    return f"({ch(i)} = '{c}')"


def coll(name=T):
    return {"binding_type": "collection", "binding_collection_name": "form_buttons", "binding_name": name}


def view(expr, target, source=None):
    b = {"binding_type": "view", "source_property_name": expr, "target_property_name": target}
    if source:
        b["source_control_name"] = source
    return b


def texture_from(prefix, idx, suffix=""):
    """Bindings that set #texture = prefix + chars at `idx` + suffix. Each character goes through
    its own property first: a literal and prefix subtractions in one expression lose the literal."""
    bs = [coll()] + [view(ch(i), f"#c{i}") for i in idx]
    expr = f"('{prefix}'" + "".join(f" + #c{i}" for i in idx) + (f" + '{suffix}'" if suffix else "") + ")"
    return {"property_bag": {f"#c{i}": "" for i in idx}, "bindings": bs + [view(expr, "#texture")]}


def visible_if(expr):
    return [coll(), view(expr, "#visible")]


PAYLOAD = f"({T} - ('%.{HEADER}s' * {T}))"


def spacer(axis, expr, extra_bindings=()):
    """Zero-size panel whose width (axis x) or height (y) is the number `expr` in pixels."""
    prop = f"#size_binding_{axis}_absolute"
    return {"type": "panel", "size": [0, 0], "property_bag": {prop: 0},
            "bindings": [coll(), *extra_bindings, view(expr, prop)]}


def positioned(content):
    """Places `content` (dict of one control) at the X/Y numbers of the button text."""
    row = {"type": "stack_panel", "orientation": "horizontal", "size": ["100%c", "100%cm"],
           "controls": [{"xs": spacer("x", NX)}, content]}
    return {"type": "stack_panel", "orientation": "vertical", "size": ["100%cm", "100%c"],
            "anchor_from": "top_left", "anchor_to": "top_left",
            "controls": [{"ys": spacer("y", NY)}, {"row": row}]}


def texture_binding(expr):
    return view(expr, "#texture")


def solid(color, size, offset=(0, 0), layer=1, alpha=None):
    """1x1 black/white texture stretched to `size`."""
    d = {"type": "image", "texture": TEX + ("line_Hk" if color == 'k' else "line_Hw"), "keep_ratio": False,
         "size": list(size), "offset": list(offset), "layer": layer,
         "anchor_from": "top_left", "anchor_to": "top_left"}
    if alpha is not None:
        d["alpha"] = alpha
    return d


ITEM_ID_BIAS = 50000   # must match Item.ITEM_ID_BIAS


def icon_image(offset, anchor="top_left", layer=4):
    """A 16x16 icon. The button's image path is either a texture, or 'Q' + runtime id + 50000 and the
    damage value (5 digits each, Item.itemRenderer): then the client's own inventory item renderer
    draws the Bedrock item (3D blocks included), so the pack ships no item icons.

    The header's ICON digit picks the variant by sizing the other one to 0x0. (Visibility bindings
    don't work inside the node button's hover control, where the tooltip draws the icon again.)"""
    tex = {"binding_type": "collection", "binding_collection_name": "form_buttons",
           "binding_name": "#form_button_texture", "binding_name_override": "#tex"}
    image = {"type": "image", "size": ["100%", "100%"], "layer": 1,
             "bindings": [
                 {"binding_type": "collection", "binding_collection_name": "form_buttons",
                  "binding_name": "#form_button_texture", "binding_name_override": "#texture"},
                 {"binding_type": "collection", "binding_collection_name": "form_buttons",
                  "binding_name": "#form_button_texture_file_system", "binding_name_override": "#texture_file_system"},
             ]}
    # #item_id_aux = id * 65536 + aux, each part in its own property first (see the README findings)
    item = {"type": "custom", "renderer": "inventory_item_renderer", "size": ["100%", "100%"], "layer": 1,
            "property_bag": {"#tex": "", "#iid": 0, "#iaux": 0, "#item_id_aux": 0},
            "bindings": [tex,
                         view(f"(((('%.6s' * #tex) - 'Q') + 0) - {ITEM_ID_BIAS})", "#iid"),
                         view("((#tex - ('%.6s' * #tex)) + 0)", "#iaux"),
                         view("((#iid * 65536) + #iaux)", "#item_id_aux")]}

    def variant(control, size_expr):
        return {"type": "panel", "size": [0, 0], "clips_children": True,
                "anchor_from": "top_left", "anchor_to": "top_left",
                "property_bag": {"#f": 0, "#size_binding_x_absolute": 0, "#size_binding_y_absolute": 0},
                "bindings": [coll(), view(f"({ch(ICON)} + 0)", "#f"),
                             view(size_expr, "#size_binding_x_absolute"), view(size_expr, "#size_binding_y_absolute")],
                "controls": [{"i": control}]}

    return {"type": "panel", "size": [16, 16], "offset": offset, "anchor_from": anchor, "anchor_to": anchor,
            "layer": layer,
            "controls": [{"img": variant(image, "(16 - (#f * 16))")}, {"item": variant(item, "(#f * 16)")}]}


def label(text_expr, color=(1, 1, 1), offset=(0, 0), anchor="top_left", layer=3, shadow=False):
    return {"type": "label", "size": ["default", "default"], "offset": list(offset),
            "anchor_from": anchor, "anchor_to": anchor, "layer": layer, "color": list(color),
            "shadow": shadow, "font_type": "default", "text": "#text",
            "bindings": [coll(), view(text_expr, "#text")]}


def meta(name, control, size=("100%", "100%"), index=0):
    """Lets `control` read one fixed button (default: button 0, the meta item). collection_index
    only works on direct children of a stack_panel that declares collection_name."""
    c = dict(control)
    c["collection_index"] = index
    return {"type": "stack_panel", "orientation": "vertical", "size": list(size),
            "collection_name": "form_buttons", "controls": [{name: c}]}


# ------------------------------------------------------------------ tooltip (AdvancementWidget#extractHover)

def place(content, x, y, name="c"):
    """Puts `content` at (x, y): number expressions that may be negative (spacers in stacks shifted
    by -1024), or plain ints (static: expressions made only of literals don't evaluate)."""
    def sp(axis, v):
        if isinstance(v, int):
            return {"type": "panel", "size": [v + 1024, 0] if axis == "x" else [0, v + 1024]}
        return spacer(axis, f"({v} + 1024)")
    row = {"type": "stack_panel", "orientation": "horizontal", "size": ["100%c", "100%cm"],
           "controls": [{"xs": sp("x", x)}, {name: content}]}
    return {"type": "stack_panel", "orientation": "vertical", "size": ["100%cm", "100%c"],
            "anchor_from": "top_left", "anchor_to": "top_left", "offset": [-1024, -1024],
            "controls": [{"ys": sp("y", y)}, {"row": row}]}


def bound_size(w_expr, h_expr, extra=None):
    """Fields for a control whose size (pixels) comes from number expressions (None: fixed 0)."""
    d = {"size": [0, 0], "property_bag": {}, "bindings": [coll()]}
    for axis, e in (("x", w_expr), ("y", h_expr)):
        if e is None:
            continue
        if isinstance(e, int):
            d["size"][0 if axis == "x" else 1] = e
            continue
        d["property_bag"][f"#size_binding_{axis}_absolute"] = 0
        d["bindings"].append(view(e, f"#size_binding_{axis}_absolute"))
    return d


def tooltip():
    """AdvancementWidget#extractHover, relative to the node's 26x26 hit area (cell x + 3).

    The server sends the geometry Java computes: where the tooltip starts (to the right of the
    node, or ending at x + 32 when flipped left; up or down), its width, the description box height
    (32 + 10 per line, Bedrock's line spacing), where the description text starts and how tall its clip is. Sizes taken from
    the text itself came out too small at times (the text then wrapped and spilled out of the box),
    so every size is sent and the labels are wide enough never to wrap.
    """
    wide = [1024, "default"]  # never wraps; the clips around it cut it to the box
    title_label = dict(label(PAYLOAD, layer=1, shadow=True), size=wide)
    title_clip = dict({"type": "panel", "clips_children": True,
                       "anchor_from": "top_left", "anchor_to": "top_left", "offset": [5, 9],
                       "controls": [{"title": title_label}]},
                      **bound_size(f"({NTW} - 6)", LINE_H))
    bar = dict({"type": "image", "layer": 2, "anchor_from": "top_left", "anchor_to": "top_left",
                "controls": [{"title_clip": title_clip}]},
               **bound_size(NTW, 26))
    bar_tex = texture_from(TEX + "box_N", (FLAG, FLAG + 1))
    bar["property_bag"].update(bar_tex["property_bag"])
    bar["bindings"] += bar_tex["bindings"]
    # The description is the label minus its first line: shifted up inside a clip that starts two
    # pixels lower (so the title's shadow and descenders don't peek in).
    desc_label = dict(label(PAYLOAD, offset=(0, -(TEXT_LINE + 2)), layer=1, shadow=True), size=wide)
    desc_clip = dict({"type": "panel", "clips_children": True, "anchor_from": "top_left", "anchor_to": "top_left",
                      "controls": [{"desc": desc_label}]},
                     **bound_size(f"({NTW} - 6)", NDH))
    text = {"type": "stack_panel", "orientation": "vertical", "size": [1024, 1024],
            "anchor_from": "top_left", "anchor_to": "top_left", "layer": 1,
            "controls": [{"ys": spacer("y", f"({NDY} - {BIAS})")},
                         {"indent": {"type": "stack_panel", "orientation": "horizontal", "size": [1024, 1024],
                                     "controls": [{"x5": {"type": "panel", "size": [5, 0]}},
                                                  {"clip": desc_clip}]}}]}
    box = dict({"type": "image", "texture": TEX + "title_box", "layer": 1, "clips_children": True,
                "anchor_from": "top_left", "anchor_to": "top_left", "controls": [{"text": text}]},
               **bound_size(NTW, NBH))
    # box at (tx, ty); the bar at the node's row, i.e. (tx, 0)
    content = {"type": "panel", "size": ["100%c", "100%c"], "layer": 1,
               "anchor_from": "top_left", "anchor_to": "top_left",
               "controls": [{"box": place(box, f"({NTX} - {BIAS})", f"({NTY} - {BIAS})", "box")},
                            {"bar": place(bar, f"({NTX} - {BIAS})", 0, "bar")}]}
    # the hovered widget is drawn again on top of the bar (Java: frame + icon over the tooltip)
    frame = {"type": "image", "size": [26, 26], "layer": 6, "anchor_from": "top_left", "anchor_to": "top_left",
             **texture_from(TEX + "frame_N", (FLAG, FLAG + 1))}
    # Only the box, bar and frame are lazy; the icon's bindings stay eager (with "visible" conditions
    # it stayed blank).
    icon = icon_image([5, 5], layer=7)
    return {"type": "panel", "size": [26, 26], "layer": 60,
            "controls": [{"content": lazy(content)}, {"frame": lazy(frame)}, {"icon": icon}]}


def lazy(control):
    """binding_condition "visible" on every binding in a subtree: the tooltip's bindings are only
    evaluated while it is shown (a big share of the per-node cost otherwise)."""
    if isinstance(control, dict):
        for k, v in control.items():
            if k == "bindings" and isinstance(v, list):
                for b in v:
                    if isinstance(b, dict) and b.get("binding_type") != "collection_details":
                        b.setdefault("binding_condition", "visible")
            else:
                lazy(v)
    elif isinstance(control, list):
        for v in control:
            lazy(v)
    return control


def hover_button():
    """The node's invisible 26x26 hit area; its hover state shows the tooltip."""
    # Java dims the whole tab (black, alpha 0.3) while a widget is hovered, below the tooltip.
    dim = dict(solid('k', [4096, 4096], layer=40, alpha=0.3), anchor_from="center", anchor_to="center")
    holder = {"type": "panel", "size": [26, 26], "controls": [{"dim": dim}, {"tip": tooltip()}]}
    return {
        "type": "button", "size": [26, 26], "layer": 5, "offset": [3, 0],
        "anchor_from": "top_left", "anchor_to": "top_left",
        "default_control": "default", "hover_control": "hover", "pressed_control": "hover",
        "locked_control": "", "sound_name": "", "focus_enabled": False,
        # a press on a node must still start dragging the canvas (Java): no mappings for the mouse
        # button or the controller's A (menu_select / menu_ok), and don't consume the input
        "consume_event": False, "consume_hover_events": False,
        "controls": [
            {"default": holder if DEBUG_TIPS else {"type": "panel"}},
            {"hover": holder},
        ]}


# ------------------------------------------------------------------ canvas items

def nav_anchor():
    """The node's D-pad focus target, under the hit area: Bedrock's focus navigation moves the
    gamepad pointer onto it, so the hit area above is hovered and shows the tooltip. Navigation in
    the view is instant and client-side; Bedrock skips clipped nodes, though, and JSON UI can't
    scroll the view to the focus. So the server marks a node in the view as an edge (flag 7: l, r,
    u, d) when no other visible node lies that way but hidden ones do; that variant's mapping turns
    the press into a form response and the server sends the screen centred on the next node that
    way (AdvancementScreen#edge)."""
    def anchor(mappings):
        return {"type": "button", "size": [26, 26], "offset": [3, 0], "layer": 1,
                "anchor_from": "top_left", "anchor_to": "top_left", "focus_enabled": True,
                "default_control": "", "hover_control": "", "pressed_control": "", "locked_control": "",
                "sound_name": "", "consume_event": False, "consume_hover_events": False,
                "button_mappings": mappings,
                "bindings": [{"binding_type": "collection_details", "binding_collection_name": "form_buttons"}]}
    variants = [{"plain": {"type": "panel", "size": [28, 27], "bindings": visible_if(is_char(FLAG + 6, 'x')),
                           "controls": [{"a": anchor([])}]}}]
    for d, b in (("l", "left"), ("r", "right"), ("u", "up"), ("d", "down")):
        m = [{"from_button_id": f"button.menu_{b}", "to_button_id": "button.form_button_click",
              "mapping_type": "focused"}]
        variants.append({f"edge_{d}": {"type": "panel", "size": [28, 27],
                                       "bindings": visible_if(is_char(FLAG + 6, d)),
                                       "controls": [{"a": anchor(m)}]}})
    return {"type": "panel", "size": [28, 27], "layer": 1, "controls": variants}


def node_cell():
    """28x27 cell of one advancement: connector stubs, frame, icon, hover areas.

    Connector pixels are AdvancementWidget#extractConnectivity relative to this cell: a child sits
    exactly one column (28px) right of its parent, so its stub and the parent's stub have fixed
    shapes. Only the vertical trunk varies; it is a separate 'L' item.
    """
    stub_child = {"type": "panel", "size": [28, 27], "bindings": visible_if(is_char(FLAG + 4, 'y')),
                  "controls": [{"k": solid('k', [13, 3], (1, 12), layer=1)},
                               {"w": solid('w', [12, 1], (2, 13), layer=2)}]}
    stub_parent = {"type": "panel", "size": [28, 27], "bindings": visible_if(is_char(FLAG + 5, 'y')),
                   "controls": [{"k": {"type": "image", "texture": TEX + "stub_parent", "size": [19, 3],
                                       "offset": [13, 12], "layer": 1, "keep_ratio": False,
                                       "anchor_from": "top_left", "anchor_to": "top_left"}},
                                {"w": solid('w', [18, 1], (13, 13), layer=2)}]}
    return {
        "type": "panel", "size": [28, 27], "bindings": visible_if(is_char(KIND, 'N')),
        "controls": [
            {"stub_c": stub_child},
            {"stub_p": stub_parent},
            {"frame": {"type": "image", "size": [26, 26], "offset": [3, 0], "layer": 3,
                       "anchor_from": "top_left", "anchor_to": "top_left",
                       **texture_from(TEX + "frame_N", (FLAG, FLAG + 1))}},
            {"icon": icon_image([8, 5], layer=4)},
            {"hit": hover_button()},
            {"nav": nav_anchor()},
        ]}


def trunk_cell():
    """Vertical connector: black x, white x+1, black x+2; length = number in the texture string."""
    tex = {"binding_type": "collection", "binding_collection_name": "form_buttons",
           "binding_name": "#form_button_texture", "binding_name_override": "#tex"}
    length = "(('%.4s' * #tex) + 0)"

    def col(color, off, layer, width):
        d = solid(color, [width, 0], (off, 0), layer=layer)
        d["property_bag"] = {"#size_binding_y_absolute": 0, "#tex": ""}
        d["bindings"] = [tex, view(length, "#size_binding_y_absolute")]
        return d

    return {"type": "panel", "size": [3, 0], "bindings": visible_if(is_char(KIND, 'L')),
            "anchor_from": "top_left", "anchor_to": "top_left",
            "controls": [{"k": col('k', 0, 1, 3)}, {"w": col('w', 1, 2, 1)}]}


def canvas_item():
    cell = {"type": "panel", "size": [28, 27],
            "controls": [{"node": node_cell()}, {"trunk": trunk_cell()}]}
    return {"type": "panel", "size": [0, 0], "anchor_from": "top_left", "anchor_to": "top_left",
            "controls": [{"pos": positioned({"cell": cell})}]}


# ------------------------------------------------------------------ tabs (AdvancementTabType)

TAB_TYPES = {
    # type: (count, size, icon offset)
    'a': (8, [28, 32], [6, 9]),
    'b': (8, [28, 32], [6, 6]),
    'l': (5, [32, 28], [10, 5]),
    'r': (5, [32, 28], [6, 5]),
}


def tab_tooltip():
    # Java draws the tab name at the cursor; we pin it just right of the tab, inside the screen.
    return {"type": "image", "texture": TEX + "tooltip", "layer": 80,
            "size": ["100%c + 8px", "100%c + 8px"], "offset": [2, 10],
            "anchor_from": "top_right", "anchor_to": "top_left",
            "controls": [{"text": label(PAYLOAD, offset=(4, 4), layer=1, shadow=True)}]}


def tab_slot(t, i):
    """Tab i of type t at its fixed Java position (AdvancementTabType#getX/getY)."""
    count, size, icon_off = TAB_TYPES[t]
    variant = 'l' if i == 0 else ('r' if i == count - 1 else 'm')
    along = 32 * i
    if t == 'a':
        place = {"anchor_from": "top_left", "anchor_to": "bottom_left", "offset": [along, 4]}
    elif t == 'b':
        place = {"anchor_from": "bottom_left", "anchor_to": "top_left", "offset": [along, -4]}
    elif t == 'l':
        place = {"anchor_from": "top_left", "anchor_to": "top_right", "offset": [4, along]}
    else:
        place = {"anchor_from": "top_right", "anchor_to": "top_left", "offset": [-4, along]}
    def button(bumpers=()):
        mappings = [
            {"from_button_id": "button.menu_select", "to_button_id": "button.form_button_click", "mapping_type": "pressed"},
            {"from_button_id": "button.menu_ok", "to_button_id": "button.form_button_click", "mapping_type": "focused"}]
        # controller: LB/RB anywhere on the screen press the previous/next tab
        mappings += [{"from_button_id": b, "to_button_id": "button.form_button_click", "mapping_type": "global"}
                     for b in bumpers]
        return {
            "type": "button", "size": size, "layer": 3,
            "default_control": "default", "hover_control": "hover", "pressed_control": "hover", "locked_control": "",
            "sound_name": "random.click",
            "button_mappings": mappings,
            "bindings": [{"binding_type": "collection_details", "binding_collection_name": "form_buttons"}],
            "controls": [
                {"default": {"type": "panel"}},
                {"hover": {"type": "panel", "controls": [{"tip": tab_tooltip()}]}},
                {"sprite": {"type": "image", "size": size, "layer": 1,
                            **texture_from(TEX + "tab_T", (FLAG,), variant + t)}},
                {"icon": icon_image(icon_off, layer=2)},
            ]}
    # The open tab is drawn the same but is not a button: Java ignores clicks on it.
    plain = button()
    selected = {"type": "panel", "size": size, "bindings": visible_if(is_char(FLAG, 'y')),
                "controls": [c for c in plain["controls"] if "sprite" in c or "icon" in c]}
    # Other tabs; the server marks the open tab's neighbours (flag 2: l previous, r next, b both).
    left, right = "button.menu_tab_left", "button.menu_tab_right"
    others = []
    for flag, bumpers in (("x", ()), ("l", (left,)), ("r", (right,)), ("b", (left, right))):
        others.append({f"other_{flag}": {
            "type": "panel", "size": size,
            "bindings": visible_if(f"({is_char(FLAG, 'n')} and {is_char(FLAG + 1, flag)})"),
            "controls": [{"tab": plain if not bumpers else button(bumpers)}]}})
    return dict(place, type="panel", size=size, controls=others + [{"open_tab": selected}])


def chrome():
    """Button 0 = meta (canvas size), 1 = drag range, 2..27 = tabs in Java order (above, below, left, right)."""
    slots = [{"meta": {"type": "panel", "size": ["100%", 0], "collection_index": 0,
                       "controls": [{"adv_sizer": {
                           "type": "panel", "size": [0, 0], "property_bag": {"#cw": VIEW_W, "#ch": VIEW_H},
                           "bindings": [coll(), view(NX, "#cw"), view(NY, "#ch")]}}]}},
             {"meta2": {"type": "panel", "size": ["100%", 0], "collection_index": 1,
                        "controls": [{"adv_range": {
                            "type": "panel", "size": [0, 0],
                            "property_bag": {"#pw": VIEW_W, "#ph": VIEW_H, "#ox": POS_SHIFT, "#oy": POS_SHIFT},
                            "bindings": [coll(), view(NX, "#pw"), view(NY, "#ph"),
                                         view(f"({number(2)} - {POS_BIAS} + {POS_SHIFT})", "#ox"),
                                         view(f"({number(3)} - {POS_BIAS} + {POS_SHIFT})", "#oy")]}}]}}]
    n = 0
    for t, (count, _, _) in TAB_TYPES.items():
        for i in range(count):
            n += 1
            slots.append({f"tab{n}": {
                "type": "panel", "size": ["100%", 0], "collection_index": n + 1,
                "controls": [{"slot": {"type": "panel", "size": [VIEW_W + 18, VIEW_H + 27],
                                       "anchor_from": "top_left", "anchor_to": "top_left",
                                       "bindings": visible_if(is_char(KIND, 'T')),
                                       "controls": [{"place": tab_slot(t, i)}]}}]}})
    assert n == MAX_TABS
    return {"type": "stack_panel", "orientation": "vertical", "size": ["100%", "100%"],
            "collection_name": "form_buttons", "layer": 4, "controls": slots}


# ------------------------------------------------------------------ screen

def drag_area():
    """Java-style canvas dragging (AdvancementTab#scroll).

    The canvas is a draggable input_panel the size of the tab (meta item 0), `contained` in a box
    (meta item 1: its size and its position in the view). Bedrock clamps a contained drag to offsets
    0..(box - canvas) from where the canvas was laid out, whatever its anchor or offset, so the
    canvas sits at the box's top-left, the box at the opening scroll position, and the box reaches
    from there to Java's left/top limit. Opened normally that is the bottom-right end of the tree
    and the box is max(canvas, 2*canvas - view): exactly Java's clamp of the scroll to
    [view - canvas, 0] ("%c" sizes are computed before the canvas gets its bound size, so the server
    sends the box). After a D-pad step the view is centred on the selected advancement and can be
    dragged from there towards the left/top limit only.

    The box is placed by spacers in stack panels (offsets can't be bound), shifted by POS_SHIFT
    because the position can be negative.
    """
    background = {"type": "image", "size": ["100%", "100%"], "tiled": True,
                  "bindings": [{"binding_type": "collection", "binding_collection_name": "form_buttons",
                                "binding_name": "#form_button_texture", "binding_name_override": "#texture"}]}
    # Tiles are aligned to the canvas origin (Java draws them at scroll % 16) and reach far past it,
    # so a canvas smaller than the view is still surrounded by background.
    bg = dict(meta("bg", background, size=(6144, 6144)), offset=[-3072, -3072], layer=0,
              anchor_from="top_left", anchor_to="top_left")
    items = {"type": "collection_panel", "size": [0, 0], "collection_name": "form_buttons", "layer": 1,
             "anchor_from": "top_left", "anchor_to": "top_left",
             "factory": {"name": "buttons", "control_ids": {"button": f"@{NS}.canvas_item"}},
             "bindings": [{"binding_name": "#form_button_contents", "binding_name_override": "#collection_length"}]}
    # The D-pad stays among the advancements at the tree's outer ends, as on Java (Bedrock otherwise
    # wraps round to the next row, or leaves for a tab or the Done button).
    stop = {f"focus_navigation_mode_{d}": "stop" for d in ("left", "right", "up", "down")}
    canvas = {"type": "input_panel", "size": [VIEW_W, VIEW_H], "draggable": "both", "contained": True,
              "anchor_from": "top_left", "anchor_to": "top_left",
              "focus_container": True, "focus_wrap_enabled": False, **stop,
              "property_bag": {"#size_binding_x_absolute": VIEW_W, "#size_binding_y_absolute": VIEW_H},
              # mouse/touch press, and the controller's A with the gamepad cursor (that arrives as
              # menu_ok; without this mapping holding A and moving the stick only moved the pointer)
              "button_mappings": [{"from_button_id": "button.menu_select", "to_button_id": "button.menu_select",
                                   "mapping_type": "pressed", "button_up_right_of_first_refusal": True},
                                  {"from_button_id": "button.menu_ok", "to_button_id": "button.menu_select",
                                   "mapping_type": "pressed", "button_up_right_of_first_refusal": True}],
              "bindings": [view("#cw", "#size_binding_x_absolute", "adv_sizer"),
                           view("#ch", "#size_binding_y_absolute", "adv_sizer")],
              "controls": [{"bg": bg}, {"items": items}]}
    box = {"type": "panel", "size": [VIEW_W, VIEW_H],
           "property_bag": {"#size_binding_x_absolute": VIEW_W, "#size_binding_y_absolute": VIEW_H},
           "bindings": [view("#pw", "#size_binding_x_absolute", "adv_range"),
                        view("#ph", "#size_binding_y_absolute", "adv_range")],
           "anchor_from": "top_left", "anchor_to": "top_left", "controls": [{"adv_canvas": canvas}]}

    def shift(axis, prop):
        p = f"#size_binding_{axis}_absolute"
        return {"type": "panel", "size": [0, 0], "property_bag": {p: POS_SHIFT},
                "bindings": [view(prop, p, "adv_range")]}
    row = {"type": "stack_panel", "orientation": "horizontal", "size": ["100%c", "100%cm"],
           "controls": [{"xs": shift("x", "#ox")}, {"box": box}]}
    return {"type": "stack_panel", "orientation": "vertical", "size": ["100%cm", "100%c"],
            "anchor_from": "top_left", "anchor_to": "top_left", "offset": [-POS_SHIFT, -POS_SHIFT],
            "controls": [{"ys": shift("y", "#oy")}, {"row": row}]}


def window():
    empty = {"type": "label", "text": "#text", "color": [1, 1, 1], "layer": 5,
             "text_alignment": "center", "size": ["100%", "default"],
             "bindings": [coll(), view(is_char(FLAG + 1, 'y'), "#visible"), view(PAYLOAD, "#text")]}
    inner = {
        "type": "panel", "size": [VIEW_W, VIEW_H], "offset": [9, 18],
        "anchor_from": "top_left", "anchor_to": "top_left", "clips_children": True, "layer": 1,
        "controls": [
            {"black": solid('k', ["100%", "100%"], layer=0)},
            {"drag": dict(drag_area(), layer=1)},
            {"empty": dict(meta("msg", empty, size=("100%", "100%c")), anchor_from="center", anchor_to="center",
                           layer=5)},
        ]}
    title = {"type": "panel", "size": ["100% - 16px", LINE_H + 1], "offset": [8, 6], "clips_children": True,
             "anchor_from": "top_left", "anchor_to": "top_left", "layer": 3,
             "controls": [{"m": meta("t", label(PAYLOAD, color=(0.25, 0.25, 0.25), layer=1),
                                     size=("100%", "100%c"))}]}
    return {
        "type": "panel", "size": [VIEW_W + 18, VIEW_H + 27], "offset": [0, 2], "layer": 2,
        "controls": [
            {"frame": {"type": "image", "texture": TEX + "window", "size": ["100%", "100%"], "layer": 2}},
            {"inner": inner},
            {"title": title},
            {"tabs": chrome()},
        ]}


def screen():
    header = {"type": "label", "text": "#text", "color": [1, 1, 1], "shadow": True, "layer": 3,
              "anchor_from": "top_middle", "anchor_to": "top_middle", "offset": [0, 12],
              "size": ["default", "default"],
              "bindings": [{"binding_name": "#title_text"},
                           view("(#title_text - 'ADVGUI:')", "#text")]}
    done = {"type": "panel", "size": [200, 20], "anchor_from": "bottom_middle", "anchor_to": "bottom_middle",
            "offset": [0, -8], "layer": 3,
            "controls": [{"done_button@common_buttons.light_text_button": {
                "$pressed_button_name": "button.menu_exit", "size": [200, 20],
                "$button_text": "gui.done", "$button_text_binding_type": "none",
                "$button_focus_precedence": 100}}]}
    return {"type": "panel", "size": ["100%", "100%"],
            "controls": [
                {"shade":{"type": "image", "texture": TEX + "line_Hk", "size": ["100%", "100%"], "keep_ratio": False,
                           "alpha": 0.5, "layer": 0}},
                {"header": header},
                {"window@" + NS + ".window": {}},
                {"done": done},
            ]}


def ui_json():
    return {
        "namespace": NS,
        "screen": screen(),
        "window": window(),
        "canvas_item": canvas_item(),
    }


def server_form_json():
    marker = "(('%.7s' * #title_text) = 'ADVGUI:')"
    return {
        "namespace": "server_form",
        # Java switches tabs instantly; Bedrock's form screen fades/slides out and in again, which
        # made every tab click take about a second. (Applies to all Geyser forms: they just appear.)
        # gamepad_cursor: a controller gets a stick-driven pointer (as in the classic inventory), so it
        # can hover advancements and drag the tree. It is a screen setting, so normal Geyser forms
        # get the pointer too.
        "third_party_server_screen@common.base_screen": {
            "$screen_content": "server_form.main_screen_content",
            "gamepad_cursor": True,
            "$screen_animations": [], "$background_animations": [],
            "button_mappings": [{"from_button_id": "button.menu_cancel", "to_button_id": "button.menu_exit",
                                 "mapping_type": "global"}]},
        "main_screen_content": {
            "type": "panel", "size": ["100%", "100%"],
            "controls": [{"server_form_factory": {
                "type": "factory",
                "control_ids": {"long_form": "@server_form.adv_router", "custom_form": "@server_form.custom_form"}}},
                {"gamepad_cursor@common.gamepad_cursor_button": {"layer": 100}}]},
        "adv_router": {
            "type": "panel", "size": ["100%", "100%"],
            "controls": [
                # Hidden by default: the vanilla button list must not be built for our form (it cost
                # about as much as our own screen). See long_form_dynamic_buttons_panel below.
                {"vanilla": {"type": "panel", "size": ["100%", "100%"], "visible": False,
                             "bindings": [{"binding_name": "#title_text"},
                                          {"binding_type": "view", "source_property_name": f"(not {marker})",
                                           "target_property_name": "#visible"}],
                             "controls": [{"long_form@server_form.long_form": {}}]}},
                {"adv": {"type": "panel", "size": ["100%", "100%"],
                         "bindings": [{"binding_name": "#title_text"},
                                      {"binding_type": "view", "source_property_name": marker,
                                       "target_property_name": "#visible"}],
                         "controls": [{"screen@" + NS + ".screen": {}}]}},
            ]},
        # vanilla definition, plus binding_condition "visible" on the button count
        "long_form_dynamic_buttons_panel": {
            "type": "stack_panel", "size": ["100% - 4px", "100%c"], "offset": [2, 0], "orientation": "vertical",
            "anchor_from": "top_middle", "anchor_to": "top_middle",
            "factory": {"name": "buttons", "control_ids": {
                "button": "server_form.dynamic_button", "label": "@server_form.dynamic_label",
                "header": "@server_form.dynamic_header", "divider": "@settings_common.option_group_section_divider"}},
            "collection_name": "form_buttons",
            "bindings": [{"binding_name": "#form_button_contents", "binding_name_override": "#collection_length",
                          "binding_condition": "visible"}]},
    }


# ------------------------------------------------------------------ textures

def save(img, out, name):
    img.save(os.path.join(out, name + ".png"))


def copy_rgba(src, dst):
    """Copy a PNG as RGBA: Bedrock renders greyscale (L) PNGs as translucent."""
    Image.open(src).convert("RGBA").save(dst)


def nineslice(out, name, size, base):
    with open(os.path.join(out, name + ".json"), "w") as f:
        json.dump({"nineslice_size": size, "base_size": base}, f)


def build_textures(java, out):
    gui = os.path.join(java, "assets", "minecraft", "textures", "gui")
    spr = os.path.join(gui, "sprites", "advancements")
    os.makedirs(out, exist_ok=True)

    window = Image.open(os.path.join(gui, "advancements", "window.png")).convert("RGBA").crop((0, 0, 252, 140))
    save(window, out, "window")
    nineslice(out, "window", [9, 18, 9, 9], [252, 140])

    for t, java_name in (("t", "task"), ("g", "goal"), ("c", "challenge")):
        for o, state in (("y", "obtained"), ("n", "unobtained")):
            copy_rgba(os.path.join(spr, f"{java_name}_frame_{state}.png"), os.path.join(out, f"frame_N{t}{o}.png"))
            copy_rgba(os.path.join(spr, f"box_{state}.png"), os.path.join(out, f"box_N{t}{o}.png"))
            nineslice(out, f"box_N{t}{o}", [10, 10, 10, 10], [200, 26])
    copy_rgba(os.path.join(spr, "title_box.png"), os.path.join(out, "title_box.png"))
    nineslice(out, "title_box", [10, 10, 10, 10], [200, 26])

    names = {'a': ('above', ('left', 'middle', 'right')), 'b': ('below', ('left', 'middle', 'right')),
             'l': ('left', ('top', 'middle', 'bottom')), 'r': ('right', ('top', 'middle', 'bottom'))}
    for t, (side, parts) in names.items():
        for v, part in zip("lmr", parts):
            for s, suffix in (("y", "_selected"), ("n", "")):
                copy_rgba(os.path.join(spr, f"tab_{side}_{part}{suffix}.png"), os.path.join(out, f"tab_T{s}{v}{t}.png"))

    for d in ("H", "V"):
        save(Image.new("RGBA", (1, 1), (0, 0, 0, 255)), out, f"line_{d}k")
        save(Image.new("RGBA", (1, 1), (255, 255, 255, 255)), out, f"line_{d}w")

    for name in ("adventure", "end", "husbandry", "nether", "stone"):
        copy_rgba(os.path.join(gui, "advancements", "backgrounds", name + ".png"), os.path.join(out, "bg_" + name + ".png"))

    # Java-style tooltip (dark purple box with gradient border)
    tip = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(tip)
    d.rectangle((1, 0, 14, 15), fill=(16, 0, 16, 240))
    d.rectangle((0, 1, 15, 14), fill=(16, 0, 16, 240))
    for y in range(1, 15):
        f = (y - 1) / 13
        c = (int(0x50 + (0x28 - 0x50) * f), 0, int(0xFF + (0x7F - 0xFF) * f), 255)
        d.point((1, y), c)
        d.point((14, y), c)
    d.line((1, 1, 14, 1), fill=(0x50, 0, 0xFF, 255))
    d.line((1, 14, 14, 14), fill=(0x28, 0, 0x7F, 255))
    save(tip, out, "tooltip")
    nineslice(out, "tooltip", [3, 3, 3, 3], [16, 16])

    # parent-side connector stub (black part): rows depY-1 and depY+1 span 18px, row depY 19px
    stub = Image.new("RGBA", (19, 3), (0, 0, 0, 255))
    stub.putpixel((18, 0), (0, 0, 0, 0))
    stub.putpixel((18, 2), (0, 0, 0, 0))
    save(stub, out, "stub_parent")


def build_icons(java, out, resources, java_icons):
    """Optionally Java GUI item renders (render_icons.py), plus the index the extension bundles
    so it knows what the pack has. Tab backgrounds use Bedrock's own block textures."""
    index = {}
    if java_icons:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import render_icons
        icons_dir = os.path.join(out, "icons")
        render_icons.render_all(java, icons_dir)
        index = json.load(open(os.path.join(icons_dir, "index.json")))
        os.remove(os.path.join(icons_dir, "index.json"))
    if resources:
        with open(os.path.join(resources, "java_icons.json"), "w") as f:
            json.dump({"items": index}, f, separators=(",", ":"), sort_keys=True)
    print(f"icons: {len(index) or 'no'} Java item renders")


def main():
    args = sys.argv[1:]
    java_icons = "--java-icons" in args
    args = [a for a in args if a != "--java-icons"]
    java, out = args[0], args[1]
    version = [int(v) for v in (args[2] if len(args) > 2 else "1.0.0").split(".")]
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "ui"))
    manifest = {
        "format_version": 2,
        "header": {"name": "Advancements UI", "description": "Java-style advancements screen for Geyser",
                   "uuid": HEADER_UUID, "version": version, "min_engine_version": [1, 21, 0]},
        "modules": [{"type": "resources", "uuid": MODULE_UUID, "version": version}],
    }
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(out, "ui", "_ui_defs.json"), "w") as f:
        json.dump({"ui_defs": ["ui/adv_gui.json"]}, f, indent=2)
    with open(os.path.join(out, "ui", "adv_gui.json"), "w") as f:
        json.dump(ui_json(), f, separators=(",", ":"))
    with open(os.path.join(out, "ui", "server_form.json"), "w") as f:
        json.dump(server_form_json(), f, indent=2)
    build_textures(java, os.path.join(out, "textures", "ui", "adv_gui"))
    resources = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "extension", "src", "main", "resources")
    build_icons(java, os.path.join(out, "textures", "ui", "adv_gui"), resources if os.path.isdir(resources) else None, java_icons)
    # pack icon: the Java "obtained challenge" frame with a jukebox-ish tint
    icon = Image.new("RGBA", (64, 64), (40, 40, 40, 255))
    frame = Image.open(os.path.join(out, "textures", "ui", "adv_gui", "frame_Ncy.png")).convert("RGBA").resize((52, 52), Image.NEAREST)
    icon.paste(frame, (6, 6), frame)
    icon.save(os.path.join(out, "pack_icon.png"))
    print("pack written to", out, "version", ".".join(map(str, version)))


if __name__ == "__main__":
    main()
