import QtQuick
import QtQuick.Controls

AbstractButton {
    id: root
    checkable: false
    property bool value: false
    implicitWidth: 40
    implicitHeight: 24
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.35
    background: Rectangle {
        radius: 12
        color: root.value ? Theme.accent : Theme.hover
        border.color: root.activeFocus ? Theme.foreground : "transparent"
        Rectangle {
            x: root.value ? 19 : 3
            y: 3
            width: 18
            height: 18
            radius: 9
            color: root.value ? Theme.accentText : Theme.muted
            Behavior on x { NumberAnimation { duration: 120 } }
        }
    }
}
