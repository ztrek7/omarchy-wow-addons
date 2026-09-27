import QtQuick
import QtQuick.Controls as Controls

Controls.ScrollBar {
    id: root
    // Hidden when everything fits, so no stray handle sits over the content.
    visible: size < 1
    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 6
        radius: 3
        color: root.pressed ? Theme.accent : Theme.muted
        opacity: root.active ? 0.8 : 0.35
    }
    background: Rectangle { color: "transparent" }
}
