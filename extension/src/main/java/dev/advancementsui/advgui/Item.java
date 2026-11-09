package dev.advancementsui.advgui;

/**
 * Encodes one form button for the JSON UI renderer.
 *
 * Every button's text starts with a fixed 43-character header that the resource pack reads with
 * JSON UI's {@code ('%.Ns' * #form_button_text)} prefix slices:
 *
 * <pre>
 *  0      'Q'
 *  1..32  eight 4-digit numbers: x, y (pixels); for nodes also the tooltip's x and y, description
 *         box height, description y, tooltip width and description clip height (tooltip numbers
 *         that can be negative are sent + 1000)
 *  33     'Z'
 *  34     kind   M meta | R drag range | N node | L connector trunk | T tab
 *  35..41 flags  kind-specific single letters
 *  42     icon   '1' when the image path is a Bedrock item for the item renderer, else '0'
 *               (set by {@link #withIcon} once the icon is known)
 *  43..   payload (free text)
 * </pre>
 *
 * JSON UI evaluates any string that starts with digits as a number (int32), so the text starts
 * with a letter: then every prefix stays a string, a field is cut out by subtracting two prefixes
 * ("Q0252" - "Q" = "0252"), and "+ 0" turns a digit field into a number. The pack sizes spacer
 * panels with {@code #size_binding_x_absolute} from these numbers, which positions each item with
 * one control per axis.
 *
 * A third number (a trunk's length) travels in the button's image path, which is otherwise
 * unused for trunks. Icons are either a texture path or a Bedrock item for the pack's item
 * renderer ({@link #itemRenderer}).
 */
final class Item {

    static final int NUMBERS = 8;
    static final int FLAGS = 7;
    static final int ICON = 1 + 4 * NUMBERS + 1 + 1 + FLAGS;
    static final int HEADER = ICON + 1;
    static final int MAX = 9999;

    private Item() {
    }

    static String header(char kind, int x, int y, String flags) {
        return header(kind, new int[]{x, y}, flags);
    }

    /** @param numbers up to eight non-negative numbers (missing ones are 0) */
    static String header(char kind, int[] numbers, String flags) {
        StringBuilder sb = new StringBuilder(HEADER + 32);
        sb.append('Q');
        for (int i = 0; i < NUMBERS; i++) {
            digits(sb, i < numbers.length ? numbers[i] : 0);
        }
        sb.append('Z').append(kind);
        String f = flags == null ? "" : flags;
        if (f.length() > FLAGS) throw new IllegalArgumentException("too many flags: " + f);
        sb.append(f).append("x".repeat(FLAGS - f.length())).append('0');
        if (sb.length() != HEADER) {
            throw new IllegalStateException("bad header length " + sb.length());
        }
        return sb.toString();
    }

    /** Bias that keeps Bedrock runtime ids (block items are negative) positive in five digits. */
    static final int ITEM_ID_BIAS = 50000;

    /**
     * Image path that tells the pack to draw a Bedrock item with its inventory item renderer instead
     * of a texture: 'Q', runtime id + 50000 (5 digits), damage (5 digits). The pack computes
     * #item_id_aux = id * 65536 + damage from it.
     */
    static String itemRenderer(int runtimeId, int damage) {
        int id = runtimeId + ITEM_ID_BIAS;
        if (id < 0 || id > 99999) return null;
        int aux = Math.max(0, Math.min(32767, damage));
        return String.format("Q%05d%05d", id, aux);
    }

    /** Sets the icon-kind digit of a button text from its image path. */
    static String withIcon(String text, String imagePath) {
        if (text.length() < HEADER) return text;
        char kind = imagePath != null && imagePath.startsWith("Q") ? '1' : '0';
        return text.substring(0, ICON) + kind + text.substring(ICON + 1);
    }

    static String number(int v) {
        StringBuilder sb = new StringBuilder(4);
        digits(sb, v);
        return sb.toString();
    }

    private static void digits(StringBuilder sb, int v) {
        v = Math.max(0, Math.min(MAX, v));
        String s = Integer.toString(v);
        sb.append("0".repeat(4 - s.length())).append(s);
    }
}
