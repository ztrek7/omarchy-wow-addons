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
    readonly property var detailRef: entry ? root.infoRef(entry) : null
    readonly property var info: detailRef ? app.details[detailRef.source + ":" + detailRef.id] || null : null
    readonly property int major: app.game?.major || 0
    // Browse shows addons for the game in use unless "Any game version" is picked.
    property bool anyGame: false
    readonly property var games: app.setup.flavors || []
    readonly property int gameIndex: anyGame ? games.length : Math.max(0, games.findIndex(g => g.key === app.game?.key))
    readonly property string flavour: app.game?.flavour || ""
    readonly property var sourceOrder: ["curseforge", "wowinterface"]
    readonly property var categories: {
        let counts = {}
        app.catalog.forEach(e => { if (e.category) counts[e.category] = (counts[e.category] || 0) + 1 })
        return Object.keys(counts).sort((a, b) => a.localeCompare(b)).map(name => ({name: name, count: counts[name]}))
    }
    readonly property var results: {
        let on = app.sourceOn
        let term = search.text.toLowerCase().trim()
        let category = categoryFilter.currentIndex > 0 ? categories[categoryFilter.currentIndex - 1]?.name : ""
        let days = [0, 31, 183, 365, 730][updatedFilter.currentIndex]
        let since = days ? Date.now() - days * 86400000 : 0
        let forGame = !anyGame && !!flavour
        let hide = hideInstalled.checked
        let found = []
        for (let e of app.catalog) {
            let refs = e.sources.filter(r => on[r.source] === true)
            if (!refs.length) continue
            if (term && (e.name + " " + e.author + " " + e.dirs.join(" ")).toLowerCase().indexOf(term) < 0) continue
            if (category && e.category !== category) continue
            let updated = Math.max(...refs.map(r => r.updated || 0))
            if (since && updated < since) continue
            if (forGame && !refs.some(r => root.fitsRef(r))) continue
            if (hide && root.app.entryState(e) !== "install") continue
            found.push({entry: e, refs: refs, updated: updated, downloads: refs.reduce((sum, r) => sum + (r.downloads || 0), 0)})
        }
        let sort = sortFilter.currentIndex
        return found.sort((a, b) => sort === 1 ? b.updated - a.updated || a.entry.name.localeCompare(b.entry.name)
            : sort === 2 ? a.entry.name.localeCompare(b.entry.name)
            : sort === 3 ? b.entry.name.localeCompare(a.entry.name)
            : b.downloads - a.downloads || a.entry.name.localeCompare(b.entry.name))
    }
    onResultsChanged: grid.positionViewAtBeginning()

    // Whether a site lists the addon for exactly this game. Only the site's
    // own tags count; a 1.13 addon isn't listed for WoW Forever just because it's 1.x.
    function fitsRef(r) { return !!flavour && (r.flavours || []).indexOf(flavour) >= 0 }
    function lineName(line) { return app.setup.gameNames?.[line] || line }
    // What the sites actually say, e.g. "Listed for WoW Classic Era 1.13.2".
    function listedText(refs) {
        if (refs.some(r => root.fitsRef(r))) return "Listed for " + lineName(flavour)
        let lines = []
        refs.forEach(r => (r.flavours || []).forEach(f => { if (lines.indexOf(f) < 0) lines.push(f) }))
        if (!lines.length) return "No game version listed"
        let newest = refs.map(r => (r.gameVersions || [])[0]).find(v => v) || ""
        return "Listed for " + lines.slice(0, 2).map(lineName).join(", ") + (lines.length > 2 ? " +" + (lines.length - 2) + " more" : "")
            + (lines.length === 1 && newest ? " " + newest : "")
    }
    // Browse sources the user has on. Wago only appears as a page link in details.
    function usable(e) { return e.sources.filter(r => app.sourceOn[r.source] === true) }
    // Where Install gets it: a site listing it for this game, most recently updated. The rest are fallbacks.
    function rankedRefs(e) {
        return usable(e).sort((a, b) => root.fitsRef(b) - root.fitsRef(a) || (b.updated || 0) - (a.updated || 0))
    }
    function bestRef(e) { return rankedRefs(e)[0] || null }
    // WoWInterface has screenshots, so its description is preferred.
    function infoRef(e) {
        return ["wowinterface", "curseforge"].map(s => e.sources.find(r => r.source === s)).find(r => r) || null
    }
    // One badge per site, even when a site lists the addon twice.
    function siteList(refs) {
        let seen = []
        refs.forEach(r => { if (seen.indexOf(r.source) < 0) seen.push(r.source) })
        return seen
    }
    function actionText(e) {
        if (app.busy && app.request.action === "install" && e.sources.some(r => r.id === app.request.id)) return "Installing…"
        if (app.busy && app.request.action === "update" && (app.request.ids || []).indexOf(app.installedRowFor(e)) >= 0) return "Updating…"
        return ({installed: "Installed", update: "Update", replace: "Install…", install: "Install"})[app.entryState(e)]
    }
    function act(e, ref) {
        let state = app.entryState(e)
        if (state === "update" && !ref) app.update([app.installedRowFor(e)])
        else if (ref) app.installEntry(e, ref, [])  // The user picked this site.
        else if (state !== "installed") {
            let ranked = rankedRefs(e)
            app.installEntry(e, ranked[0], ranked.slice(1))
        }
    }
    function cfSlug(e) { return (e.sources.find(r => r.source === "curseforge") || {}).id || "" }
    function openDetails(e) {
        entry = e
        let r = infoRef(e)
        if (r) app.loadDetails(r.source, r.id)
        details.open()
    }
    function closeDetails() { details.close() }
    function focusSearch() { search.forceActiveFocus() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            UI.SearchField { id: search; objectName: "browseSearch"; Layout.fillWidth: true; placeholderText: "Search " + root.app.catalog.length.toLocaleString(Qt.locale(), "f", 0) + " addons by name, author, or folder…" }
            UI.Filter { id: sortFilter; objectName: "browseSort"; Layout.preferredWidth: 190; Layout.minimumWidth: 150; model: ["Most downloaded", "Recently updated", "Name A–Z", "Name Z–A"] }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            UI.Filter {
                id: categoryFilter
                objectName: "categoryFilter"
                Layout.fillWidth: true
                Layout.preferredWidth: 190
                Layout.minimumWidth: 130
                model: ["All categories"].concat(root.categories.map(c => c.name + "  (" + c.count + ")"))
            }
            UI.Filter {
                id: gameFilter
                objectName: "gameFilter"
                Layout.fillWidth: true
                Layout.preferredWidth: 300
                Layout.minimumWidth: 200
                model: root.games.map(g => root.app.gameLabel(g)).concat(["Any game version"])
                currentIndex: root.gameIndex
                // Picking another game switches the app to it, so installs go to that game's AddOns folder.
                onActivated: index => {
                    root.anyGame = index >= root.games.length
                    let picked = root.games[index]
                    if (picked && picked.key !== root.app.game?.key) root.app.execute({action: "configure", flavor: picked.key})
                    currentIndex = Qt.binding(() => root.gameIndex)
                }
            }
            UI.Filter { id: updatedFilter; objectName: "updatedFilter"; Layout.fillWidth: true; Layout.preferredWidth: 190; Layout.minimumWidth: 140; model: ["Updated any time", "Updated past month", "Updated past 6 months", "Updated past year", "Updated past 2 years"] }
            UI.CheckOption { id: hideInstalled; objectName: "hideInstalled"; text: "Hide installed" }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 4
            UI.Label { text: "SOURCES"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5; rightPadding: 6 }
            Repeater {
                model: root.sourceOrder
                delegate: UI.CheckOption {
                    id: toggle
                    required property string modelData
                    readonly property var status: root.app.catalogInfo.sources?.[modelData] || null
                    objectName: "source-" + modelData
                    badge: modelData
                    checked: root.app.sourceOn[modelData] === true
                    text: root.app.sourceName(modelData) + (status ? "  " + status.count.toLocaleString(Qt.locale(), "f", 0) : "") + (status?.error ? "  ⚠" : "")
                    onToggled: root.app.setSource(modelData, checked)
                    UI.Tooltip { visible: toggle.hovered && !!toggle.status?.error; text: "Couldn't refresh " + root.app.sourceName(toggle.modelData) + ": " + (toggle.status?.error || "") + " Showing the saved list." }
                }
            }
            Item { Layout.fillWidth: true }
            UI.Label { objectName: "browseCount"; text: root.results.length.toLocaleString(Qt.locale(), "f", 0) + " shown"; color: UI.Theme.muted; font.pixelSize: 11 }
        }
        UI.Label {
            Layout.fillWidth: true
            text: "Addons on both sites show up once. Install gets the newest release listed for your game, from whichever site has it. "
                + "“Listed for” is what the author put on the site. Addons listed for an older game often still work; pick “Any game version” to see them."
                + (root.app.catalogMessage ? "  " + root.app.catalogMessage : "")
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
                readonly property var item: modelData.entry
                readonly property string installState: root.app.entryState(item)
                readonly property string logoSlug: root.cfSlug(item)
                Component.onCompleted: root.app.wantLogo(logoSlug)
                Component.onDestruction: root.app.dropLogo(logoSlug)
                width: grid.cellWidth - 10
                height: grid.cellHeight - 10
                radius: 10
                color: cardMouse.containsMouse ? UI.Theme.hover : UI.Theme.surface
                border.color: card.installState === "installed" || card.installState === "update" ? UI.Theme.accent : UI.Theme.border
                MouseArea { id: cardMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.openDetails(card.item) }
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
                            // CurseForge logos load as cards appear. WoWInterface's thumbnail (a small
                            // screenshot) fills in until then, or when the addon isn't on CurseForge.
                            source: root.visible ? root.app.cfLogos[card.logoSlug] || card.item.thumb || "" : ""
                            sourceSize: Qt.size(168, 168)
                            asynchronous: true
                            fillMode: Image.PreserveAspectCrop
                        }
                        UI.Label { anchors.centerIn: parent; visible: thumb.status !== Image.Ready; text: card.item.name.slice(0, 1).toUpperCase(); font.pixelSize: 34; color: UI.Theme.muted }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 3
                        UI.Label { Layout.fillWidth: true; text: card.item.name; font.weight: Font.DemiBold; elide: Text.ElideRight }
                        UI.Label {
                            Layout.fillWidth: true
                            text: [card.item.author ? "by " + card.item.author : "", card.item.category].filter(x => x).join("  ·  ") || card.item.dirs.slice(0, 3).join(", ")
                            color: UI.Theme.muted; font.pixelSize: 11; elide: Text.ElideRight
                        }
                        UI.Label {
                            Layout.fillWidth: true
                            text: "↓ " + root.app.compact(card.modelData.downloads) + "    Updated " + root.app.fullDate(card.modelData.updated)
                            font.pixelSize: 11; elide: Text.ElideRight
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Repeater {
                                model: root.siteList(card.modelData.refs)
                                delegate: UI.SourceBadge { required property string modelData; source: modelData; label: "On " + root.app.sourceName(modelData) }
                            }
                            UI.Label {
                                Layout.fillWidth: true
                                leftPadding: 3
                                text: root.listedText(card.modelData.refs)
                                color: root.flavour && !card.modelData.refs.some(r => root.fitsRef(r)) ? UI.Theme.warning : UI.Theme.muted
                                font.pixelSize: 10; elide: Text.ElideRight
                            }
                        }
                        Item { Layout.fillHeight: true }
                        RowLayout {
                            spacing: 8
                            UI.ActionButton {
                                implicitHeight: 30
                                text: root.actionText(card.item)
                                primary: card.installState === "install" || card.installState === "update"
                                enabled: !root.app.busy && card.installState !== "installed" && !!root.app.game
                                onClicked: root.act(card.item, null)
                            }
                            UI.ActionButton { implicitHeight: 30; text: "Details"; onClicked: root.openDetails(card.item) }
                        }
                    }
                }
            }
            UI.Label {
                anchors.centerIn: parent
                width: parent.width - 40
                visible: !root.results.length
                text: root.catalogLoading && !root.app.catalog.length ? "Loading the CurseForge and WoWInterface catalogs…"
                    : !root.app.catalog.length ? (root.app.catalogMessage || "The catalog isn't loaded.") + "\nUse Refresh catalog to try again."
                    : !root.sourceOrder.some(s => root.app.sourceOn[s]) ? "Every source is turned off.\nTurn one on above."
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
                    enabled: !!root.entry && !root.app.busy && root.app.entryState(root.entry) !== "installed" && !!root.app.game && !!root.bestRef(root.entry)
                    onClicked: root.act(root.entry, null)
                }
                UI.ActionButton { text: "Close"; onClicked: details.close() }
            }
            UI.Label {
                Layout.fillWidth: true
                text: root.entry ? [root.info?.author || root.entry.author ? "by " + (root.info?.author || root.entry.author) : "", root.entry.category, "Folders: " + root.entry.dirs.join(", ")].filter(x => x).join("  ·  ") : ""
                color: UI.Theme.muted; font.pixelSize: 12; wrapMode: Text.Wrap
            }
            UI.Label { text: "WHERE TO GET IT"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
            Repeater {
                model: root.entry ? root.entry.sources : []
                delegate: RowLayout {
                    id: sourceRow
                    required property var modelData
                    readonly property bool wago: modelData.source === "wago"
                    readonly property bool on: wago || root.app.sourceOn[modelData.source] === true
                    Layout.fillWidth: true
                    spacing: 10
                    opacity: on ? 1 : 0.5
                    RowLayout {
                        Layout.preferredWidth: 124
                        spacing: 7
                        UI.SourceBadge { visible: root.app.hasLogo(sourceRow.modelData.source); source: root.app.hasLogo(sourceRow.modelData.source) ? sourceRow.modelData.source : ""; size: 18 }
                        UI.Label { text: root.app.sourceName(sourceRow.modelData.source); font.weight: Font.DemiBold; font.pixelSize: 12 }
                    }
                    UI.Label {
                        Layout.fillWidth: true
                        text: sourceRow.wago ? "Also on Wago. This app can't download from Wago, but you can get it there and add the .zip."
                            : ["Updated " + root.app.fullDate(sourceRow.modelData.updated), sourceRow.modelData.downloads ? "↓ " + root.app.compact(sourceRow.modelData.downloads) : "",
                               root.listedText([sourceRow.modelData]), sourceRow.on ? "" : "source turned off"].filter(x => x).join("  ·  ")
                        color: UI.Theme.muted; font.pixelSize: 11; wrapMode: Text.Wrap
                    }
                    UI.ActionButton {
                        visible: !sourceRow.wago
                        implicitHeight: 30
                        text: "Install from here"
                        enabled: sourceRow.on && !root.app.busy && !!root.app.game
                        onClicked: root.act(root.entry, sourceRow.modelData)
                    }
                    UI.ActionButton { implicitHeight: 30; text: "Page ↗"; onClicked: Qt.openUrlExternally(sourceRow.modelData.url) }
                }
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
                        text: root.app.detailsError && root.detailRef && root.app.detailsId === root.detailRef.source + ":" + root.detailRef.id ? root.app.detailsError : "Loading the description…"
                        color: root.app.detailsError ? UI.Theme.danger : UI.Theme.muted
                        wrapMode: Text.Wrap
                    }
                    UI.Label { visible: !!root.info; text: "ABOUT · FROM " + root.app.sourceName(root.detailRef?.source || "").toUpperCase(); color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                    UI.Label { objectName: "detailsDescription"; Layout.fillWidth: true; text: root.info?.description || ""; wrapMode: Text.Wrap; font.pixelSize: 13; lineHeight: 1.35 }
                    UI.Label { visible: !!root.info?.changelog; text: "CHANGES"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                    UI.Label { visible: !!root.info?.changelog; Layout.fillWidth: true; text: root.info?.changelog || ""; wrapMode: Text.Wrap; font.pixelSize: 11; color: UI.Theme.muted; font.family: "Adwaita Mono" }
                }
            }
        }
    }
}
