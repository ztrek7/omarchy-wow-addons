pragma Singleton
import QtQuick
import "file:///usr/share/omarchy/shell/Commons" as Omarchy

QtObject {
    id: root
    // Share Omarchy's parser, surface overrides, and semantic colors. This
    // separate window does not receive the main shell's theme-change IPC.
    property bool followTheme: true
    property Timer refresh: Timer {
        interval: 1500
        repeat: true
        running: root.followTheme
        onTriggered: {
            Omarchy.Color.colorsFile.reload()
            Omarchy.Color.shellFile.reload()
        }
    }
    readonly property color background: Omarchy.Color.menu.background
    readonly property color foreground: Omarchy.Color.menu.text
    readonly property color accent: Omarchy.Color.accent
    // Some themes use a dark gray as their urgent color; never let warnings fade into the background.
    readonly property color danger: root.readable(Omarchy.Color.urgent)
    readonly property color warning: Omarchy.Color.accent
    readonly property color muted: root.mix(root.background, root.foreground, 0.72)
    readonly property color surface: root.mix(root.background, root.foreground, 0.035)
    readonly property color hover: root.mix(root.background, root.foreground, 0.08)
    readonly property color selected: root.mix(root.background, root.accent, 0.18)
    readonly property color border: root.mix(root.background, root.foreground, 0.25)
    readonly property color accentHover: root.mix(root.accent, root.foreground, 0.18)
    readonly property color accentText: root.contrast(root.accent)
    readonly property color scrim: Qt.rgba(root.background.r, root.background.g, root.background.b, 0.72)
    function mix(a, b, fraction) {
        return Qt.rgba(a.r + (b.r - a.r) * fraction, a.g + (b.g - a.g) * fraction, a.b + (b.b - a.b) * fraction, 1)
    }
    function luminance(color) {
        function linear(v) { return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
        return 0.2126 * linear(color.r) + 0.7152 * linear(color.g) + 0.0722 * linear(color.b)
    }
    function contrast(color) {
        return root.luminance(color) > 0.179 ? "#000000" : "#ffffff"
    }
    // WCAG contrast of at least 3:1 against the window background, else the text color.
    function readable(color) {
        let a = root.luminance(color), b = root.luminance(root.background)
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) >= 3 ? color : root.foreground
    }
}
