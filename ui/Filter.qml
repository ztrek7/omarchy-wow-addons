pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls

ComboBox {
    id: root
    implicitHeight: 38
    implicitWidth: 158
    leftPadding: 12
    rightPadding: 28
    contentItem: Label {
        color: Theme.foreground
        text: root.displayText
        verticalAlignment: Text.AlignVCenter
        font.pixelSize: 12
        elide: Text.ElideRight
    }
    indicator: Label { x: root.width - 23; y: 9; text: "⌄"; color: Theme.muted }
    background: Rectangle {
        color: Theme.surface
        radius: 8
        border.color: root.activeFocus ? Theme.accent : Theme.border
    }
    delegate: ItemDelegate {
        id: option
        required property var modelData
        required property int index
        width: root.width
        highlighted: root.highlightedIndex === index
        contentItem: Label { color: Theme.foreground; text: option.modelData; font.pixelSize: 12 }
        background: Rectangle { color: option.highlighted ? Theme.selected : Theme.surface; radius: 6 }
    }
    popup: Popup {
        y: root.height + 5
        width: root.width
        padding: 5
        // Long lists (catalog categories) scroll instead of running off the window.
        implicitHeight: Math.min(contentItem.implicitHeight + 10, 440)
        background: Rectangle { color: Theme.surface; border.color: Theme.border; radius: 9 }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollBar.vertical: ScrollBar {}
        }
    }
}
