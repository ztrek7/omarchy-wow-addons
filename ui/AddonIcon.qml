import QtQuick

// An addon's logo or screenshot, or its first letter while none is available.
Rectangle {
    id: root
    property string image: ""
    property string name: ""
    property color letterColor: Theme.muted
    property int size: 38
    implicitWidth: size
    implicitHeight: size
    radius: Math.round(size / 4.5)
    color: Theme.hover
    clip: true
    Image {
        id: picture
        anchors.fill: parent
        source: root.image
        sourceSize: Qt.size(root.size * 2, root.size * 2)
        asynchronous: true
        fillMode: Image.PreserveAspectCrop
    }
    Label {
        anchors.centerIn: parent
        visible: picture.status !== Image.Ready
        text: root.name.slice(0, 1).toUpperCase()
        font.pixelSize: Math.round(root.size * 0.45)
        font.weight: Font.Medium
        color: root.letterColor
    }
}
