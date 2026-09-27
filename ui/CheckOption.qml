import QtQuick
import QtQuick.Controls

CheckBox {
    id: root
    implicitHeight: 38
    contentItem: Label { text: root.text; color: Theme.foreground; leftPadding: 27; verticalAlignment: Text.AlignVCenter; font.pixelSize: 12 }
    indicator: Rectangle {
        x: 3; y: (root.height - 18) / 2
        width: 18; height: 18; radius: 4
        color: root.checked ? Theme.accent : Theme.surface
        border.color: root.activeFocus ? Theme.foreground : Theme.border
        Label { anchors.centerIn: parent; text: root.checked ? "✓" : ""; color: Theme.accentText; font.pixelSize: 13 }
    }
}
