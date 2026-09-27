pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
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
                        UI.Label { text: root.app.gameLabel(flavor.modelData); font.weight: Font.DemiBold; font.pixelSize: 13 }
                        UI.Label { Layout.fillWidth: true; text: flavor.modelData.key + "  ·  " + (flavor.modelData.interface ? "interface " + flavor.modelData.interface : "version unknown"); color: UI.Theme.muted; font.pixelSize: 11; elide: Text.ElideRight }
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
        UI.Label { text: "WHAT CHANGES IN YOUR GAME FOLDER"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
        UI.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap; font.pixelSize: 12; lineHeight: 1.45; color: UI.Theme.muted
            text: "•  Turning an addon off moves its folders to Interface/AddOns.disabled, so it's off for every character. Turning it on moves them back.\n"
                + "•  Removing an addon moves it to the trash. Your addon settings in WTF are left alone.\n"
                + "•  WoW only loads addons at login. If the game is open, type /reload after making changes.\n"
                + "•  You can still turn addons on or off per character from the in-game AddOns list."
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
        UI.Label { text: "HAVING A PROBLEM?"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
        UI.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap; font.pixelSize: 12; lineHeight: 1.45; color: UI.Theme.muted
            text: "Report it on GitHub. Copy the details below and paste them into the report. They list your game version and recent activity, not your files or account."
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            UI.ActionButton { text: "Report a problem ↗"; onClicked: Qt.openUrlExternally("https://github.com/ztrek7/omarchy-wow-addons/issues/new/choose") }
            UI.ActionButton {
                id: copyDetails
                objectName: "copyDetails"
                property bool copied: false
                text: copied ? "Copied" : "Copy details for a report"
                onClicked: { Quickshell.clipboardText = root.app.reportDetails(); copied = true; copiedTimer.restart() }
                Timer { id: copiedTimer; interval: 2500; onTriggered: copyDetails.copied = false }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
        UI.Label { text: "ABOUT"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
        UI.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap; font.pixelSize: 12; lineHeight: 1.45; color: UI.Theme.muted
            text: "WoW Addons" + (root.app.setup.appVersion ? " " + root.app.setup.appVersion : "") + ". Addons come from CurseForge and WoWInterface only (" + (root.app.catalogInfo.count || 0).toLocaleString(Qt.locale(), "f", 0) + " in the catalog right now). "
                + "The CurseForge list comes from the instawow project's public catalog and from CFWidget. Files always download straight from CurseForge or WoWInterface. "
                + "Wago isn't supported because it requires a paid API key. You can still add a .zip you downloaded yourself.\n"
                + "Not affiliated with Blizzard Entertainment, CurseForge, WoWInterface, or Wago. World of Warcraft is a trademark of Blizzard Entertainment."
        }
    }
}
