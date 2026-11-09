#!/usr/bin/env python3
"""Generate extension/src/main/resources/vanilla_icons.json.

Maps every Java item id to the closest Bedrock vanilla texture path, using the list of
textures that ship with Bedrock (bedrock_vanilla_textures.txt, extracted from the game's
resource packs) and naming heuristics for the places where Java and Bedrock differ.

It also maps every Java block texture (tab backgrounds such as minecraft:block/oak_planks) to
Bedrock's texture for the same block face (textures/blocks/planks_oak), using Bedrock's own
blocks.json + terrain_texture.json, condensed into bedrock_block_textures.json.

usage: gen_vanilla_icons.py <unpacked java client jar dir> [advancement icon ids to check...]
       gen_vanilla_icons.py --bedrock <Bedrock data/resource_packs dir> <unpacked java client jar dir>
           (first re-extracts bedrock_block_textures.json from an installed Bedrock client)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'extension', 'src', 'main', 'resources', 'vanilla_icons.json')
BLOCK_TABLE = os.path.join(HERE, 'bedrock_block_textures.json')

MANUAL = {
    'grass_block': 'textures/blocks/grass_side_carried',
    'golden_apple': 'textures/items/apple_golden',
    'enchanted_golden_apple': 'textures/items/apple_golden',
    'golden_carrot': 'textures/items/carrot_golden',
    'glistering_melon_slice': 'textures/items/melon_speckled',
    'melon_slice': 'textures/items/melon',
    'lava_bucket': 'textures/items/bucket_lava',
    'water_bucket': 'textures/items/bucket_water',
    'milk_bucket': 'textures/items/bucket_milk',
    'powder_snow_bucket': 'textures/items/bucket_powder_snow',
    'axolotl_bucket': 'textures/items/bucket_axolotl',
    'cod_bucket': 'textures/items/bucket_cod',
    'salmon_bucket': 'textures/items/bucket_salmon',
    'pufferfish_bucket': 'textures/items/bucket_pufferfish',
    'tropical_fish_bucket': 'textures/items/bucket_tropical',
    'tadpole_bucket': 'textures/items/bucket_tadpole',
    'bucket': 'textures/items/bucket_empty',
    'ender_eye': 'textures/items/ender_eye',
    'ender_pearl': 'textures/items/ender_pearl',
    'fire_charge': 'textures/items/fireball',
    'flint_and_steel': 'textures/items/flint_and_steel',
    'fishing_rod': 'textures/items/fishing_rod_uncast',
    'bow': 'textures/items/bow_standby',
    'crossbow': 'textures/items/crossbow_standby',
    'potion': 'textures/items/potion_bottle_drinkable',
    'enchanted_book': 'textures/items/book_enchanted',
    'map': 'textures/items/map_empty',
    'filled_map': 'textures/items/map_filled',
    'oak_boat': 'textures/items/boat_oak',
    'red_bed': 'textures/items/bed_red',
    'white_banner': 'textures/items/banner_pattern',
    'cookie': 'textures/items/cookie',
    'wheat': 'textures/items/wheat',
    'torchflower_seeds': 'textures/items/torchflower_seeds',
    'lead': 'textures/items/lead',
    'shield': 'textures/items/empty_armor_slot_shield',
    'trident': 'textures/items/trident',
    'spyglass': 'textures/items/spyglass',
    'warped_fungus_on_a_stick': 'textures/items/warped_fungus_on_a_stick',
    'wither_skeleton_skull': 'textures/items/skull_banner_pattern',
    'cod': 'textures/items/fish_raw',
    'salmon': 'textures/items/fish_salmon_raw',
    'tropical_fish': 'textures/items/fish_clownfish_raw',
    'pufferfish': 'textures/items/fish_pufferfish_raw',
    'iron_spear': 'textures/items/iron_sword',
    'dragon_head': 'textures/items/dragon_fireball',
    'end_crystal': 'textures/items/end_crystal',
    'dragon_breath': 'textures/items/dragons_breath',
    'totem_of_undying': 'textures/items/totem',
    'shulker_shell': 'textures/items/shulker_shell',
    'ghast_tear': 'textures/items/ghast_tear',
    'nether_star': 'textures/items/nether_star',
    'beacon': 'textures/blocks/beacon',
    'jukebox': 'textures/blocks/jukebox_top',
    'note_block': 'textures/blocks/noteblock',
    'tnt': 'textures/blocks/tnt_side',
    'hay_block': 'textures/blocks/hay_block_side',
    'honey_block': 'textures/blocks/honey_side',
    'bee_nest': 'textures/blocks/bee_nest_front',
    'carved_pumpkin': 'textures/blocks/pumpkin_face_off',
    'chest': 'textures/blocks/chest_front',
    'target': 'textures/blocks/target_side',
    'respawn_anchor': 'textures/blocks/respawn_anchor_side4',
    'lodestone': 'textures/blocks/lodestone_side',
    'crafter': 'textures/blocks/crafter_north',
    'chiseled_bookshelf': 'textures/blocks/chiseled_bookshelf_empty',
    'sculk_catalyst': 'textures/blocks/sculk_catalyst_side',
    'sculk_sensor': 'textures/blocks/sculk_sensor_side',
    'red_nether_bricks': 'textures/blocks/red_nether_brick',
    'nether_bricks': 'textures/blocks/nether_brick',
    'purpur_block': 'textures/blocks/purpur_block',
    'polished_blackstone_bricks': 'textures/blocks/polished_blackstone_bricks',
    'end_stone': 'textures/blocks/end_stone',
    'ancient_debris': 'textures/blocks/ancient_debris_side',
    'crying_obsidian': 'textures/blocks/crying_obsidian',
    'creaking_heart': 'textures/blocks/creaking_heart_side_active',
    'verdant_froglight': 'textures/blocks/verdant_froglight_side',
    'copper_bulb': 'textures/blocks/copper_bulb_lit',
    'chiseled_tuff': 'textures/blocks/chiseled_tuff',
    'sniffer_egg': 'textures/items/sniffer_egg',
    'decorated_pot': 'textures/items/decorated_pot',
    'armadillo_scute': 'textures/items/armadillo_scute',
    'wolf_armor': 'textures/items/wolf_armor',
    'glow_ink_sac': 'textures/items/dye_powder_glow',
    'honey_bottle': 'textures/items/honey_bottle',
    'honeycomb': 'textures/items/honeycomb',
    'brush': 'textures/items/brush',
    'pitcher_pod': 'textures/items/pitcher_pod',
    'dried_ghast': 'textures/blocks/dried_ghast_state_1_front',
}

PREFIX_SWAPS = [('golden_', 'gold_'), ('wooden_', 'wood_')]


def candidates(item):
    yield 'textures/items/' + item
    if item.startswith('music_disc_'):
        rest = item[len('music_disc_'):]
        yield 'textures/items/record_' + rest
        yield 'textures/items/music_disc_' + rest
    for a, b in PREFIX_SWAPS:
        if item.startswith(a):
            yield 'textures/items/' + b + item[len(a):]
    if item.endswith('_bucket'):
        yield 'textures/items/bucket_' + item[:-len('_bucket')]
    if item.endswith('_spawn_egg'):
        yield 'textures/items/spawn_eggs/spawn_egg_' + item[:-len('_spawn_egg')]
    if item.endswith('_smithing_template'):
        yield 'textures/items/' + item.replace('_smithing_template', '_smithing_template')
    if item.endswith('_dye'):
        yield 'textures/items/dye_powder_' + item[:-len('_dye')]
    for suffix in ('', '_side', '_top', '_front', '_north', '_0', '_stage_0'):
        yield 'textures/blocks/' + item + suffix
    if item.endswith('s'):
        yield 'textures/blocks/' + item[:-1]


# ---- block textures (tab backgrounds) ----

COLORS = ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'gray',
          'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black']
# Java block id -> Bedrock blocks.json id where Bedrock still uses the old name.
BLOCK_ALIASES = {
    'bricks': 'brick_block', 'grass_block': 'grass', 'cobweb': 'web', 'terracotta': 'hardened_clay',
    'comparator': 'unpowered_comparator', 'repeater': 'unpowered_repeater', 'snow_block': 'snow',
    'nether_bricks': 'nether_brick', 'red_nether_bricks': 'red_nether_brick',
    'jack_o_lantern': 'lit_pumpkin', 'sugar_cane': 'reeds', 'end_stone_bricks': 'end_bricks',
    'note_block': 'noteblock', 'oak_door': 'wooden_door', 'oak_trapdoor': 'trapdoor', 'slime_block': 'slime',
    'spawner': 'mob_spawner', 'rooted_dirt': 'dirt_with_roots', 'nether_quartz_ore': 'quartz_ore',
    'lily_pad': 'waterlily', 'dirt_path': 'grass_path', 'item_frame': 'frame', 'powered_rail': 'golden_rail',
    'light_gray_glazed_terracotta': 'silver_glazed_terracotta',
}
# Java block texture -> Bedrock texture where the matching below picks the wrong one.
BLOCK_MANUAL = {
    'powered_rail': 'textures/blocks/rail_golden',
    'powered_rail_on': 'textures/blocks/rail_golden_powered',
    'carved_pumpkin': 'textures/blocks/pumpkin_face_off',
    'jack_o_lantern': 'textures/blocks/pumpkin_face_on',
}
FACES = {'top': ('up',), 'bottom': ('down',), 'side': ('side', 'south', 'east', 'north', 'west'),
         'front': ('north', 'south', 'side'), '': ('side', 'south', 'up')}
SUFFIXES = ('_top', '_bottom', '_side', '_front', '')


def extract_block_table(packs_dir):
    """Bedrock block id -> {face: texture path}, from every vanilla* pack (later versions win)."""
    def version(name):
        m = re.fullmatch(r'vanilla(?:_(\d+(?:\.\d+)*))?', name)
        if not m:
            return None
        return tuple(int(x) for x in m.group(1).split('.')) if m.group(1) else (0,)

    def load(path):
        return json.loads(re.sub(r'//[^\n]*', '', open(path, encoding='utf-8').read()))

    blocks, terrain = {}, {}
    for _, name in sorted((v, n) for n in os.listdir(packs_dir) if (v := version(n)) is not None):
        b = os.path.join(packs_dir, name, 'blocks.json')
        t = os.path.join(packs_dir, name, 'textures', 'terrain_texture.json')
        if os.path.exists(b):
            blocks.update({k: v for k, v in load(b).items() if isinstance(v, dict) and 'textures' in v})
        if os.path.exists(t):
            terrain.update(load(t)['texture_data'])

    def paths(key):
        t = (terrain.get(key) or {}).get('textures')
        t = t if isinstance(t, list) else [t]
        return [e.get('path') if isinstance(e, dict) else e for e in t if e]

    table = {}
    for block, entry in sorted(blocks.items()):
        tex = entry['textures']
        faces = {'side': tex} if isinstance(tex, str) else tex
        row = {face: paths(key) for face, key in faces.items() if paths(key)}
        if row:
            table[block] = row
    return table


def _words(name):
    words = set(name.split('_'))
    if 'light_gray' in name:
        words.add('silver')
    if 'top' in words:
        words.add('upper')
    if 'bottom' in words:
        words.add('lower')
    if name.startswith('oak_'):
        words.add('wood')  # Bedrock's legacy oak textures: door_wood_upper, planks_oak, ...
    return words


def block_background(name, table):
    """Bedrock texture for the Java block texture `name` (e.g. oak_log_top), or None.

    Bedrock often lists several textures for one block (legacy variants such as all wooden doors
    under one id, or per-face textures), so among them the one sharing the most words with the
    Java name wins; the face the Java suffix names (_top -> up, ...) breaks ties."""
    if name in BLOCK_MANUAL:
        return BLOCK_MANUAL[name]
    words = _words(name)

    def score(path):
        parts = set(path.rsplit('/', 1)[-1].split('_'))
        return len(words & parts), -len(parts - words)  # most shared words, then fewest extra ones

    for suffix in SUFFIXES:
        if suffix and not name.endswith(suffix):
            continue
        base = name[:len(name) - len(suffix)] if suffix else name
        color = next((c for c in sorted(COLORS, key=len, reverse=True) if base.startswith(c + '_')), None)
        if color and base == color + '_terracotta':
            options = table.get('stained_hardened_clay', {}).get('side', [])
            if len(options) == len(COLORS):
                return options[COLORS.index(color)]
        tries = [base, BLOCK_ALIASES.get(base), base + 's', base[:-1] if base.endswith('s') else None,
                 base + '_block']
        for block in filter(None, tries):
            row = table.get(block)
            if not row:
                continue
            preferred = [o for face in FACES[suffix.lstrip('_')] for o in row.get(face, [])]
            others = [o for options in row.values() for o in options]
            ranked = preferred + [o for o in others if o not in preferred]
            if ranked:
                return max(ranked, key=score)  # max keeps the first of equal scores
    return None


def main():
    args = sys.argv[1:]
    if args and args[0] == '--bedrock':
        with open(BLOCK_TABLE, 'w') as f:
            json.dump(extract_block_table(args[1]), f, indent=0, sort_keys=True)
        args = args[2:]
    java_dir = args[0]
    textures = set(open(os.path.join(HERE, 'bedrock_vanilla_textures.txt')).read().split())
    items_dir = os.path.join(java_dir, 'assets', 'minecraft', 'items')
    java_items = sorted(f[:-5] for f in os.listdir(items_dir) if f.endswith('.json'))

    items = {}
    missing = []
    for item in java_items:
        path = MANUAL.get(item)
        if path is None or path not in textures:
            path = next((c for c in candidates(item) if c in textures), MANUAL.get(item))
        if path is None:
            missing.append(item)
            continue
        items[item] = path

    backgrounds = {}
    for name in ('adventure', 'end', 'husbandry', 'nether', 'stone'):
        backgrounds['gui/advancements/backgrounds/' + name] = 'textures/ui/adv_gui/bg_' + name
    for tex in textures:
        if tex.startswith('textures/blocks/'):
            backgrounds['block/' + tex[len('textures/blocks/'):]] = tex
    backgrounds['block/jukebox_side'] = 'textures/blocks/jukebox_side'
    table = json.load(open(BLOCK_TABLE))
    java_blocks = sorted(f[:-4] for f in os.listdir(os.path.join(java_dir, 'assets', 'minecraft', 'textures', 'block'))
                         if f.endswith('.png'))
    unmapped_blocks = []
    for name in java_blocks:
        if 'block/' + name in backgrounds:
            continue
        path = block_background(name, table)
        if path:
            backgrounds['block/' + name] = path
        else:
            unmapped_blocks.append(name)

    with open(OUT, 'w') as f:
        json.dump({'items': items, 'backgrounds': backgrounds}, f, indent=0, sort_keys=True)
    print(f'{len(items)} items mapped, {len(missing)} unmapped')
    print(f'{len(java_blocks) - len(unmapped_blocks)} of {len(java_blocks)} Java block textures mapped '
          f'(unmapped ones fall back to textures/blocks/<name>)')
    adv_icons = args[1:]
    for icon in adv_icons:
        if icon not in items:
            print('  advancement icon unmapped:', icon)


if __name__ == '__main__':
    main()
