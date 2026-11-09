package dev.advancementsui.advgui;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.geysermc.geyser.api.extension.ExtensionLogger;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * Works out which Bedrock texture path to show for a Java item icon or tab background.
 *
 * Sources, highest priority first:
 *   1. icons.json in the extension's data folder (user overrides),
 *   2. the Java GUI renders, only if the companion pack was built with them (build_pack.py
 *      --java-icons; textures/ui/adv_gui/icons, listed in java_icons.json),
 *   3. the Bedrock item itself, drawn by the client's inventory item renderer (Geyser's translation,
 *      so custom items from custom_mappings work too),
 *   4. Geyser custom item mappings + the item_texture.json of every pack in Geyser's packs folder,
 *      for item_model icons Geyser has no custom item for,
 *   5. the bundled vanilla table (Java item id -> Bedrock vanilla texture).
 */
final class IconResolver {

    private final Map<String, String> overrides = new HashMap<>();
    private final Map<String, String> vanillaItems = new HashMap<>();
    private final Map<String, String> backgrounds = new HashMap<>();
    /** Java item_model key (e.g. morediscs:music_disc_aerie) -> Bedrock texture path. */
    private final Map<String, String> customModels = new HashMap<>();
    /** Java item id -> icon file name in the pack's textures/ui/adv_gui/icons. */
    private final Map<String, String> javaIcons = new HashMap<>();
    private String fallback = "textures/blocks/barrier";
    private ExtensionLogger logger;
    private final java.util.Set<String> missing = java.util.concurrent.ConcurrentHashMap.newKeySet();
    static final String ICON_DIR = "textures/ui/adv_gui/icons/";

    void load(Path dataFolder, Path geyserConfigDir, Path packDir, ExtensionLogger logger) {
        this.logger = logger;
        try (InputStream in = IconResolver.class.getResourceAsStream("/vanilla_icons.json")) {
            if (in != null) {
                JsonObject root = parse(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject();
                root.getAsJsonObject("items").entrySet().forEach(e -> vanillaItems.put(e.getKey(), e.getValue().getAsString()));
                root.getAsJsonObject("backgrounds").entrySet().forEach(e -> backgrounds.put(e.getKey(), e.getValue().getAsString()));
            }
        } catch (Exception e) {
            logger.error("Could not read bundled vanilla icon table", e);
        }

        try (InputStream in = IconResolver.class.getResourceAsStream("/java_icons.json")) {
            if (in != null) {
                JsonObject root = parse(new InputStreamReader(in, StandardCharsets.UTF_8)).getAsJsonObject();
                root.getAsJsonObject("items").entrySet().forEach(e -> javaIcons.put(e.getKey(), e.getValue().getAsString()));
            }
        } catch (Exception e) {
            logger.error("Could not read bundled Java icon list", e);
        }

        // Texture keys (atlas short names) from every Bedrock pack Geyser serves.
        Map<String, String> textureKeys = new HashMap<>();
        if (packDir != null && Files.isDirectory(packDir)) {
            try (DirectoryStream<Path> packs = Files.newDirectoryStream(packDir)) {
                for (Path pack : packs) {
                    readItemTextures(pack, textureKeys, logger);
                }
            } catch (IOException e) {
                logger.warning("Could not scan packs folder: " + e.getMessage());
            }
        }

        // Geyser custom item mappings: model -> icon key.
        Path mappings = geyserConfigDir.resolve("custom_mappings");
        if (Files.isDirectory(mappings)) {
            try (Stream<Path> files = Files.list(mappings)) {
                files.filter(p -> p.toString().endsWith(".json")).forEach(p -> readMappings(p, textureKeys, logger));
            } catch (IOException e) {
                logger.warning("Could not scan custom_mappings: " + e.getMessage());
            }
        }

        Path overridesFile = dataFolder.resolve("icons.json");
        try {
            if (!Files.exists(overridesFile)) {
                Files.createDirectories(dataFolder);
                try (InputStream in = IconResolver.class.getResourceAsStream("/icons.json")) {
                    if (in != null) {
                        Files.copy(in, overridesFile);
                    }
                }
            }
            if (Files.exists(overridesFile)) {
                try (Reader r = Files.newBufferedReader(overridesFile, StandardCharsets.UTF_8)) {
                    JsonObject root = parse(r).getAsJsonObject();
                    if (root.has("icons")) {
                        root.getAsJsonObject("icons").entrySet().forEach(e -> overrides.put(e.getKey(), e.getValue().getAsString()));
                    }
                    if (root.has("backgrounds")) {
                        root.getAsJsonObject("backgrounds").entrySet().forEach(e -> backgrounds.put(e.getKey(), e.getValue().getAsString()));
                    }
                    if (root.has("fallback")) {
                        fallback = root.get("fallback").getAsString();
                    }
                }
            }
        } catch (Exception e) {
            logger.error("Could not read " + overridesFile, e);
        }

        logger.info("Icons: " + (javaIcons.isEmpty() ? "Bedrock item renderer" : javaIcons.size() + " Java renders") + ", " + vanillaItems.size() + " Bedrock vanilla, "
                + customModels.size() + " custom models, " + overrides.size() + " overrides");
    }

    /**
     * @param javaItem  Java item identifier, e.g. minecraft:music_disc_13
     * @param itemModel the item_model component if the icon has one, else null
     * @param bedrock   the Bedrock item for the pack's item renderer ({@link Item#itemRenderer}), or null
     */
    String icon(String javaItem, String itemModel, String bedrock) {
        if (itemModel != null) {
            String key = withNamespace(itemModel);
            String path = overrides.get(key);
            if (path != null) return path;
            if (key.startsWith("minecraft:")) {
                javaItem = key;
            } else {
                if (bedrock != null) return bedrock; // Geyser has a custom item for it
                path = customModels.get(key);
                if (path != null) return path;
                // Convention used by Rainbow / most converted packs.
                return "textures/item/" + key.substring(key.indexOf(':') + 1);
            }
        }
        String key = withNamespace(javaItem);
        String path = overrides.get(key);
        if (path != null) return path;
        String rendered = javaIcons.get(key); // only when the pack was built with --java-icons
        if (rendered != null) return ICON_DIR + rendered;
        if (bedrock != null) return bedrock;
        path = vanillaItems.get(key.substring(key.indexOf(':') + 1));
        if (path != null) return path;
        if (logger != null && missing.add(key + (itemModel == null ? "" : " (item_model " + itemModel + ")"))) {
            logger.info("No icon for " + key + (itemModel == null ? "" : " with item_model " + itemModel)
                    + "; showing the fallback. Map it in icons.json to fix.");
        }
        return fallback;
    }

    /** @param texture the Java background, e.g. minecraft:block/jukebox_side */
    String background(String texture) {
        if (texture == null || texture.isEmpty()) {
            return "textures/blocks/stone";
        }
        String key = withNamespace(texture);
        String path = overrides.get(key);
        if (path != null) return path;
        String p = key.substring(key.indexOf(':') + 1);
        if (p.startsWith("textures/")) p = p.substring("textures/".length());
        if (p.endsWith(".png")) p = p.substring(0, p.length() - 4);
        path = backgrounds.get(key);
        if (path == null) path = backgrounds.get(key.substring(key.indexOf(':') + 1));
        if (path != null) return path;
        if (p.startsWith("block/")) return "textures/blocks/" + p.substring(6);
        return "textures/" + p;
    }

    private static String withNamespace(String id) {
        id = id.toLowerCase(Locale.ROOT);
        return id.indexOf(':') < 0 ? "minecraft:" + id : id;
    }

    private void readMappings(Path file, Map<String, String> textureKeys, ExtensionLogger logger) {
        try (Reader r = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            JsonElement root = parse(r);
            if (!root.isJsonObject() || !root.getAsJsonObject().has("items")) return;
            for (Map.Entry<String, JsonElement> item : root.getAsJsonObject().getAsJsonObject("items").entrySet()) {
                if (item.getValue().isJsonArray()) {
                    readDefinitions(item.getValue().getAsJsonArray(), textureKeys);
                }
            }
        } catch (Exception e) {
            logger.warning("Skipping mappings file " + file.getFileName() + ": " + e.getMessage());
        }
    }

    private void readDefinitions(JsonArray defs, Map<String, String> textureKeys) {
        for (JsonElement el : defs) {
            if (!el.isJsonObject()) continue;
            JsonObject def = el.getAsJsonObject();
            if (def.has("definitions") && def.get("definitions").isJsonArray()) {
                readDefinitions(def.getAsJsonArray("definitions"), textureKeys); // "group" entries
            }
            if (!def.has("model")) continue;
            String model = withNamespace(def.get("model").getAsString());
            String iconKey = null;
            if (def.has("bedrock_options") && def.getAsJsonObject("bedrock_options").has("icons")) {
                JsonElement icons = def.getAsJsonObject("bedrock_options").get("icons");
                if (icons.isJsonObject() && icons.getAsJsonObject().has("default")) {
                    iconKey = icons.getAsJsonObject().get("default").getAsString();
                }
            } else if (def.has("bedrock_options") && def.getAsJsonObject("bedrock_options").has("icon")) {
                iconKey = def.getAsJsonObject("bedrock_options").get("icon").getAsString();
            }
            if (iconKey == null && def.has("bedrock_identifier")) {
                String bid = def.get("bedrock_identifier").getAsString();
                iconKey = bid.replace(':', '.').replace('/', '_');
            }
            String path = iconKey == null ? null : textureKeys.get(iconKey);
            if (path != null) {
                customModels.put(model, path);
            }
        }
    }

    private static void readItemTextures(Path pack, Map<String, String> out, ExtensionLogger logger) {
        try {
            if (Files.isDirectory(pack)) {
                Path f = pack.resolve("textures/item_texture.json");
                if (Files.exists(f)) {
                    try (Reader r = Files.newBufferedReader(f, StandardCharsets.UTF_8)) {
                        readItemTextureJson(parse(r), out);
                    }
                }
            } else {
                String name = pack.getFileName().toString().toLowerCase(Locale.ROOT);
                if (!name.endsWith(".zip") && !name.endsWith(".mcpack")) return;
                try (ZipFile zip = new ZipFile(pack.toFile())) {
                    zip.stream()
                            .filter(e -> e.getName().endsWith("textures/item_texture.json"))
                            .forEach(e -> readZipEntry(zip, e, out));
                }
            }
        } catch (Exception e) {
            logger.warning("Skipping pack " + pack.getFileName() + ": " + e.getMessage());
        }
    }

    private static void readZipEntry(ZipFile zip, ZipEntry entry, Map<String, String> out) {
        try (Reader r = new InputStreamReader(zip.getInputStream(entry), StandardCharsets.UTF_8)) {
            readItemTextureJson(parse(r), out);
        } catch (IOException ignored) {
        }
    }

    private static void readItemTextureJson(JsonElement root, Map<String, String> out) {
        JsonObject data = root.getAsJsonObject().getAsJsonObject("texture_data");
        if (data == null) return;
        for (Map.Entry<String, JsonElement> e : data.entrySet()) {
            JsonElement tex = e.getValue().getAsJsonObject().get("textures");
            if (tex == null) continue;
            if (tex.isJsonArray()) tex = tex.getAsJsonArray().get(0);
            if (tex.isJsonObject()) tex = tex.getAsJsonObject().get("path");
            if (tex != null && tex.isJsonPrimitive()) {
                out.put(e.getKey(), tex.getAsString());
            }
        }
    }

    @SuppressWarnings("deprecation")
    private static JsonElement parse(Reader r) {
        return JsonParser.parseReader(r);
    }
}
