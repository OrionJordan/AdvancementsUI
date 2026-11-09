package dev.advancementsui.advgui;

import org.geysermc.event.subscribe.Subscribe;
import org.geysermc.geyser.api.command.Command;
import org.geysermc.geyser.api.command.CommandSource;
import org.geysermc.geyser.api.connection.GeyserConnection;
import org.geysermc.geyser.api.event.bedrock.SessionDisconnectEvent;
import org.geysermc.geyser.api.event.lifecycle.GeyserDefineCommandsEvent;
import org.geysermc.geyser.api.event.lifecycle.GeyserPostInitializeEvent;
import org.geysermc.geyser.api.extension.Extension;
import org.geysermc.geyser.session.GeyserSession;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Geyser extension that shows Bedrock players a Java-style advancements screen.
 *
 * Bedrock players open it with {@code /advancements open}.
 * The visuals come from the companion resource pack, which restyles the form.
 */
public class AdvGuiExtension implements Extension {

    private final IconResolver icons = new IconResolver();
    private final AdvancementScreen screen = new AdvancementScreen(this);
    private final Map<UUID, String> lastTab = new ConcurrentHashMap<>();

    /** Command root: {@code /advancements ...} (vanilla Java only has the singular /advancement). */
    @Override
    public String rootCommand() {
        return "advancements";
    }

    @Subscribe
    public void onPostInitialize(GeyserPostInitializeEvent event) {
        icons.load(dataFolder(), geyserApi().configDirectory(), geyserApi().packDirectory(), logger());
    }

    @Subscribe
    public void onDefineCommands(GeyserDefineCommandsEvent event) {
        event.register(Command.builder(this)
                .source(CommandSource.class)
                .name("open")
                .aliases(List.of("show", "gui"))
                .description("Open the Java-style advancements screen")
                // No permission node: on Fabric/NeoForge, Geyser checks permissions through
                // fabric-permissions-api, which without a permissions mod falls back to op-only,
                // even for nodes registered with a TRUE default. Everyone may view advancements.
                .bedrockOnly(true)
                .playerOnly(true)
                .executor((source, command, args) -> {
                    GeyserConnection connection = source.connection();
                    if (connection instanceof GeyserSession session) {
                        open(session);
                    }
                })
                .build());
    }

    @Subscribe
    public void onDisconnect(SessionDisconnectEvent event) {
        lastTab.remove(event.connection().javaUuid());
    }

    /** Opens the screen on the last tab the player looked at (Java remembers it too). */
    public void open(GeyserSession session) {
        session.ensureInEventLoop(() -> {
            try {
                screen.open(session, lastTab.get(session.javaUuid()));
            } catch (Exception e) {
                logger().error("Failed to open advancements screen", e);
            }
        });
    }

    void rememberTab(GeyserSession session, String tabId) {
        if (session.javaUuid() != null) {
            lastTab.put(session.javaUuid(), tabId);
        }
    }

    IconResolver icons() {
        return icons;
    }
}
