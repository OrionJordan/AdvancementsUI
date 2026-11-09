package dev.advancementsui.advgui;

import org.geysermc.geyser.translator.text.MessageTranslator;
import org.geysermc.mcprotocollib.protocol.data.game.advancement.Advancement;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Adventure access without linking against Adventure types.
 *
 * Geyser-Spigot relocates Adventure (to {@code org.geysermc.geyser.platform.spigot.shaded.net.kyori...}),
 * while Geyser-Fabric/NeoForge/Standalone don't, so any compiled call whose signature mentions
 * {@code Component} or {@code Key} fails with NoSuchMethodError on one platform or the other.
 * Everything here goes through reflection, looked up once and cached.
 */
final class Text {

    private static final Map<String, Method> CACHE = new ConcurrentHashMap<>();

    private Text() {
    }

    /** Formatted title, as {@code MessageTranslator.convertMessage(d.getTitle(), locale)}. */
    static String title(Advancement.DisplayData d, String locale) {
        return translate("convertMessage", invoke(d, "getTitle"), locale);
    }

    /** Description without formatting, as {@code MessageTranslator.convertToPlainText(...)}. */
    static String plainDescription(Advancement.DisplayData d, String locale) {
        return translate("convertToPlainText", invoke(d, "getDescription"), locale);
    }

    /** {@code Key#asString()} for a key of whichever (possibly relocated) Adventure is present. */
    static String keyString(Object key) {
        if (key == null) return null;
        Object s = invoke(key, "asString");
        return s == null ? key.toString() : s.toString();
    }

    private static Object invoke(Object target, String name) {
        Method m = CACHE.computeIfAbsent(target.getClass().getName() + "#" + name,
                k -> publicMethod(target.getClass(), name, k));
        try {
            return m.invoke(target);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("Calling " + name + " failed", e);
        }
    }

    /**
     * The no-arg method {@code name} as declared by a public type. Implementation classes such as
     * Adventure's KeyImpl are package-private, and their own Method objects can't be invoked.
     */
    private static Method publicMethod(Class<?> type, String name, String what) {
        Deque<Class<?>> queue = new ArrayDeque<>();
        queue.add(type);
        while (!queue.isEmpty()) {
            Class<?> c = queue.poll();
            if (Modifier.isPublic(c.getModifiers())) {
                try {
                    return c.getMethod(name);
                } catch (NoSuchMethodException ignored) {
                }
            }
            if (c.getSuperclass() != null) queue.add(c.getSuperclass());
            queue.addAll(Arrays.asList(c.getInterfaces()));
        }
        throw new IllegalStateException("No public method " + what);
    }

    /** Calls the static {@code MessageTranslator.<name>(Component, String)}. */
    private static String translate(String name, Object component, String locale) {
        if (component == null) return "";
        Method m = CACHE.computeIfAbsent("MessageTranslator#" + name, k -> {
            for (Method candidate : MessageTranslator.class.getMethods()) {
                Class<?>[] p = candidate.getParameterTypes();
                if (candidate.getName().equals(name) && p.length == 2 && p[1] == String.class
                        && p[0].getSimpleName().equals("Component")) {
                    return candidate;
                }
            }
            throw new IllegalStateException("No MessageTranslator." + name + "(Component, String)");
        });
        try {
            return (String) m.invoke(null, component, locale);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("MessageTranslator." + name + " failed", e);
        }
    }
}
