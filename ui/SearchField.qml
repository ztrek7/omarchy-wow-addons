import QtQuick
import QtQuick.Controls

TextField {
    id: root
    implicitHeight: 38
    selectionColor: Theme.selected
    selectedTextColor: Theme.foreground
    placeholderTextColor: Theme.muted
    color: Theme.foreground
    font.family: "Adwaita Sans"
    font.pixelSize: 13
    leftPadding: 13
    selectByMouse: true
    background: Rectangle { color: Theme.surface; radius: 8; border.color: root.activeFocus ? Theme.accent : Theme.border }
}
