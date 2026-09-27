import QtQuick
import QtQuick.Controls as Controls

Controls.ToolTip {
    id: root
    contentItem: Label { text: root.text; wrapMode: Text.Wrap; font.pixelSize: 11 }
    background: Rectangle { color: Theme.background; border.color: Theme.border; radius: 6 }
    width: Math.min(400, implicitWidth)
}
