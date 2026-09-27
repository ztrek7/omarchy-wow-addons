pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "ui" as UI

Item {
    id: root
    required property var app
    property bool catalogLoading: false
    property bool detailsLoading: false
    property var entry: null
    readonly property bool detailsOpen: details.opened
    readonly property var info: entry ? app.details[entry.id] || null : null
    readonly property int major: app.game?.major || 0
    readonly property var categories: {
        let counts = {}
        app.catalog.forEach(e => counts[e.category] = (counts[e.category] || 0) + 1)
        return Object.keys(counts).sort((a, b) => a.localeCompare(b)).map(name => ({name: name, count: counts[name]}))
    }
    readonly property var results: {
        let term = search.text.toLowerCase().trim()
        let category = categoryFilter.currentIndex > 0 ? categories[categoryFilter.currentIndex - 1]?.name : ""
        let days = [0, 31, 183, 365, 730][updatedFilter.currentIndex]
        let since = days ? Date.now() - days * 86400000 : 0
        let forGame = gameFilter.currentIndex === 0 && major > 0
        let hide = hideInstalled.checked
        let found = app.catalog.filter(e => (!term || (e.name + " " + e.author + " " + e.dirs.join(" ")).toLowerCase().indexOf(term) >= 0)
            && (!category || e.category === category)
            && (!since || e.updated >= since)
            && (!forGame || root.fits(e))
            && (!hide || root.app.entryState(e) === "install"))
        let sort = sortFilter.currentIndex
        let key = [e => e.downloads, e => e.monthly, e => e.favorites, e => e.updated][sort]
        return found.sort(key ? (a, b) => key(b) - key(a) || a.name.localeCompare(b.name) : (a, b) => a.name.localeCompare(b.name))
    }
    onResultsChanged: grid.positionViewAtBeginning()
    function fits(e) { return e.gameVersions.some(v => parseInt(v) === major) }
    function versionsText(e) {
        let ours = e.gameVersions.filter(v => parseInt(v) === major)
        let shown = (ours.length ? ours : e.gameVersions).slice(0, 3)
        return shown.length ? "for " + shown.join(", ") : "no game version listed"
    }
    function actionText(e) {
        if (app.busy && (app.request.id === e.id || (app.request.ids || []).indexOf("wowi:" + e.id) >= 0)) return "Installing…"
        return ({installed: "Installed", update: "Update", replace: "Install…", install: "Install"})[app.entryState(e)]
    }
    function act(e) {
        let state = app.entryState(e)
        if (state === "update") app.execute({action: "update", ids: ["wowi:" + e.id]})
        else if (state !== "installed") app.installEntry(e)
    }
    function openDetails(e) { entry = e; app.loadDetails(e.id); details.open() }
    function closeDetails() { details.close() }
    function focusSearch() { search.forceActiveFocus() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            UI.SearchField { id: search; objectName: "browseSearch"; Layout.fillWidth: true; placeholderText: "Search " + root.app.catalog.length.toLocaleString(Qt.locale(), "f", 0) + " addons by name, author, or folder…" }
            UI.Filter { id: sortFilter; objectName: "browseSort"; Layout.preferredWidth: 190; Layout.minimumWidth: 150; model: ["Most downloaded", "Popular this month", "Most favorited", "Recently updated", "Name A–Z"] }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            UI.Filter {
                id: categoryFilter
                objectName: "categoryFilter"
                Layout.fillWidth: true
                Layout.preferredWidth: 250
                Layout.minimumWidth: 140
                model: ["All categories"].concat(root.categories.map(c => c.name + "  (" + c.count + ")"))
            }
            UI.Filter { id: gameFilter; objectName: "gameFilter"; Layout.fillWidth: true; Layout.preferredWidth: 210; Layout.minimumWidth: 140; model: [root.major ? "For my game (" + root.major + ".x)" : "For my game", "Any game version"] }
            UI.Filter { id: updatedFilter; objectName: "updatedFilter"; Layout.fillWidth: true; Layout.preferredWidth: 190; Layout.minimumWidth: 140; model: ["Updated any time", "Updated past month", "Updated past 6 months", "Updated past year", "Updated past 2 years"] }
            UI.CheckOption { id: hideInstalled; objectName: "hideInstalled"; text: "Hide installed" }
        }
        UI.Label {
            Layout.fillWidth: true
            objectName: "browseCount"
            text: root.results.length.toLocaleString(Qt.locale(), "f", 0) + " shown  ·  From WoWInterface" + (root.app.catalogInfo.fetchedAt ? " · catalog from " + new Date(root.app.catalogInfo.fetchedAt * 1000).toLocaleString(Qt.locale(), "MMM d, h:mm AP") : "")
                + (root.app.catalogMessage ? " · " + root.app.catalogMessage : "")
                + ". Game versions are what authors list; newer clients often run older addons."
            color: UI.Theme.muted; font.pixelSize: 10; wrapMode: Text.Wrap
        }
        GridView {
            id: grid
            objectName: "browseGrid"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            cellWidth: Math.max(1, width / Math.max(1, Math.floor(width / 350)))
            cellHeight: 156
            model: root.results
            cacheBuffer: 300
            ScrollBar.vertical: UI.ScrollBar {}
            delegate: Rectangle {
                id: card
                required property var modelData
                readonly property string installState: root.app.entryState(modelData)
                width: grid.cellWidth - 10
                height: grid.cellHeight - 10
                radius: 10
                color: cardMouse.containsMouse ? UI.Theme.hover : UI.Theme.surface
                border.color: card.installState === "installed" || card.installState === "update" ? UI.Theme.accent : UI.Theme.border
                MouseArea { id: cardMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.openDetails(card.modelData) }
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12
                    Rectangle {
                        Layout.alignment: Qt.AlignTop
                        implicitWidth: 84; implicitHeight: 84; radius: 8
                        color: UI.Theme.hover
                        clip: true
                        Image {
                            id: thumb
                            anchors.fill: parent
                            source: root.visible ? card.modelData.thumb : ""
                            sourceSize: Qt.size(168, 168)
                            asynchronous: true
                            fillMode: Image.PreserveAspectCrop
                        }
                        UI.Label { anchors.centerIn: parent; visible: thumb.status !== Image.Ready; text: card.modelData.name.slice(0, 1).toUpperCase(); font.pixelSize: 34; color: UI.Theme.muted }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 3
                        UI.Label { Layout.fillWidth: true; text: card.modelData.name; font.weight: Font.DemiBold; elide: Text.ElideRight }
                        UI.Label { Layout.fillWidth: true; text: "by " + card.modelData.author + "  ·  " + card.modelData.category; color: UI.Theme.muted; font.pixelSize: 11; elide: Text.ElideRight }
                        UI.Label {
                            Layout.fillWidth: true
                            text: "↓ " + root.app.compact(card.modelData.downloads) + "    " + root.app.compact(card.modelData.monthly) + "/mo    ♥ " + root.app.compact(card.modelData.favorites)
                            font.pixelSize: 11; elide: Text.ElideRight
                        }
                        UI.Label {
                            Layout.fillWidth: true
                            text: "Updated " + root.app.monthYear(card.modelData.updated) + "  ·  " + root.versionsText(card.modelData)
                            color: root.major && !root.fits(card.modelData) ? UI.Theme.warning : UI.Theme.muted
                            font.pixelSize: 10; elide: Text.ElideRight
                        }
                        Item { Layout.fillHeight: true }
                        RowLayout {
                            spacing: 8
                            UI.ActionButton {
                                implicitHeight: 30
                                text: root.actionText(card.modelData)
                                primary: card.installState === "install" || card.installState === "update"
                                enabled: !root.app.busy && card.installState !== "installed" && !!root.app.game
                                onClicked: root.act(card.modelData)
                            }
                            UI.ActionButton { implicitHeight: 30; text: "Details"; onClicked: root.openDetails(card.modelData) }
                        }
                    }
                }
            }
            UI.Label {
                anchors.centerIn: parent
                width: parent.width - 40
                visible: !root.results.length
                text: root.catalogLoading && !root.app.catalog.length ? "Loading the WoWInterface catalog…"
                    : !root.app.catalog.length ? (root.app.catalogMessage || "The catalog isn't loaded.") + "\nUse Refresh catalog to try again."
                    : "No addons match.\nTry “Any game version”, a longer time range, or another category."
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                lineHeight: 1.5
                color: UI.Theme.muted
            }
        }
    }

    Popup {
        id: details
        objectName: "browseDetails"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 880)
        height: Math.min(parent.height - 48, 760)
        modal: true
        padding: 22
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: UI.Theme.scrim }
        background: Rectangle { color: UI.Theme.background; border.color: UI.Theme.border; radius: 14 }
        contentItem: ColumnLayout {
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                UI.Label { Layout.fillWidth: true; text: root.entry?.name || ""; font.pixelSize: 23; font.weight: Font.DemiBold; elide: Text.ElideRight }
                UI.ActionButton {
                    text: root.entry ? root.actionText(root.entry) : ""
                    primary: !!root.entry && ["install", "update"].indexOf(root.app.entryState(root.entry)) >= 0
                    enabled: !!root.entry && !root.app.busy && root.app.entryState(root.entry) !== "installed" && !!root.app.game
                    onClicked: root.act(root.entry)
                }
                UI.ActionButton { text: "WoWInterface ↗"; onClicked: Qt.openUrlExternally(root.entry.url) }
                UI.ActionButton { text: "Close"; onClicked: details.close() }
            }
            UI.Label {
                Layout.fillWidth: true
                text: root.entry ? "by " + root.entry.author + "  ·  " + root.entry.category + "  ·  version " + root.entry.version + "  ·  updated " + new Date(root.entry.updated).toLocaleDateString()
                    + "\n↓ " + root.entry.downloads.toLocaleString(Qt.locale(), "f", 0) + " downloads  ·  " + root.entry.monthly.toLocaleString(Qt.locale(), "f", 0) + " this month  ·  ♥ " + root.entry.favorites.toLocaleString(Qt.locale(), "f", 0)
                    + "\nGame versions: " + (root.entry.gameVersions.join(", ") || "none listed") + "  ·  Folders: " + root.entry.dirs.join(", ") : ""
                color: UI.Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap; lineHeight: 1.4
            }
            ScrollView {
                id: detailScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ScrollBar.vertical: UI.ScrollBar { parent: detailScroll; x: detailScroll.width - width; height: detailScroll.height }
                ColumnLayout {
                    width: parent.width
                    spacing: 14
                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: visible ? 250 : 0
                        visible: (root.info?.images.length || 0) > 0
                        orientation: ListView.Horizontal
                        spacing: 10
                        clip: true
                        model: details.opened ? root.info?.images || [] : []
                        delegate: Rectangle {
                            id: shot
                            required property string modelData
                            width: 400; height: 250; radius: 8
                            color: UI.Theme.surface
                            clip: true
                            Image { id: shotImage; anchors.fill: parent; source: shot.modelData; sourceSize: Qt.size(800, 500); asynchronous: true; fillMode: Image.PreserveAspectFit }
                            UI.Label { anchors.centerIn: parent; visible: shotImage.status !== Image.Ready; text: shotImage.status === Image.Error ? "Preview unavailable" : "Loading…"; color: UI.Theme.muted }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: Qt.openUrlExternally(shot.modelData) }
                        }
                    }
                    UI.Label {
                        Layout.fillWidth: true
                        visible: !root.info
                        text: root.app.detailsError && root.app.detailsId === root.entry?.id ? root.app.detailsError : "Loading the description…"
                        color: root.app.detailsError ? UI.Theme.danger : UI.Theme.muted
                        wrapMode: Text.Wrap
                    }
                    UI.Label { objectName: "detailsDescription"; Layout.fillWidth: true; text: root.info?.description || ""; wrapMode: Text.Wrap; font.pixelSize: 13; lineHeight: 1.35 }
                    UI.Label { visible: !!root.info?.changelog; text: "CHANGES"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                    UI.Label { visible: !!root.info?.changelog; Layout.fillWidth: true; text: root.info?.changelog || ""; wrapMode: Text.Wrap; font.pixelSize: 11; color: UI.Theme.muted; font.family: "Adwaita Mono" }
                }
            }
        }
    }
}
