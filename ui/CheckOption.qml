import QtQuick
import QtQuick.Controls

CheckBox {
    id: root
    // Optional site logo shown before the text.
    property string badge: ""
    implicitHeight: 38
    contentItem: Row {
        leftPadding: 27
        spacing: 6
        SourceBadge { visible: !!root.badge; source: root.badge; anchors.verticalCenter: parent.verticalCenter }
        Label { text: root.text; color: Theme.foreground; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
    }
    indicator: Rectangle {
        x: 3; y: (root.height - 18) / 2
        width: 18; height: 18; radius: 4
        color: root.checked ? Theme.accent : Theme.surface
        border.color: root.activeFocus ? Theme.foreground : Theme.border
        Label { anchors.centerIn: parent; text: root.checked ? "✓" : ""; color: Theme.accentText; font.pixelSize: 13 }
    }
}
