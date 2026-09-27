import QtQuick

Rectangle {
    id: root
    property string text: ""
    property color ink: Theme.muted
    implicitWidth: label.implicitWidth + 16
    implicitHeight: 24
    radius: 6
    color: Qt.rgba(ink.r, ink.g, ink.b, 0.09)
    Label {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.ink
        font.pixelSize: 11
        font.weight: Font.Medium
    }
}
