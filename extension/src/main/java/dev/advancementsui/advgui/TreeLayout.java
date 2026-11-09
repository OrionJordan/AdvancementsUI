package dev.advancementsui.advgui;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Port of Minecraft Java's {@code net.minecraft.advancements.TreeNodePosition}
 * (Walker / Buchheim tree layout), so Bedrock players see the advancement tree in
 * exactly the same arrangement as Java players.
 *
 * Geyser does not keep the x/y the Java server computes, so we recompute it here.
 */
final class TreeLayout {

    /** A displayable advancement in the tab. */
    static final class Node {
        final String id;
        final List<Node> children = new ArrayList<>();
        Node parent;
        float x;
        float y;

        Node(String id) {
            this.id = id;
        }
    }

    private static final class Pos {
        final Node node;
        final Pos parent;
        final Pos previousSibling;
        final int childIndex;
        final List<Pos> children = new ArrayList<>();
        Pos ancestor;
        Pos thread;
        int x;
        float y;
        float mod;
        float change;
        float shift;

        Pos(Node node, Pos parent, Pos previousSibling, int childIndex, int depth) {
            this.node = node;
            this.parent = parent;
            this.previousSibling = previousSibling;
            this.childIndex = childIndex;
            this.ancestor = this;
            this.x = depth;
            this.y = -1.0F;
            Pos previous = null;
            for (Node child : node.children) {
                previous = new Pos(child, this, previous, this.children.size() + 1, this.x + 1);
                this.children.add(previous);
            }
        }

        void firstWalk() {
            if (children.isEmpty()) {
                y = previousSibling != null ? previousSibling.y + 1.0F : 0.0F;
            } else {
                Pos defaultAncestor = null;
                for (Pos child : children) {
                    child.firstWalk();
                    defaultAncestor = child.apportion(defaultAncestor == null ? child : defaultAncestor);
                }
                executeShifts();
                float midpoint = (children.get(0).y + children.get(children.size() - 1).y) / 2.0F;
                if (previousSibling != null) {
                    y = previousSibling.y + 1.0F;
                    mod = y - midpoint;
                } else {
                    y = midpoint;
                }
            }
        }

        float secondWalk(float modSum, int depth, float min) {
            y += modSum;
            x = depth;
            if (y < min) {
                min = y;
            }
            for (Pos child : children) {
                min = child.secondWalk(modSum + mod, depth + 1, min);
            }
            return min;
        }

        void thirdWalk(float offset) {
            y += offset;
            for (Pos child : children) {
                child.thirdWalk(offset);
            }
        }

        void executeShifts() {
            float shift = 0.0F;
            float change = 0.0F;
            for (int i = children.size() - 1; i >= 0; i--) {
                Pos child = children.get(i);
                child.y += shift;
                child.mod += shift;
                change += child.change;
                shift += child.shift + change;
            }
        }

        Pos previousOrThread() {
            if (thread != null) return thread;
            return !children.isEmpty() ? children.get(0) : null;
        }

        Pos nextOrThread() {
            if (thread != null) return thread;
            return !children.isEmpty() ? children.get(children.size() - 1) : null;
        }

        Pos apportion(Pos defaultAncestor) {
            if (previousSibling == null) {
                return defaultAncestor;
            }
            Pos vir = this;
            Pos vor = this;
            Pos vil = previousSibling;
            Pos vol = parent.children.get(0);
            float sir = mod;
            float sor = mod;
            float sil = vil.mod;
            float sol = vol.mod;
            while (vil.nextOrThread() != null && vir.previousOrThread() != null) {
                vil = vil.nextOrThread();
                vir = vir.previousOrThread();
                vol = vol.previousOrThread();
                vor = vor.nextOrThread();
                vor.ancestor = this;
                float shift = vil.y + sil - (vir.y + sir) + 1.0F;
                if (shift > 0.0F) {
                    vil.getAncestor(this, defaultAncestor).moveSubtree(this, shift);
                    sir += shift;
                    sor += shift;
                }
                sil += vil.mod;
                sir += vir.mod;
                sol += vol.mod;
                sor += vor.mod;
            }
            if (vil.nextOrThread() != null && vor.nextOrThread() == null) {
                vor.thread = vil.nextOrThread();
                vor.mod += sil - sor;
            } else {
                if (vir.previousOrThread() != null && vol.previousOrThread() == null) {
                    vol.thread = vir.previousOrThread();
                    vol.mod += sir - sol;
                }
                defaultAncestor = this;
            }
            return defaultAncestor;
        }

        void moveSubtree(Pos right, float shift) {
            float subtrees = right.childIndex - childIndex;
            if (subtrees != 0.0F) {
                right.change -= shift / subtrees;
                change += shift / subtrees;
            }
            right.shift += shift;
            right.y += shift;
            right.mod += shift;
        }

        Pos getAncestor(Pos other, Pos defaultAncestor) {
            return ancestor != null && other.parent.children.contains(ancestor) ? ancestor : defaultAncestor;
        }

        void finalizePosition() {
            node.x = x;
            node.y = y;
            for (Pos child : children) {
                child.finalizePosition();
            }
        }
    }

    private TreeLayout() {
    }

    /** Lays out the tree rooted at {@code root}, writing {@link Node#x}/{@link Node#y}. */
    static void run(Node root) {
        Pos pos = new Pos(root, null, null, 1, 0);
        pos.firstWalk();
        float min = pos.secondWalk(0.0F, 0, pos.y);
        if (min < 0.0F) {
            pos.thirdWalk(-min);
        }
        pos.finalizePosition();
    }

    /** Collects every node of the tree, parents before children. */
    static void collect(Node node, List<Node> out) {
        out.add(node);
        for (Node child : node.children) {
            collect(child, out);
        }
    }

    static Map<String, Node> index(Node root, Map<String, Node> out) {
        out.put(root.id, root);
        for (Node child : root.children) {
            index(child, out);
        }
        return out;
    }
}
