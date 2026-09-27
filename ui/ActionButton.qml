import QtQuick
import QtQuick.Controls

Button {
    id: root
    property bool primary: false
    property bool danger: false
    implicitHeight: 38
    implicitWidth: label.implicitWidth + 28
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.38
    contentItem: Label {
        id: label
        text: root.text
        color: root.primary ? Theme.accentText : root.danger ? Theme.danger : Theme.foreground
        font.pixelSize: 13
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        radius: 9
        color: root.primary ? (root.hovered ? Theme.accentHover : Theme.accent) : root.hovered ? Theme.hover : Theme.surface
        border.width: 1
        border.color: root.activeFocus ? Theme.accent : root.primary ? "transparent" : Theme.border
        Behavior on color { ColorAnimation { duration: 100 } }
    }
}
