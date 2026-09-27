import QtQuick

// A site's logo, with its name on hover.
Item {
    id: root
    property string source: ""
    property string label: ""
    property int size: 16
    implicitWidth: size
    implicitHeight: size
    Accessible.role: Accessible.Graphic
    Accessible.name: label
    Image {
        anchors.fill: parent
        source: root.source ? Qt.resolvedUrl("../assets/sources/" + root.source + ".png") : ""
        sourceSize: Qt.size(root.size * 2, root.size * 2)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }
    HoverHandler { id: hover }
    Tooltip { visible: hover.hovered && !!root.label; text: root.label }
}
