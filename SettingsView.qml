pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "ui" as UI

ScrollView {
    id: root
    required property var app
    contentWidth: availableWidth
    clip: true
    ScrollBar.vertical: UI.ScrollBar { parent: root; x: root.width - width; height: root.height }
    ColumnLayout {
        width: Math.min(root.availableWidth, 760)
        spacing: 14
        UI.Label { text: "GAME VERSION"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
        UI.Label { visible: !root.app.setup.flavors.length; Layout.fillWidth: true; text: "No game versions found. Choose the World of Warcraft folder below."; color: UI.Theme.muted; wrapMode: Text.Wrap }
        Repeater {
            model: root.app.setup.flavors
            delegate: AbstractButton {
                id: flavor
                required property var modelData
                readonly property bool current: root.app.game?.key === modelData.key
                Layout.fillWidth: true
                implicitHeight: 58
                enabled: !root.app.busy
                onClicked: { if (!current) root.app.execute({action: "configure", flavor: modelData.key}) }
                background: Rectangle { radius: 10; color: flavor.current ? UI.Theme.selected : flavor.hovered ? UI.Theme.hover : UI.Theme.surface; border.color: flavor.current || flavor.activeFocus ? UI.Theme.accent : UI.Theme.border }
                contentItem: RowLayout {
                    spacing: 12
                    UI.Label { leftPadding: 14; text: flavor.current ? "●" : "○"; color: flavor.current ? UI.Theme.accent : UI.Theme.muted; font.pixelSize: 14 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        UI.Label { text: flavor.modelData.name + "  ·  " + flavor.modelData.key; font.weight: Font.DemiBold; font.pixelSize: 13 }
                        UI.Label { Layout.fillWidth: true; text: (flavor.modelData.version ? "Client " + flavor.modelData.version + "  ·  interface " + flavor.modelData.interface : "Version unknown"); color: UI.Theme.muted; font.pixelSize: 11; elide: Text.ElideRight }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
        UI.Label { text: "WORLD OF WARCRAFT FOLDER"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
        UI.Label {
            Layout.fillWidth: true
            text: (root.app.setup.root || "Not found") + (root.app.setup.configuredRoot ? "" : root.app.setup.root ? "  (found automatically)" : "")
            font.family: "Adwaita Mono"; font.pixelSize: 11; wrapMode: Text.WrapAnywhere
        }
        Repeater {
            model: root.app.setup.roots.filter(r => r !== root.app.setup.root)
            delegate: UI.ActionButton {
                required property string modelData
                Layout.fillWidth: true
                text: "Use " + modelData
                enabled: !root.app.busy
                onClicked: root.app.execute({action: "configure", root: modelData})
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            UI.SearchField { id: custom; objectName: "customRoot"; Layout.fillWidth: true; placeholderText: "…/drive_c/Program Files (x86)/World of Warcraft" }
            UI.ActionButton { text: "Use folder"; enabled: !root.app.busy && custom.text.trim().length > 0; onClicked: root.app.execute({action: "configure", root: custom.text.trim()}) }
            UI.ActionButton { visible: !!root.app.setup.configuredRoot; text: "Find automatically"; enabled: !root.app.busy; onClicked: root.app.execute({action: "configure", root: ""}) }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            UI.ActionButton { text: "Open AddOns ↗"; enabled: !!root.app.game; onClicked: Qt.openUrlExternally("file://" + root.app.game.addons) }
            UI.ActionButton { text: "Open disabled addons ↗"; enabled: !!root.app.game; onClicked: Qt.openUrlExternally("file://" + root.app.game.path + "/Interface/AddOns.disabled") }
            UI.ActionButton { text: "Open trash ↗"; onClicked: Qt.openUrlExternally("trash:///") }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
        UI.Label { text: "HOW THIS APP CHANGES YOUR GAME"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
        UI.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap; font.pixelSize: 12; lineHeight: 1.45; color: UI.Theme.muted
            text: "•  Disabling moves an addon's folders to Interface/AddOns.disabled, so it's off for every character. Enabling moves them back.\n"
                + "•  Removing and replacing move folders to the trash. Settings saved in WTF are never touched.\n"
                + "•  The game reads addons when it starts. If it's running, use /reload or restart it after changes.\n"
                + "•  The in-game AddOns list still controls per-character choices among enabled addons."
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
        UI.Label { text: "ABOUT"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
        UI.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap; font.pixelSize: 12; lineHeight: 1.45; color: UI.Theme.muted
            text: "Browse merges CurseForge, WoWInterface, and Tukui (" + (root.app.catalogInfo.count || 0).toLocaleString(Qt.locale(), "f", 0) + " addons). "
                + "CurseForge listings come from the community catalog published by the instawow project and from CFWidget; files download from CurseForge's own servers. "
                + "Wago Addons isn't included: its data needs a paid key and its site disallows automated downloads. "
                + "Add addon installs GitHub releases, CurseForge pages, or any .zip. No accounts, keys, or tracking.\n"
                + "Not affiliated with Blizzard Entertainment, CurseForge, WoWInterface, Tukui, or Wago. World of Warcraft is a trademark of Blizzard Entertainment."
        }
    }
}
