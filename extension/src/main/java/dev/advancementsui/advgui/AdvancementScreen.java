package dev.advancementsui.advgui;

import org.geysermc.cumulus.form.SimpleForm;
import org.geysermc.cumulus.util.FormImage;
import org.geysermc.geyser.level.GeyserAdvancement;
import org.geysermc.geyser.registry.type.ItemMapping;
import org.geysermc.geyser.session.GeyserSession;
import org.geysermc.geyser.text.MinecraftLocale;
import org.geysermc.geyser.translator.item.ItemTranslator;
import org.cloudburstmc.protocol.bedrock.data.inventory.ItemData;
import org.geysermc.mcprotocollib.protocol.data.game.advancement.Advancement;
import org.geysermc.mcprotocollib.protocol.data.game.item.ItemStack;
import org.geysermc.mcprotocollib.protocol.data.game.item.component.DataComponentTypes;
import org.geysermc.mcprotocollib.protocol.data.game.item.component.DataComponents;
import org.geysermc.mcprotocollib.protocol.packet.ingame.serverbound.inventory.ServerboundSeenAdvancementsPacket;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;

/**
 * Builds the Java-style advancements screen as one SimpleForm.
 *
 * Button order: meta (canvas size, title, background), drag range, up to 26 tabs, connector
 * trunks, nodes.
 * The pack reads the meta and the tabs from fixed indices. Only tabs and edge presses (below) send
 * a response; everything else (dragging, tooltips, D-pad steps in the view) is client-side.
 *
 * Controller D-pad: Bedrock's focus navigation moves the gamepad pointer between the advancements
 * in the view, but JSON UI can't move the view when focus moves, and it skips the clipped ones. So
 * an advancement in the view that has none visible beyond it in some direction, but hidden ones
 * there, is marked as an edge for that direction (node flag 7): pressing that way while it is
 * focused comes here, and the screen is sent again centred on the next advancement that way.
 * Bedrock puts the gamepad pointer back at the screen centre for a new form, so that one is
 * hovered and shows its tooltip. Edges are judged at the scroll the form opens with.
 */
final class AdvancementScreen {

    /** Marker the resource pack looks for in the form title. */
    static final String TITLE_MARKER = "ADVGUI:";

    /** Java's inner window size (AdvancementsScreen.WINDOW_INSIDE_WIDTH/HEIGHT); the pack uses it too. */
    static final int VIEW_W = 234;
    static final int VIEW_H = 113;
    /**
     * How far the screen's centre (where Bedrock puts the gamepad pointer for a new form) is above
     * the view's centre: the window (140 high) is centred 2px low, the view starts 18 into it and is
     * 113 high, so 2 + 18 + 113 / 2 - 140 / 2 = 6.5.
     */
    static final int POINTER_DY = 6;
    /** Bias for the drag range box position, which can be negative (sent + this). */
    static final int POS_BIAS = 5000;
    /** Extra scrollable space around the tree, in pixels. */
    static final int CANVAS_MARGIN = 16;
    /** Java's tab slots per page (AdvancementTabType: 8 above, 8 below, 5 left, 5 right). */
    static final int MAX_TABS = 26;
    /**
     * Distance between the lines of a multi-line Bedrock label. Java's tooltip uses 9; Bedrock spaces
     * its lines 10 apart, so the description boxes grow by one pixel per line to keep Java's margins
     * (with 9 the text ran past the box bottom, or into the title bar when the tooltip opens upwards).
     */
    static final int LINE = 10;

    private static final List<String> VANILLA_TAB_ORDER = List.of(
            "minecraft:story/root", "minecraft:nether/root", "minecraft:end/root",
            "minecraft:adventure/root", "minecraft:husbandry/root");

    private final AdvGuiExtension ext;

    AdvancementScreen(AdvGuiExtension ext) {
        this.ext = ext;
    }

    // ---------------------------------------------------------------- data access

    private static Map<String, GeyserAdvancement> advancements(GeyserSession session) {
        return session.getAdvancementsCache().getStoredAdvancements();
    }

    /** Roots that Java would show as tabs (they need a display and a background). */
    List<GeyserAdvancement> tabs(GeyserSession session) {
        List<GeyserAdvancement> roots = new ArrayList<>();
        for (GeyserAdvancement adv : advancements(session).values()) {
            Advancement.DisplayData d = adv.getDisplayData();
            if (adv.getParentId() == null && d != null && d.getBackgroundTexture() != null) {
                roots.add(adv);
            }
        }
        roots.sort(Comparator.comparingInt((GeyserAdvancement a) -> {
            int i = VANILLA_TAB_ORDER.indexOf(a.getId());
            return i < 0 ? VANILLA_TAB_ORDER.size() : i;
        }).thenComparing(GeyserAdvancement::getId));
        return roots;
    }

    /** Requirement groups completed / total, the way Java's AdvancementProgress counts them. */
    private static int[] progress(GeyserSession session, GeyserAdvancement adv) {
        List<List<String>> reqs = adv.getRequirements();
        Map<String, Long> got = session.getAdvancementsCache().getStoredAdvancementProgress().get(adv.getId());
        int done = 0;
        for (List<String> group : reqs) {
            for (String criterion : group) {
                Long t = got == null ? null : got.get(criterion);
                if (t != null && t != -1L) {
                    done++;
                    break;
                }
            }
        }
        return new int[]{done, reqs.size()};
    }

    // ---------------------------------------------------------------- form

    void open(GeyserSession session, String requestedTab) {
        open(session, requestedTab, null, (char) 0);
    }

    /**
     * @param focus the advancement selected with the D-pad on the previous form (null: none)
     * @param dir   D-pad direction pressed ('l', 'r', 'u', 'd'), or 0 to open normally
     */
    private void open(GeyserSession session, String requestedTab, String focus, char dir) {
        List<GeyserAdvancement> tabs = tabs(session);
        GeyserAdvancement tab = null;
        for (GeyserAdvancement t : tabs) {
            if (t.getId().equals(requestedTab)) tab = t;
        }
        if (tab == null && !tabs.isEmpty()) tab = tabs.get(0);
        if (tab != null) {
            ext.rememberTab(session, tab.getId());
            session.sendDownstreamGamePacket(new ServerboundSeenAdvancementsPacket(tab.getId()));
        }
        session.sendForm(build(session, tabs, tab, focus, dir));
    }

    private SimpleForm build(GeyserSession session, List<GeyserAdvancement> tabs, GeyserAdvancement tab,
                             String focus, char dir) {
        String locale = session.locale();
        String windowTitle = tab != null
                ? Text.title(tab.getDisplayData(), locale)
                : MinecraftLocale.getLocaleString("gui.advancements", locale);

        SimpleForm.Builder form = SimpleForm.builder()
                .title(TITLE_MARKER + MinecraftLocale.getLocaleString("gui.advancements", locale));

        Map<Integer, String> tabButtons = new HashMap<>();
        List<String[]> buttons = new ArrayList<>(); // {text, imagePath}

        Canvas canvas = tab == null ? null : layout(session, tab, focus, dir);

        // ---- meta (index 0): canvas size, flags, window title, background
        char showTabs = tabs.size() > 1 ? 'y' : 'n';
        char empty = canvas == null ? 'y' : 'n';
        String metaPayload = windowTitle;
        if (canvas == null) {
            metaPayload += "\n" + MinecraftLocale.getLocaleString("advancements.empty", locale);
        }
        buttons.add(new String[]{
                Item.header('M', canvas == null ? VIEW_W : canvas.width, canvas == null ? VIEW_H : canvas.height,
                        "" + showTabs + empty) + metaPayload,
                tab == null ? "textures/blocks/stone" : ext.icons().background(tab.getDisplayData().getBackgroundTexture())});

        // ---- drag range (index 1): the canvas sits at the top-left of a box placed at the opening
        // scroll position, and can be dragged inside it. Bedrock only lets a contained drag move away
        // from where it was laid out (right/down), so the box reaches from there to Java's left/top
        // limit: max(canvas, canvas - scroll). Opened normally (scroll = view - canvas, the bottom-right
        // end) that is max(canvas, 2 * canvas - view), Java's whole range.
        int cw = canvas == null ? VIEW_W : canvas.width;
        int chh = canvas == null ? VIEW_H : canvas.height;
        int sx = canvas == null ? 0 : canvas.scrollX;
        int sy = canvas == null ? 0 : canvas.scrollY;
        buttons.add(new String[]{Item.header('R', new int[]{Math.max(cw, cw - sx), Math.max(chh, chh - sy),
                sx + POS_BIAS, sy + POS_BIAS}, ""), null});

        // ---- tabs (indices 2..27, Java order: above, below, left, right). Java hides them for one tab.
        // Controller bumpers: LB opens the previous tab, RB the next one (wrapping), through the
        // neighbours' buttons (flag 2: l = previous, r = next, b = both, x = neither).
        if (tabs.size() > 1) {
            List<GeyserAdvancement> shown = tabs.subList(0, Math.min(tabs.size(), MAX_TABS));
            int sel = shown.indexOf(tab);
            int prev = sel < 0 ? -1 : (sel + shown.size() - 1) % shown.size();
            int next = sel < 0 ? -1 : (sel + 1) % shown.size();
            for (int i = 0; i < shown.size(); i++) {
                GeyserAdvancement t = shown.get(i);
                String title = Text.title(t.getDisplayData(), locale);
                char bumper = i == sel ? 'x' : i == prev && i == next ? 'b' : i == prev ? 'l' : i == next ? 'r' : 'x';
                tabButtons.put(buttons.size(), t.getId());
                buttons.add(new String[]{
                        Item.header('T', 0, 0, "" + (t == tab ? 'y' : 'n') + bumper) + title,
                        iconPath(session, t.getDisplayData().getIcon())});
            }
        }

        // ---- trunks and nodes; an edge node's button responds when the D-pad presses past it
        Map<Integer, String[]> edges = new HashMap<>(); // index -> {node id, direction}
        if (canvas != null) {
            for (String[] item : canvas.items) {
                if (item.length > 3 && item[3] != null) {
                    edges.put(buttons.size(), new String[]{item[2], item[3]});
                }
                buttons.add(item);
            }
        }

        for (String[] b : buttons) {
            b[0] = Item.withIcon(b[0], b[1]);
            if (b[1] != null) {
                form.button(b[0], FormImage.Type.PATH, b[1]);
            } else {
                form.button(b[0]);
            }
        }

        String tabId = tab == null ? null : tab.getId();
        form.validResultHandler(response -> {
            String target = tabButtons.get(response.clickedButtonId());
            String[] edge = edges.get(response.clickedButtonId());
            if (target != null) {
                open(session, target);
            } else if (edge != null) {
                open(session, tabId, edge[0], edge[1].charAt(0));
            }
        });
        form.closedOrInvalidResultHandler(() ->
                session.sendDownstreamGamePacket(new ServerboundSeenAdvancementsPacket()));
        return form.build();
    }

    // ---------------------------------------------------------------- layout

    private static final class Canvas {
        int width;
        int height;
        /** Canvas position in the view when the screen opens (<= 0 when larger than the view). */
        int scrollX;
        int scrollY;
        /** Node id -> pixel position of its 28x27 cell on the canvas. */
        final Map<String, int[]> nodes = new HashMap<>();
        /** {text, image path} and for nodes {.., node id, edge direction or null}. */
        final List<String[]> items = new ArrayList<>();
    }

    /**
     * The advancement the D-pad selects: from {@code current} the nearest one in direction
     * {@code dir} (by centre distance along it, sideways distance counting double); without a
     * current one, the one nearest the view's centre.
     */
    private static String step(Map<String, int[]> nodes, String current, char dir, int viewCx, int viewCy) {
        int[] from = current == null ? null : nodes.get(current);
        if (from == null) {
            String best = null;
            long bestD = Long.MAX_VALUE;
            for (Map.Entry<String, int[]> e : nodes.entrySet()) {
                long dx = e.getValue()[0] + 16 - viewCx, dy = e.getValue()[1] + 13 - viewCy;
                long d = dx * dx + dy * dy;
                if (d < bestD) {
                    bestD = d;
                    best = e.getKey();
                }
            }
            return best;
        }
        String best = current;
        int bestScore = Integer.MAX_VALUE;
        for (Map.Entry<String, int[]> e : nodes.entrySet()) {
            int dx = e.getValue()[0] - from[0], dy = e.getValue()[1] - from[1];
            int along = switch (dir) {
                case 'l' -> -dx;
                case 'r' -> dx;
                case 'u' -> -dy;
                default -> dy;
            };
            int side = Math.abs(dir == 'l' || dir == 'r' ? dy : dx);
            if (along <= 0) continue;
            int score = along + 2 * side;
            if (score < bestScore) {
                bestScore = score;
                best = e.getKey();
            }
        }
        return best;
    }

    /** A node's frame (cell x + 3, 26x26) lies wholly inside the view at this scroll. */
    private static boolean inView(int[] p, int scrollX, int scrollY) {
        int x = scrollX + p[0] + 3, y = scrollY + p[1];
        return x >= 0 && y >= 0 && x + 26 <= VIEW_W && y + 26 <= VIEW_H;
    }

    /** Some of a node's frame shows in the view (Bedrock's navigation can reach such a node). */
    private static boolean partlyInView(int[] p, int scrollX, int scrollY) {
        int x = scrollX + p[0] + 3, y = scrollY + p[1];
        return x + 26 > 0 && y + 26 > 0 && x < VIEW_W && y < VIEW_H;
    }

    /**
     * The direction ('l', 'r', 'u', 'd') in which this (at least partly) visible node is an edge: no
     * other wholly visible node lies that way (so Bedrock's focus navigation would find nothing, a
     * clipped node, a tab or the Done button) but a hidden or clipped one does. Horizontal first;
     * null when none.
     */
    private static String edge(Map<String, int[]> nodes, String id, int scrollX, int scrollY) {
        int[] p = nodes.get(id);
        if (!partlyInView(p, scrollX, scrollY)) return null;
        for (char d : new char[]{'l', 'r', 'u', 'd'}) {
            boolean visible = false, hidden = false;
            for (Map.Entry<String, int[]> e : nodes.entrySet()) {
                if (e.getKey().equals(id)) continue;
                int dx = e.getValue()[0] - p[0], dy = e.getValue()[1] - p[1];
                int along = switch (d) {
                    case 'l' -> -dx;
                    case 'r' -> dx;
                    case 'u' -> -dy;
                    default -> dy;
                };
                if (along <= 0) continue;
                if (inView(e.getValue(), scrollX, scrollY)) visible = true;
                else hidden = true;
            }
            if (hidden && !visible) return String.valueOf(d);
        }
        return null;
    }

    private Canvas layout(GeyserSession session, GeyserAdvancement rootAdv, String focus, char dir) {
        Map<String, GeyserAdvancement> all = advancements(session);

        // children lists (sorted by id for a stable order)
        Map<String, TreeSet<String>> childrenOf = new HashMap<>();
        for (GeyserAdvancement adv : all.values()) {
            if (adv.getParentId() != null) {
                childrenOf.computeIfAbsent(adv.getParentId(), k -> new TreeSet<>()).add(adv.getId());
            }
        }
        TreeLayout.Node root = new TreeLayout.Node(rootAdv.getId());
        buildTree(root, all, childrenOf);
        TreeLayout.run(root);

        List<TreeLayout.Node> nodes = new ArrayList<>();
        TreeLayout.collect(root, nodes);

        // Pixel positions exactly like AdvancementWidget: floor(x*28), floor(y*27). Java's tab
        // scrolls over [0, maxX] x [0, maxY]; only shift if something ended up negative.
        Map<TreeLayout.Node, int[]> px = new HashMap<>();
        int minX = 0, minY = 0, maxX = 0, maxY = 0;
        for (TreeLayout.Node n : nodes) {
            int x = (int) Math.floor(n.x * 28.0F);
            int y = (int) Math.floor(n.y * 27.0F);
            px.put(n, new int[]{x, y});
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x + 28);
            maxY = Math.max(maxY, y + 27);
        }
        for (int[] p : px.values()) {
            p[0] += CANVAS_MARGIN - minX;
            p[1] += CANVAS_MARGIN - minY;
        }

        // The scrollable area reaches CANVAS_MARGIN past the outermost advancements on every side
        // (Java's stops right at them). A multiple of 16 keeps the background tiles where Java has them.
        Canvas canvas = new Canvas();
        canvas.width = maxX - minX + 2 * CANVAS_MARGIN;
        canvas.height = maxY - minY + 2 * CANVAS_MARGIN;
        // Where the canvas sits in the view when the screen opens: a canvas larger than the view
        // starts at the far end of its drag range (a Bedrock limit, see the pack), a smaller one is centred.
        int scrollX = canvas.width > VIEW_W ? VIEW_W - canvas.width : (VIEW_W - canvas.width) / 2;
        int scrollY = canvas.height > VIEW_H ? VIEW_H - canvas.height : (VIEW_H - canvas.height) / 2;
        for (TreeLayout.Node n : nodes) {
            canvas.nodes.put(n.id, px.get(n));
        }
        // D-pad: put the selected advancement's frame (cell x + 3, 26x26) under the pointer, which a
        // new form puts at the screen's centre: that is POINTER_DY above the view's centre. Also past
        // Java's scroll limits, so the selection is always hovered.
        if (dir != 0) {
            String selected = step(canvas.nodes, focus, dir, VIEW_W / 2 - scrollX, VIEW_H / 2 - scrollY);
            int[] f = selected == null ? null : canvas.nodes.get(selected);
            if (f != null) {
                scrollX = VIEW_W / 2 - (f[0] + 16);
                scrollY = VIEW_H / 2 - POINTER_DY - (f[1] + 13);
            }
        }
        canvas.scrollX = scrollX;
        canvas.scrollY = scrollY;

        // ---- connector trunks (AdvancementWidget#extractConnectivity). A child is always exactly one
        // column right of its parent, so the horizontal stubs have fixed shapes and are drawn by the
        // nodes; only the vertical part at splitX = parentX + 30 varies. Its black columns are
        // splitX -/+ 1 and the white one splitX, from the topmost to the bottommost of the parent's
        // and children's centre rows, both ends exclusive.
        for (TreeLayout.Node n : nodes) {
            if (n.children.isEmpty()) continue;
            int[] p = px.get(n);
            int lo = p[1] + 13, hi = p[1] + 13;
            for (TreeLayout.Node c : n.children) {
                int cy = px.get(c)[1] + 13;
                lo = Math.min(lo, cy);
                hi = Math.max(hi, cy);
            }
            if (hi - lo >= 2) {
                canvas.items.add(new String[]{Item.header('L', p[0] + 29, lo + 1, ""), Item.number(hi - lo - 1)});
            }
        }

        // ---- nodes
        String locale = session.locale();
        for (TreeLayout.Node n : nodes) {
            GeyserAdvancement adv = all.get(n.id);
            Advancement.DisplayData d = adv.getDisplayData();
            int[] pr = progress(session, adv);
            boolean done = pr[1] > 0 && pr[0] >= pr[1];
            int[] p = px.get(n);

            char frame = switch (d.getAdvancementType()) {
                case CHALLENGE -> 'c';
                case GOAL -> 'g';
                default -> 't';
            };
            String title = Text.title(d, locale);
            String descColor = d.getAdvancementType() == Advancement.DisplayData.AdvancementType.CHALLENGE ? "§5" : "§a";
            // Plain text: Java colours the whole description with the frame colour; Geyser's
            // formatted conversion starts with a reset code that would undo it on the first line.
            String desc = Text.plainDescription(d, locale);
            String progressText = pr[1] > 1
                    ? MinecraftLocale.getLocaleString("advancements.progress", locale)
                        .replaceFirst("%s", String.valueOf(pr[0])).replaceFirst("%s", String.valueOf(pr[1]))
                    : "";
            if (progressText.contains("%")) progressText = pr[0] + "/" + pr[1];

            // ---- tooltip geometry (AdvancementWidget constructor + extractHover)
            int titleWidth = Math.max(FontMetrics.width(title), 80);
            int maxProgressWidth = pr[1] > 1 ? FontMetrics.width(pr[1] + "/" + pr[1]) + 8 : 0;
            int longest = 29 + titleWidth + maxProgressWidth;
            List<String> descLines = FontMetrics.findOptimalLines(FontMetrics.stripFormatting(desc).isEmpty() ? "" : desc, longest);
            if (descLines.size() == 1 && descLines.get(0).isEmpty()) descLines = List.of();
            for (String line : descLines) {
                longest = Math.max(longest, FontMetrics.width(line));
            }
            int width = longest + 3 + 5;
            // Java: left if windowLeft + 9 + scrollX + x + width + 26 >= screen width;
            //       up if 113 - (scrollY + y) - 26 <= 6 + lines * 9 (here LINE, Bedrock's spacing).
            // Java draws tooltips over the window frame; here they are clipped to the view, so the
            // side is the one that stays inside the view at the opening scroll position.
            int vx = scrollX + p[0];
            boolean fitsRight = vx + width <= VIEW_W;
            boolean fitsLeft = vx + 32 - width >= 0;
            boolean leftSide = fitsRight ? false : (fitsLeft || vx + 16 > VIEW_W / 2);
            int descHeight = 6 + descLines.size() * LINE;
            int vy = scrollY + p[1];
            boolean fitsBelow = VIEW_H - vy - 26 > descHeight;
            boolean fitsAbove = vy - descHeight >= 0;
            boolean topSide = !fitsBelow && (fitsAbove || vy > VIEW_H - vy - 26);

            // First line = title (padded so the label is as wide as Java's box), then description lines.
            // Right side: title starts after the icon (x+32). Left side: icon sits at the right end.
            int textWidth = width - 8;
            StringBuilder text = new StringBuilder();
            String firstLine;
            // Starts with a colour code so Bedrock doesn't trim the indent spaces.
            if (leftSide) {
                firstLine = "§f" + title;
            } else {
                firstLine = "§f" + FontMetrics.spaces(27) + title;
            }
            // Progress ("3/14") is right-aligned at the end of the title line, as in Java.
            // Left side: Java draws it just left of the icon, i.e. 32px before the box edge.
            int progressWidth = FontMetrics.width(progressText);
            int rightGap = leftSide ? 32 - 5 : 0;
            int pad = textWidth - rightGap - FontMetrics.width(firstLine) - progressWidth;
            text.append(firstLine).append(FontMetrics.spaces(pad));
            if (!progressText.isEmpty()) {
                text.append("§f").append(progressText);
            }
            if (leftSide) {
                text.append(FontMetrics.spaces(rightGap));
            }
            for (String line : descLines) {
                text.append('\n').append(descColor).append(line);
            }

            String edge = edge(canvas.nodes, n.id, scrollX, scrollY);
            String flags = "" + frame + (done ? 'y' : 'n') + (leftSide ? 'l' : 'r') + (topSide ? 'u' : 'd')
                    + (n.parent != null ? 'y' : 'n') + (n.children.isEmpty() ? 'n' : 'y')
                    + (edge == null ? 'x' : edge.charAt(0));
            // Tooltip geometry relative to the hit area (cell x + 3), as Java's extractHover: the box
            // starts at the node's x, or ends at x + 32 when flipped left; the description box is
            // 32 + LINE per line high and opens downwards from the node's row or upwards ending at its
            // bottom; the description text starts 7 below the box top (up) or at 26 (down).
            int tipX = (leftSide ? 32 - width : 0) - 3;
            int boxH = descLines.isEmpty() ? 0 : 32 + descLines.size() * LINE;
            int tipY = topSide ? 26 - boxH : 0;
            int descY = (topSide ? 7 : 26) + 2; // + 2: the pack's text clip starts 2px lower
            // The pack sizes the tooltip from these numbers rather than from its text (sizes taken
            // from text weren't reliable) and clips the description to the box.
            // Opening upwards, the clip stops where the title bar starts (boxH - 26), so text can't
            // reach the bar or the icon even if the client's font is taller than expected.
            int descClip = descLines.isEmpty() ? 0 : Math.max(0, boxH - descY - (topSide ? 26 : 1));
            canvas.items.add(new String[]{
                    Item.header('N', new int[]{p[0], p[1], tipX + 1000, tipY + 1000, boxH, descY + 1000,
                            width, descClip}, flags) + text,
                    iconPath(session, d.getIcon()), n.id, edge});
        }
        return canvas;
    }

    private static void buildTree(TreeLayout.Node node, Map<String, GeyserAdvancement> all, Map<String, TreeSet<String>> childrenOf) {
        TreeSet<String> kids = childrenOf.get(node.id);
        if (kids == null) return;
        for (String kid : kids) {
            GeyserAdvancement adv = all.get(kid);
            if (adv == null) continue;
            if (adv.getDisplayData() != null) {
                TreeLayout.Node child = new TreeLayout.Node(kid);
                child.parent = node;
                node.children.add(child);
                buildTree(child, all, childrenOf);
            } else {
                // Invisible advancement: its children attach to the nearest visible parent (like Java).
                TreeLayout.Node ghost = new TreeLayout.Node(kid);
                buildTree(ghost, all, childrenOf);
                for (TreeLayout.Node grandchild : ghost.children) {
                    grandchild.parent = node;
                    node.children.add(grandchild);
                }
            }
        }
    }

    private String iconPath(GeyserSession session, ItemStack icon) {
        if (icon == null) return ext.icons().icon("minecraft:air", null, null);
        String javaId = "minecraft:air";
        ItemMapping mapping = null;
        try {
            mapping = session.getItemMappings().getMapping(icon.getId());
            if (mapping != null && mapping.getJavaItem() != null) {
                javaId = mapping.getJavaItem().javaIdentifier().toString();
            }
        } catch (Exception ignored) {
        }
        String model = null;
        DataComponents components = icon.getDataComponentsPatch();
        if (components != null) {
            Object key = components.get(DataComponentTypes.ITEM_MODEL); // Adventure Key (relocated on Spigot)
            if (key != null) model = Text.keyString(key);
        }
        return ext.icons().icon(javaId, model, bedrockItem(session, icon, mapping, model));
    }

    /**
     * The Bedrock item the client would show for this stack (custom items included, through Geyser's
     * own translation), as the image path the pack's item renderer reads: 'Q', runtime id + 50000
     * and the damage value, five digits each. Null when there is nothing sensible to draw.
     */
    private static String bedrockItem(GeyserSession session, ItemStack icon, ItemMapping mapping, String model) {
        try {
            ItemData data = ItemTranslator.translateToBedrock(session, icon);
            if (data == null || data.getDefinition() == null) return null;
            int id = data.getDefinition().getRuntimeId();
            if (id == 0) return null; // air
            // A non-vanilla item_model that Geyser has no custom item for falls back to the base item;
            // let the resolver try its texture guesses first.
            if (model != null && !model.startsWith("minecraft:") && mapping != null
                    && data.getDefinition().equals(mapping.getBedrockDefinition())) {
                return null;
            }
            return Item.itemRenderer(id, data.getDamage());
        } catch (Exception e) {
            return null;
        }
    }
}
