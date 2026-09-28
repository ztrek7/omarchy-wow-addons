pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "ui" as UI

Item {
    id: root
    required property var app
    property string selectedId: ""
    readonly property var selected: app.addons.find(a => a.id === selectedId) || null
    readonly property var results: {
        let term = search.text.toLowerCase().trim()
        let status = statusFilter.currentIndex, origin = sourceFilter.currentIndex
        let found = app.addons.filter(a => {
            let text = (a.name + " " + a.notes + " " + a.author + " " + a.dirs.map(d => d.name).join(" ")).toLowerCase()
            return (!term || text.indexOf(term) >= 0)
                && (status === 0 || (status === 1 && a.state !== "disabled") || (status === 2 && a.state !== "enabled")
                    || (status === 3 && root.app.checks[a.id]?.state === "available") || (status === 4 && a.outOfDate)
                    || (status === 5 && (a.missing.length > 0 || a.requiresDisabled.length > 0)))
                && (origin === 0 || a.source === ["", "curseforge", "wowinterface"][origin]
                    || (origin === 3 && !a.managed) || (origin === 4 && a.source === "file"))
        })
        let sort = sortFilter.currentIndex
        return found.sort((a, b) => {
            if (sort === 1) return b.name.localeCompare(a.name)
            if (sort === 2) return (b.installedAt || "").localeCompare(a.installedAt || "") || a.name.localeCompare(b.name)
            if (sort === 3) return root.attention(b) - root.attention(a) || a.name.localeCompare(b.name)
            if (sort === 4) return b.dirs.length - a.dirs.length || a.name.localeCompare(b.name)
            return a.name.localeCompare(b.name)
        })
    }
    onResultsChanged: { if (!results.some(a => a.id === selectedId)) selectedId = results.length ? results[0].id : "" }
    function focusSearch() { search.forceActiveFocus() }
    // Escape clears a search before it closes the window.
    function clearSearch() {
        if (!search.activeFocus || !search.text) return false
        search.text = ""
        return true
    }
    // Missing requirements first, then updates, then out-of-date addons.
    function attention(a) {
        return (a.missing.length || a.requiresDisabled.length ? 4 : 0) + (app.checks[a.id]?.state === "available" ? 2 : 0) + (a.outOfDate ? 1 : 0)
    }
    function badges(addon) {
        let list = []
        if (addon.missing.length) list.push({text: "Needs " + addon.missing.join(", "), ink: UI.Theme.danger})
        if (addon.requiresDisabled.length) list.push({text: "Needs " + addon.requiresDisabled.join(", ") + " on", ink: UI.Theme.danger})
        let check = app.checks[addon.id]
        if (check?.state === "available") list.push({text: "Update → " + check.latest, ink: UI.Theme.accent})
        if (check?.state === "error") list.push({text: "Check failed", ink: UI.Theme.danger})
        if (!addon.loadable) list.push({text: "Not for this game", ink: UI.Theme.danger})
        else if (addon.outOfDate) list.push({text: "Out of date", ink: UI.Theme.warning})
        if (addon.state === "partial") list.push({text: "Partly disabled", ink: UI.Theme.muted})
        return list
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            UI.Pill { text: root.app.addons.length + " addons"; ink: UI.Theme.foreground }
            UI.Pill { text: root.app.enabledCount + " enabled"; ink: UI.Theme.accent }
            UI.Pill { visible: root.app.addons.length > root.app.enabledCount; text: (root.app.addons.length - root.app.enabledCount) + " disabled"; ink: UI.Theme.muted }
            UI.Pill { visible: root.app.updateIds.length > 0; text: root.app.updateIds.length + (root.app.updateIds.length === 1 ? " update" : " updates"); ink: UI.Theme.warning }
            UI.Pill { visible: root.app.outOfDateCount > 0; text: root.app.outOfDateCount + " out of date"; ink: UI.Theme.warning }
            Item { Layout.fillWidth: true }
            UI.Label { visible: !!root.app.lastChecked; text: "Last checked " + root.app.lastChecked; color: UI.Theme.muted; font.pixelSize: 11 }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            UI.SearchField { id: search; objectName: "installedSearch"; Layout.fillWidth: true; Layout.minimumWidth: 160; placeholderText: "Search installed addons, notes, or folders…" }
            UI.Filter { id: statusFilter; objectName: "statusFilter"; Layout.fillWidth: true; Layout.preferredWidth: 170; Layout.minimumWidth: 120; model: ["Any status", "Enabled", "Disabled", "Update available", "Out of date", "Missing requirements"] }
            UI.Filter { id: sourceFilter; objectName: "sourceFilter"; Layout.fillWidth: true; Layout.preferredWidth: 160; Layout.minimumWidth: 120; model: ["All sources", "CurseForge", "WoWInterface", "Manual installs", "Zip files"] }
            UI.Filter { id: sortFilter; objectName: "installedSort"; Layout.fillWidth: true; Layout.preferredWidth: 180; Layout.minimumWidth: 120; model: ["Name A–Z", "Name Z–A", "Recently installed", "Needs attention", "Most folders"] }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 18
            ListView {
                id: list
                objectName: "installedList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 7
                model: root.results
                ScrollBar.vertical: UI.ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    readonly property bool current: root.selectedId === modelData.id
                    // Its Browse listing, for the icon. The catalog may load after the list does.
                    readonly property var entry: root.app.rowEntries[modelData.id] || null
                    readonly property string logoSlug: root.app.cfSlug(entry)
                    onLogoSlugChanged: root.app.wantLogo(logoSlug)
                    Component.onCompleted: root.app.wantLogo(logoSlug)
                    activeFocusOnTab: true
                    Accessible.role: Accessible.ListItem
                    Accessible.name: modelData.name + ", " + modelData.state
                    Keys.onReturnPressed: root.selectedId = modelData.id
                    Keys.onSpacePressed: root.app.toggle(modelData)
                    width: list.width - 10
                    height: 92
                    radius: 10
                    color: current ? UI.Theme.selected : rowMouse.containsMouse ? UI.Theme.hover : UI.Theme.surface
                    border.color: activeFocus || current ? UI.Theme.accent : UI.Theme.border
                    opacity: modelData.state === "disabled" ? 0.72 : 1
                    MouseArea { id: rowMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.selectedId = row.modelData.id }
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 12
                        UI.AddonIcon {
                            size: 44
                            image: root.app.iconFor(row.entry)
                            name: row.modelData.name
                            letterColor: row.modelData.managed ? UI.Theme.accent : UI.Theme.foreground
                        }
                        ColumnLayout {
                            // Fill what's left beside the toggle instead of growing with long badges.
                            Layout.fillWidth: true
                            Layout.preferredWidth: 0
                            spacing: 4
                            UI.Label { Layout.fillWidth: true; text: row.modelData.name; elide: Text.ElideRight; font.weight: Font.DemiBold }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                UI.SourceBadge {
                                    visible: root.app.hasLogo(row.modelData.source)
                                    source: visible ? row.modelData.source : ""
                                    label: "Installed from " + root.app.sourceName(row.modelData.source)
                                    size: 13
                                }
                                UI.Label {
                                    Layout.fillWidth: true
                                    text: [root.app.versionText(row.modelData.version), root.app.hasLogo(row.modelData.source) ? "" : root.app.sourceName(row.modelData.source),
                                           row.modelData.dirs.length + (row.modelData.dirs.length === 1 ? " folder" : " folders")].filter(x => x).join("  ·  ")
                                    color: UI.Theme.muted; font.pixelSize: 10; elide: Text.ElideRight
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                clip: true
                                spacing: 6
                                UI.Label { visible: !root.badges(row.modelData).length; Layout.fillWidth: true; text: row.modelData.notes; color: UI.Theme.muted; font.pixelSize: 11; elide: Text.ElideRight }
                                Repeater {
                                    model: root.badges(row.modelData)
                                    delegate: UI.Pill { required property var modelData; text: modelData.text; ink: modelData.ink; implicitHeight: 20 }
                                }
                            }
                        }
                        UI.Toggle {
                            objectName: "toggle-" + row.modelData.id
                            value: row.modelData.state === "enabled"
                            enabled: !root.app.busy
                            Accessible.name: (value ? "Disable " : "Enable ") + row.modelData.name
                            onClicked: { root.selectedId = row.modelData.id; root.app.toggle(row.modelData) }
                        }
                    }
                }
                UI.Label {
                    anchors.centerIn: parent
                    width: parent.width - 40
                    visible: root.results.length === 0
                    text: root.app.busy ? "Loading…"
                        : !root.app.game ? "No World of Warcraft install found.\nSet its folder in Settings."
                        : root.app.addons.length === 0 ? "No addons installed yet.\nFind some in Browse, or use Add addon."
                        : "No addons match.\nTry another search or filter."
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    lineHeight: 1.5
                    color: UI.Theme.muted
                }
            }
            Rectangle {
                visible: !!root.selected
                Layout.preferredWidth: 330
                Layout.fillHeight: true
                radius: 13
                color: UI.Theme.background
                border.color: UI.Theme.border
                ScrollView {
                    id: detailScroll
                    anchors.fill: parent
                    anchors.margins: 20
                    clip: true
                    contentWidth: availableWidth
                    ScrollBar.vertical: UI.ScrollBar { parent: detailScroll; x: detailScroll.width - width + 12; height: detailScroll.height }
                    ColumnLayout {
                        width: parent.width
                        spacing: 13
                        readonly property var addon: root.selected
                        readonly property var check: addon ? root.app.checks[addon.id] : null
                        id: detail
                        UI.Label { text: "ADDON DETAILS"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            UI.AddonIcon {
                                objectName: "detailIcon"
                                Layout.alignment: Qt.AlignTop
                                size: 52
                                image: detail.addon ? root.app.iconFor(root.app.rowEntries[detail.addon.id]) : ""
                                name: detail.addon?.name || ""
                            }
                            UI.Label { objectName: "detailName"; Layout.fillWidth: true; text: detail.addon?.name || ""; font.pixelSize: 23; font.weight: Font.DemiBold; wrapMode: Text.Wrap }
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle {
                                implicitWidth: sourceRow.implicitWidth + 16; implicitHeight: 24; radius: 6
                                color: Qt.rgba(UI.Theme.foreground.r, UI.Theme.foreground.g, UI.Theme.foreground.b, 0.09)
                                RowLayout {
                                    id: sourceRow
                                    anchors.centerIn: parent
                                    spacing: 6
                                    UI.SourceBadge { visible: root.app.hasLogo(detail.addon?.source); source: visible ? detail.addon.source : ""; size: 14 }
                                    UI.Label { text: root.app.sourceName(detail.addon?.source || ""); font.pixelSize: 11; font.weight: Font.Medium }
                                }
                            }
                            UI.Pill { text: ({enabled: "Enabled", disabled: "Disabled", partial: "Partly disabled"})[detail.addon?.state] || ""; ink: detail.addon?.state === "enabled" ? UI.Theme.accent : UI.Theme.muted }
                            Repeater {
                                model: detail.addon ? root.badges(detail.addon) : []
                                delegate: UI.Pill { required property var modelData; text: modelData.text; ink: modelData.ink }
                            }
                        }
                        UI.Label { visible: !!detail.addon?.notes; Layout.fillWidth: true; text: detail.addon?.notes || ""; wrapMode: Text.WordWrap; font.pixelSize: 12; color: UI.Theme.muted; lineHeight: 1.4 }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
                        Repeater {
                            model: detail.addon ? [
                                ["Version", detail.addon.version || "—"],
                                ["Author", detail.addon.author || "—"],
                                ["Category", detail.addon.category || "—"],
                                ["Addon interface", detail.addon.interfaces.length ? detail.addon.interfaces.join(", ") : "—"],
                                ["Game interface", root.app.game?.interface || "—"],
                                ["Installed", detail.addon.installedAt ? root.app.fullDate(detail.addon.installedAt) : "—"]
                            ] : []
                            delegate: RowLayout {
                                id: fact
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 12
                                UI.Label { Layout.preferredWidth: 96; text: fact.modelData[0]; color: UI.Theme.muted; font.pixelSize: 11 }
                                UI.Label { Layout.fillWidth: true; text: String(fact.modelData[1]); font.pixelSize: 11; wrapMode: Text.WrapAnywhere }
                            }
                        }
                        UI.Label {
                            visible: detail.addon?.outOfDate === true
                            Layout.fillWidth: true
                            text: "This addon doesn't list your game's interface version. The game loads it only with “Load out of date AddOns” checked, and it may not work."
                            color: UI.Theme.warning; font.pixelSize: 11; wrapMode: Text.WordWrap
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            visible: !!detail.addon && (detail.addon.missing.length > 0 || detail.addon.requiresDisabled.length > 0)
                            spacing: 8
                            UI.Label { text: "REQUIREMENTS"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                            UI.Label {
                                Layout.fillWidth: true
                                text: detail.addon ? [detail.addon.missing.length ? "Needs " + detail.addon.missing.join(", ") + ", which isn't installed." : "",
                                                      detail.addon.requiresDisabled.length ? "Needs " + detail.addon.requiresDisabled.join(", ") + ", which is turned off." : ""].filter(x => x).join(" ")
                                    + " It won't load in game until then." : ""
                                color: UI.Theme.danger; font.pixelSize: 12; wrapMode: Text.WordWrap
                            }
                            UI.ActionButton {
                                objectName: "requirementsButton"
                                text: "Install what it needs"
                                primary: true
                                enabled: !root.app.busy
                                onClicked: root.app.execute({action: "requirements", id: detail.addon.id})
                            }
                        }
                        UI.Label { text: "FOLDERS"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                        Repeater {
                            model: detail.addon?.dirs || []
                            delegate: UI.Label {
                                required property var modelData
                                Layout.fillWidth: true
                                text: (modelData.enabled ? "●  " : "○  ") + modelData.name + (modelData.outOfDate ? "  · out of date" : "")
                                color: modelData.enabled ? UI.Theme.foreground : UI.Theme.muted
                                font.family: "Adwaita Mono"; font.pixelSize: 11; elide: Text.ElideRight
                            }
                        }
                        UI.Label {
                            visible: (detail.addon?.savedVariables.length || 0) > 0
                            Layout.fillWidth: true
                            text: detail.addon ? detail.addon.savedVariables.length + " saved variable" + (detail.addon.savedVariables.length === 1 ? "" : "s") + " in WTF, kept if you remove it." : ""
                            color: UI.Theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap
                        }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
                        UI.Label { text: "UPDATES"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                        UI.Label {
                            Layout.fillWidth: true
                            text: !detail.addon ? ""
                                : detail.addon.source === "file" ? "Installed from a .zip, so it isn't checked. Install a newer .zip to update it."
                                : !detail.addon.links.length ? "Its files don't say where it's published on CurseForge or WoWInterface, so it isn't checked. Reinstall it from Browse to get updates."
                                : detail.check?.state === "available" ? "Version " + detail.check.latest + " is available from " + root.app.sourceName(detail.check.source) + "."
                                : detail.check?.state === "current" ? "Up to date with " + root.app.sourceName(detail.check.source) + " (" + detail.check.latest + ")."
                                : detail.check?.state === "error" ? "Couldn't check. " + detail.check.message
                                : detail.check?.state === "unknown" ? detail.check.message
                                : "Not checked yet."
                            color: detail.check?.state === "error" ? UI.Theme.danger : detail.check?.state === "available" ? UI.Theme.accent : UI.Theme.muted
                            font.pixelSize: 12; wrapMode: Text.WordWrap
                        }
                        UI.Label {
                            visible: !!detail.addon && !detail.addon.managed && detail.addon.links.length > 0
                            Layout.fillWidth: true
                            text: detail.addon ? "Installed by hand. Checked through " + detail.addon.links.map(l => root.app.sourceName(l.source)).join(", then ") + ", as listed in its files. Updating replaces the folder and tracks it from then on." : ""
                            color: UI.Theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap
                        }
                        UI.ActionButton {
                            visible: detail.check?.state === "available"
                            text: "Install update"
                            primary: true
                            enabled: !root.app.busy
                            onClicked: root.app.update([detail.addon.id])
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 8
                            UI.ActionButton { text: "Open folder ↗"; enabled: !!detail.addon?.path; onClicked: Qt.openUrlExternally("file://" + detail.addon.path) }
                            UI.ActionButton { text: "Website ↗"; visible: (detail.addon?.website || "").indexOf("https://") === 0; onClicked: Qt.openUrlExternally(detail.addon.website) }
                        }
                        UI.ActionButton {
                            objectName: "removeButton"
                            text: "Remove…"
                            danger: true
                            enabled: !root.app.busy
                            onClicked: root.app.confirm("remove", detail.addon)
                        }
                    }
                }
            }
        }
    }
}
