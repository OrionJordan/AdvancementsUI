package dev.advancementsui.advgui;

import java.util.ArrayList;
import java.util.List;

/**
 * Glyph advances of the default Minecraft bitmap font (shared by Java and Bedrock),
 * used to size and word-wrap tooltips the same way Java's AdvancementWidget does.
 */
final class FontMetrics {

    private FontMetrics() {
    }

    static int charWidth(char c) {
        switch (c) {
            case ' ': return 4;
            case '!': case '\'': case ',': case '.': case ':': case ';': case 'i': case '|': return 2;
            case '`': case 'l': return 3;
            case '"': case '(': case ')': case '*': case 'I': case '[': case ']': case 't': case '{': case '}': return 4;
            case '<': case '>': case 'f': case 'k': return 5;
            case '@': case '~': return 7;
            default: return 6;
        }
    }

    /** Width of a string that may contain § formatting codes. */
    static int width(String s) {
        int w = 0;
        boolean bold = false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '§' && i + 1 < s.length()) {
                char code = Character.toLowerCase(s.charAt(++i));
                if (code == 'l') {
                    bold = true;
                } else if (code == 'r' || (code >= '0' && code <= '9') || (code >= 'a' && code <= 'f')) {
                    bold = false;
                }
                continue;
            }
            w += charWidth(c) + (bold ? 1 : 0);
        }
        return w;
    }

    static String stripFormatting(String s) {
        return s.replaceAll("§.", "");
    }

    /** Greedy word wrap at {@code maxWidth} pixels (like Java's StringSplitter#splitLines). */
    static List<String> wrap(String text, int maxWidth) {
        List<String> lines = new ArrayList<>();
        for (String paragraph : text.split("\n", -1)) {
            StringBuilder line = new StringBuilder();
            int lineWidth = 0;
            for (String word : paragraph.split(" ", -1)) {
                int wordWidth = width(word);
                int spaceWidth = line.length() == 0 ? 0 : charWidth(' ');
                if (line.length() > 0 && lineWidth + spaceWidth + wordWidth > maxWidth) {
                    lines.add(line.toString());
                    line.setLength(0);
                    lineWidth = 0;
                    spaceWidth = 0;
                }
                // A single word longer than the line gets broken by characters.
                while (line.length() == 0 && wordWidth > maxWidth && word.length() > 1) {
                    int cut = 1;
                    while (cut < word.length() && width(word.substring(0, cut + 1)) <= maxWidth) {
                        cut++;
                    }
                    lines.add(word.substring(0, cut));
                    word = word.substring(cut);
                    wordWidth = width(word);
                }
                if (spaceWidth > 0) {
                    line.append(' ');
                }
                line.append(word);
                lineWidth += spaceWidth + wordWidth;
            }
            lines.add(line.toString());
        }
        return lines;
    }

    private static final int[] TEST_SPLIT_OFFSETS = {0, 10, -10, 25, -25};

    /** Java's AdvancementWidget#findOptimalLines. */
    static List<String> findOptimalLines(String text, int preferredWidth) {
        List<String> best = null;
        float bestDistance = Float.MAX_VALUE;
        for (int margin : TEST_SPLIT_OFFSETS) {
            List<String> split = wrap(text, preferredWidth - margin);
            int max = 0;
            for (String l : split) {
                max = Math.max(max, width(l));
            }
            float distance = Math.abs(max - preferredWidth);
            if (distance <= 10.0F) {
                return split;
            }
            if (distance < bestDistance) {
                bestDistance = distance;
                best = split;
            }
        }
        return best;
    }

    /** Spaces needed to cover at least {@code px} pixels. */
    static String spaces(int px) {
        return " ".repeat(Math.max(0, (px + 3) / 4));
    }
}
