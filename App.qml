import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "ui" as UI

Scope {
    id: app
    property alias windowItem: surface
    property alias installedView: installedView
    property alias browseView: browseView
    property bool demo: Quickshell.env("WOW_ADDONS_DEMO") === "1"

    // Installed state, from backend.py list.
    property var setup: ({roots: [], flavors: [], flavor: null})
    readonly property var game: setup.flavor || null
    property var addons: []
    property var checks: ({})
    property bool gameRunning: false
    property var downloads: []
    property string lastChecked: ""

    // WoWInterface catalog, loaded from the backend's cache file.
    property var catalog: []
    property var catalogInfo: ({})
    property string catalogMessage: ""
    property var details: ({})
    // CurseForge logos by project slug. The catalog has none, so they're fetched for cards on screen.
    property var cfLogos: ({})
    property var logoQueue: []
    property var logoTried: ({})
    property string detailsId: ""
    property string detailsError: ""

    property string page: "installed"
    property var events: []
    property string status: "Looking for World of Warcraft…"
    property bool failed: false
    property var request: ({})
    property string output: ""
    property string errors: ""
    property string dialogAction: ""
    property var dialogTarget: ({})
    readonly property bool busy: worker.running

    readonly property var updateIds: addons.filter(a => checks[a.id]?.state === "available").map(a => a.id)
    readonly property int enabledCount: addons.filter(a => a.state !== "disabled").length
    readonly property int outOfDateCount: addons.filter(a => a.outOfDate).length
    // Browse sources the user has turned on; saved to the config file.
    property var sourceOn: ({curseforge: true, wowinterface: true})
    // "source:id" -> installed addon id, from install records and TOC-declared sources.
    readonly property var installedKeys: {
        let keys = {}
        let prefixes = {wowi: "wowinterface"}
        addons.forEach(a => {
            let [prefix, ...rest] = a.id.split(":")
            keys[(prefixes[prefix] || prefix) + ":" + rest.join(":").toLowerCase()] = a.id
            a.links.forEach(l => keys[l.source + ":" + String(l.id).toLowerCase()] = a.id)
        })
        return keys
    }
    // Folder name -> addon id, so the catalog can tell what's already on disk.
    readonly property var folderOwners: {
        let owners = {}
        addons.forEach(a => a.dirs.forEach(d => owners[d.name] = a.id))
        return owners
    }

    function helper() { return decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace(/^file:\/\//, "")) }
    function gameLabel(g) {
        g = g === undefined ? game : g
        return g ? g.name + (g.version ? " " + g.version : "") : "No game found"
    }
    function compact(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M"
        if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "K"
        return String(n)
    }
    function versionText(v) { return !v ? "" : /^\d/.test(v) ? "v" + v : v }
    function fullDate(value) { return value ? new Date(value).toLocaleDateString(Qt.locale(), "MMMM d, yyyy") : "unknown" }
    // Sites with a logo badge; anything else is described in words.
    function hasLogo(source) { return source === "curseforge" || source === "wowinterface" }
    function sourceName(source) {
        return ({wowinterface: "WoWInterface", curseforge: "CurseForge", wago: "Wago", file: "Zip file", manual: "Manual install"})[source] || source
    }

    function log(message, error) {
        status = message
        failed = !!error
        events = [{time: new Date().toLocaleTimeString(), message: message, error: !!error}].concat(events).slice(0, 100)
    }
    function execute(data) {
        if (busy) return
        if (demo) { log("Preview mode: changes are disabled.", false); return }
        request = data
        output = ""
        errors = ""
        // A refresh after a change keeps that change's message in the status line.
        if (!followUp) {
            failed = false
            status = ({list: "Reading your AddOns folder…", install: "Downloading and installing…", requirements: "Installing what it needs…",
                       update: "Installing updates…", remove: "Moving to the trash…", enable: "Enabling…", disable: "Disabling…", configure: "Saving settings…"})[data.action] || "Working…"
        }
        worker.command = ["python3", helper(), JSON.stringify(data)]
        worker.running = true
    }
    function refresh() { execute({action: "list"}) }
    // Checks only read, so they run beside other work. force skips the catalog
    // cache; automatic checks reuse a catalog up to an hour old.
    function checkUpdates(force) {
        if (demo || checkWorker.running || !game) return
        checkWorker.output = ""
        checkWorker.auto = !force
        if (force) status = "Checking for updates…"
        checkWorker.command = ["python3", helper(), JSON.stringify({action: "check", force: !!force})]
        checkWorker.running = true
    }
    function update(ids) {
        let preferred = {}
        ids.forEach(id => { if (checks[id]?.source) preferred[id] = checks[id].source })
        execute({action: "update", ids: ids, sources: preferred})
    }
    function toggle(addon) { execute({action: addon.state === "enabled" ? "disable" : "enable", id: addon.id}) }
    function installedRowFor(entry) {
        for (let r of entry.sources) {
            let row = installedKeys[r.source + ":" + String(r.id).toLowerCase()] || (r.numericId && installedKeys[r.source + ":" + r.numericId])
            if (row) return row
        }
        return ""
    }
    function entryState(entry) {
        let row = installedRowFor(entry)
        if (row) return checks[row]?.state === "available" ? "update" : "installed"
        return entry.dirs.some(d => folderOwners[d]) ? "replace" : "install"
    }
    // alternatives: other sites to try, in order, if the first one can't deliver.
    function installEntry(entry, ref, alternatives) {
        if (!ref) return
        let row = installedRowFor(entry)
        let clashes = entry.dirs.filter(d => folderOwners[d] && folderOwners[d] !== row)
        let request = {action: "install", source: ref.source, id: ref.id, alternatives: (alternatives || []).map(r => ({source: r.source, id: r.id}))}
        if (clashes.length) confirm("replace", {name: entry.name, clashes: clashes, request: request})
        else execute(request)
    }
    function wantLogo(slug) {
        if (demo || !slug || cfLogos[slug] || logoTried[slug] || logoQueue.indexOf(slug) >= 0) return
        logoQueue = logoQueue.concat([slug])
        logoTimer.restart()
    }
    // A card scrolled away before its turn; don't fetch its logo.
    function dropLogo(slug) {
        if (logoQueue.indexOf(slug) >= 0) logoQueue = logoQueue.filter(s => s !== slug)
    }
    function fetchLogos(everything) {
        if (logoWorker.running || (!everything && !logoQueue.length)) return
        // Newest requests first: those are the cards on screen now.
        let batch = everything ? [] : logoQueue.slice(-12).reverse()
        logoQueue = logoQueue.filter(s => batch.indexOf(s) < 0)
        let tried = Object.assign({}, logoTried)
        batch.forEach(s => tried[s] = true)
        logoTried = tried
        logoWorker.output = ""
        logoWorker.command = ["python3", helper(), JSON.stringify({action: "logos", slugs: batch, all: !!everything})]
        logoWorker.running = true
    }
    function setSource(name, on) {
        let next = Object.assign({}, sourceOn)
        next[name] = on
        sourceOn = next
        if (demo) return
        configWorker.command = ["python3", helper(), JSON.stringify({action: "configure", sources: next})]
        configWorker.running = true
    }
    function loadCatalog(force) {
        if (demo || catalogWorker.running) return
        catalogMessage = force ? "Downloading the addon catalog…" : "Loading the addon catalog…"
        catalogWorker.output = ""
        catalogWorker.command = ["python3", helper(), JSON.stringify({action: "catalog", force: !!force})]
        catalogWorker.running = true
    }
    function loadDetails(source, id) {
        detailsId = source + ":" + id
        detailsError = ""
        if (demo || details[detailsId] || detailsWorker.running) return
        detailsWorker.output = ""
        detailsWorker.command = ["python3", helper(), JSON.stringify({action: "details", source: source, id: id})]
        detailsWorker.running = true
    }
    function confirm(action, target) {
        dialogAction = action
        dialogTarget = target || {}
        addLocation.text = ""
        dialog.open()
        if (action === "add") addLocation.forceActiveFocus()
    }

    function finish(code) {
        let data
        try { data = JSON.parse(output) }
        catch (e) { log(errors.trim() || "Something went wrong (exit " + code + ").", true); return }
        if (!data.ok) { log(data.error || "The operation failed.", true); return }
        let action = request.action
        if (action === "list") {
            setup = data.setup
            addons = data.addons
            gameRunning = data.gameRunning
            if (data.setup.sources) sourceOn = data.setup.sources
            downloads = data.downloads || []
            let kept = {}
            addons.forEach(a => { if (checks[a.id]) kept[a.id] = checks[a.id] })
            checks = kept
            if (!game) log("No World of Warcraft install found. Choose its folder in Settings.", true)
            else if (!followUp) status = addons.length + " addons in " + gameLabel() + " · " + enabledCount + " enabled"
            followUp = false
            if (game && !autoChecked) {
                autoChecked = true
                Qt.callLater(() => checkUpdates(false))
            }
            return
        }
        if (data.results) {
            data.results.forEach(r => log(r.message, !r.ok))
            let failures = data.results.filter(r => !r.ok).length
            log((data.results.length - failures) + " updated · " + failures + " failed" + (gameRunning ? " · /reload in game to apply" : ""), failures > 0)
            let next = Object.assign({}, checks)
            data.results.forEach(r => { if (r.ok) delete next[r.id] })
            checks = next
        } else {
            if (action === "install" && request.id) {
                // The installed copy is now current; drop its stale update check.
                let next = Object.assign({}, checks)
                let id = ":" + String(request.id).toLowerCase()
                Object.keys(next).filter(k => k.toLowerCase().endsWith(id)).forEach(k => delete next[k])
                checks = next
            }
            log(data.message + (gameRunning && action !== "configure" ? " Restart the game or /reload to apply." : ""), false)
        }
        // Show the folder as it is now, keeping the message above in the status line.
        followUp = true
        Qt.callLater(refresh)
    }
    property bool followUp: false
    function finishCheck(data, auto) {
        if (!data.ok) { log("Couldn't check for updates. " + (data.error || ""), !auto); return }
        checks = data.checks
        lastChecked = new Date().toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
        let checked = Object.keys(data.checks)
        let failures = checked.filter(k => data.checks[k].state === "error")
        failures.forEach(k => log((addons.find(a => a.id === k)?.name || k) + " couldn't be checked. " + data.checks[k].message, true))
        let count = updateIds.length
        let summary = !checked.length ? "No addons with an update source to check."
            : count ? count + (count === 1 ? " update available" : " updates available")
            : "All " + checked.length + " checked addons are up to date"
        // Automatic checks don't turn the status red; failures stay listed in Activity.
        log(summary + (failures.length ? " · " + failures.length + " couldn't be checked (see Activity)" : ""), failures.length > 0 && !auto)
    }
    property bool autoChecked: false
    readonly property bool checking: checkWorker.running

    Component.onCompleted: {
        Quickshell.watchFiles = false
        if (demo) demoFile.path = Qt.resolvedUrl("tests/demo.json")
        else {
            refresh()
            loadCatalog(false)
            fetchLogos(true)  // Logos remembered from earlier sessions.
        }
    }
    FileView {
        id: demoFile
        onLoaded: {
            let data = JSON.parse(text())
            app.setup = data.setup
            app.addons = data.addons
            app.checks = data.checks
            app.catalog = data.catalog
            app.details = data.details
            app.catalogInfo = data.catalogInfo
            app.sourceOn = data.setup.sources
            app.downloads = data.downloads
            app.status = "Preview mode · example data · changes disabled"
        }
    }
    FileView {
        id: catalogFile
        onLoaded: {
            try {
                app.catalog = JSON.parse(text()).entries
                app.catalogMessage = app.catalogInfo.message || ""
            } catch (e) {
                app.catalogMessage = "The saved catalog could not be read. Use Refresh catalog."
            }
        }
        onLoadFailed: app.catalogMessage = "The saved catalog could not be opened. Use Refresh catalog."
    }
    // Keep checking while the app stays open.
    Timer {
        interval: 6 * 3600 * 1000
        repeat: true
        running: !app.demo && !!app.game
        onTriggered: app.checkUpdates(false)
    }
    Process {
        id: checkWorker
        property string output: ""
        property bool auto: false
        stdout: SplitParser { onRead: data => checkWorker.output += data + "\n" }
        onExited: {
            let data
            try { data = JSON.parse(output) } catch (e) { data = {ok: false, error: "The update helper failed."} }
            app.finishCheck(data, auto)
        }
    }
    Process { id: configWorker }
    Timer { id: logoTimer; interval: 250; onTriggered: app.fetchLogos(false) }
    Process {
        id: logoWorker
        property string output: ""
        stdout: SplitParser { onRead: data => logoWorker.output += data + "\n" }
        onExited: {
            try {
                let data = JSON.parse(output)
                if (data.ok) app.cfLogos = Object.assign({}, app.cfLogos, data.logos)
            } catch (e) {}
            if (app.logoQueue.length) logoTimer.restart()
        }
    }
    Process {
        id: worker
        stdout: SplitParser { onRead: data => app.output += data + "\n" }
        stderr: SplitParser { onRead: data => app.errors += data + "\n" }
        onExited: exitCode => app.finish(exitCode)
    }
    Process {
        id: catalogWorker
        property string output: ""
        stdout: SplitParser { onRead: data => catalogWorker.output += data + "\n" }
        onExited: {
            let data
            try { data = JSON.parse(output) } catch (e) { data = {ok: false, error: "The catalog helper failed."} }
            if (!data.ok) { app.catalogMessage = data.error; return }
            app.catalogInfo = data
            if (catalogFile.path === data.path) catalogFile.reload()
            else catalogFile.path = data.path
        }
    }
    Process {
        id: detailsWorker
        property string output: ""
        stdout: SplitParser { onRead: data => detailsWorker.output += data + "\n" }
        onExited: {
            let data
            try { data = JSON.parse(output) } catch (e) { data = {ok: false, error: "The details helper failed."} }
            if (!data.ok) { app.detailsError = data.error; return }
            let next = Object.assign({}, app.details)
            next[data.details.source + ":" + data.details.id] = data.details
            app.details = next
            // The user may have opened another addon while this one loaded.
            if (app.detailsId && !app.details[app.detailsId]) {
                let [source, ...rest] = app.detailsId.split(":")
                app.loadDetails(source, rest.join(":"))
            }
        }
    }

    FloatingWindow {
        id: window
        title: "WoW Addons"
        visible: true
        implicitWidth: 1200
        implicitHeight: 800
        minimumSize: Qt.size(960, 640)
        color: UI.Theme.background
        onVisibleChanged: {
            if (!visible) {
                if (app.busy) { visible = true; app.status = "Still working. Close the window when this finishes." }
                else Qt.quit()
            }
        }

        Shortcut { sequence: "Ctrl+F"; onActivated: app.page === "browse" ? browseView.focusSearch() : installedView.focusSearch() }
        Shortcut { sequence: "Ctrl+R"; onActivated: app.page === "browse" ? app.loadCatalog(true) : app.refresh() }
        Shortcut { sequence: "Ctrl+N"; onActivated: app.confirm("add", null) }
        Shortcut { sequence: "Ctrl+1"; onActivated: app.page = "installed" }
        Shortcut { sequence: "Ctrl+2"; onActivated: app.page = "browse" }
        Shortcut {
            sequence: "Escape"
            onActivated: {
                if (browseView.detailsOpen) browseView.closeDetails()
                else if (dialog.opened) dialog.close()
                else if (!app.busy) Qt.quit()
            }
        }

        Rectangle {
            id: surface
            anchors.fill: parent
            color: window.color
            RowLayout {
                anchors.fill: parent
                spacing: 0
                ColumnLayout {
                    Layout.preferredWidth: 200
                    Layout.maximumWidth: 200
                    Layout.fillHeight: true
                    Layout.margins: 18
                    spacing: 9
                    Rectangle {
                        Layout.topMargin: 12
                        implicitWidth: 43; implicitHeight: 43; radius: 13
                        color: UI.Theme.accent
                        UI.Label { anchors.centerIn: parent; text: "󰓥"; font.family: "JetBrainsMono Nerd Font"; font.pixelSize: 24; color: UI.Theme.accentText }
                    }
                    UI.Label { text: "WOW\nADDONS"; font.pixelSize: 20; font.weight: Font.Bold; font.letterSpacing: 1.8; lineHeight: 1.12; Layout.topMargin: 8 }
                    Item { Layout.preferredHeight: 24 }
                    Repeater {
                        model: [{key: "installed", name: "▦   Installed" + (app.updateIds.length ? "   ·  " + app.updateIds.length + " ↑" : "")}, {key: "browse", name: "◈   Browse"}, {key: "activity", name: "≡   Activity"}, {key: "settings", name: "⚙   Settings"}]
                        delegate: AbstractButton {
                            id: nav
                            required property var modelData
                            objectName: "nav-" + modelData.key
                            Layout.fillWidth: true
                            implicitHeight: 42
                            onClicked: app.page = modelData.key
                            contentItem: UI.Label { text: nav.modelData.name; leftPadding: 12; verticalAlignment: Text.AlignVCenter; font.pixelSize: 13; color: app.page === nav.modelData.key ? UI.Theme.accent : UI.Theme.muted }
                            background: Rectangle { radius: 8; color: app.page === nav.modelData.key ? UI.Theme.selected : nav.hovered ? UI.Theme.hover : "transparent"; border.color: nav.activeFocus ? UI.Theme.accent : "transparent" }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: gameCard.implicitHeight + 24
                        radius: 10
                        color: UI.Theme.surface
                        border.color: UI.Theme.border
                        ColumnLayout {
                            id: gameCard
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 3
                            UI.Label { text: "GAME"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                            UI.Label { Layout.fillWidth: true; text: app.game ? app.game.name : "Not found"; font.weight: Font.DemiBold; font.pixelSize: 13; elide: Text.ElideRight }
                            UI.Label { Layout.fillWidth: true; visible: !!app.game; text: app.game ? "Version " + (app.game.version || "unknown") : ""; color: UI.Theme.muted; font.pixelSize: 11 }
                            UI.Label { Layout.fillWidth: true; visible: app.gameRunning; text: "● Running"; color: UI.Theme.accent; font.pixelSize: 11 }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: app.page = "settings" }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 28
                    spacing: 16
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        UI.Label { text: ({installed: "Installed", browse: "Browse", activity: "Activity", settings: "Settings"})[app.page]; font.pixelSize: 28; font.weight: Font.DemiBold }
                        Item { Layout.fillWidth: true }
                        UI.ActionButton { objectName: "checkButton"; visible: app.page === "installed"; text: checkWorker.running ? "Checking…" : "↻  Check updates"; enabled: !checkWorker.running && !!app.game; onClicked: app.checkUpdates(true) }
                        UI.ActionButton {
                            objectName: "updateAll"
                            visible: app.page === "installed" && app.updateIds.length > 0
                            text: "Update all (" + app.updateIds.length + ")"
                            enabled: !app.busy
                            onClicked: app.confirm("updateAll", null)
                        }
                        UI.ActionButton { visible: app.page === "browse"; text: catalogWorker.running ? "Loading…" : "↻  Refresh catalog"; enabled: !catalogWorker.running && !app.demo; onClicked: app.loadCatalog(true) }
                        UI.ActionButton { objectName: "addButton"; text: "+  Add addon"; primary: true; enabled: !app.busy && !!app.game; onClicked: app.confirm("add", null) }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: UI.Theme.border }
                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: ["installed", "browse", "activity", "settings"].indexOf(app.page)
                        InstalledView { id: installedView; app: app }
                        BrowseView { id: browseView; app: app; catalogLoading: catalogWorker.running; detailsLoading: detailsWorker.running }
                        ListView {
                            clip: true
                            spacing: 10
                            model: app.events
                            ScrollBar.vertical: UI.ScrollBar {}
                            delegate: Rectangle {
                                id: eventRow
                                required property var modelData
                                width: ListView.view.width - 12
                                height: eventColumn.implicitHeight + 26
                                radius: 10
                                color: UI.Theme.surface
                                ColumnLayout {
                                    id: eventColumn
                                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 13
                                    UI.Label { text: eventRow.modelData.time; color: UI.Theme.muted; font.pixelSize: 10 }
                                    UI.Label { Layout.fillWidth: true; text: eventRow.modelData.message; color: eventRow.modelData.error ? UI.Theme.danger : UI.Theme.foreground; wrapMode: Text.Wrap; font.pixelSize: 12 }
                                }
                            }
                            UI.Label { anchors.centerIn: parent; visible: app.events.length === 0; text: "Installs, updates, and changes will appear here."; color: UI.Theme.muted }
                        }
                        SettingsView { app: app }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Rectangle { implicitWidth: 6; implicitHeight: 6; radius: 3; color: app.failed ? UI.Theme.danger : app.busy ? UI.Theme.warning : UI.Theme.accent }
                        UI.Label {
                            Layout.fillWidth: true
                            text: app.status.replace(/\n/g, " · ")
                            elide: Text.ElideRight; font.pixelSize: 11
                            color: app.failed ? UI.Theme.danger : UI.Theme.muted
                            UI.Tooltip { visible: statusHover.hovered && parent.truncated; text: app.status }
                            HoverHandler { id: statusHover }
                        }
                        UI.Pill { visible: app.gameRunning; text: "Game running · /reload after changes"; ink: UI.Theme.warning }
                        UI.ActionButton { text: "Refresh"; enabled: !app.busy; implicitHeight: 30; onClicked: app.refresh() }
                    }
                }
            }
        }

        Popup {
            id: dialog
            objectName: "dialog"
            anchors.centerIn: parent
            width: 540
            padding: 26
            modal: true
            focus: true
            closePolicy: Popup.CloseOnEscape
            background: Rectangle { radius: 16; color: UI.Theme.surface; border.color: UI.Theme.accent }
            Overlay.modal: Rectangle { color: UI.Theme.scrim }
            contentItem: ColumnLayout {
                spacing: 16
                UI.Label {
                    Layout.fillWidth: true
                    text: app.dialogAction === "add" ? "Add an addon"
                        : app.dialogAction === "remove" ? "Remove " + app.dialogTarget.name + "?"
                        : app.dialogAction === "replace" ? "Replace existing folders?"
                        : "Install " + app.updateIds.length + " update" + (app.updateIds.length === 1 ? "?" : "s?")
                    font.pixelSize: 24; font.weight: Font.DemiBold; wrapMode: Text.WordWrap
                }
                UI.Label {
                    Layout.fillWidth: true
                    text: app.dialogAction === "add" ? "Paste an addon's CurseForge or WoWInterface page, or the path of a .zip you downloaded. The right file is picked for " + app.gameLabel() + "."
                        : app.dialogAction === "remove" ? "Its " + (app.dialogTarget.dirs?.length || 0) + " folder" + (app.dialogTarget.dirs?.length === 1 ? "" : "s") + " move to the trash, so you can restore them. Settings the addon saved in WTF are kept."
                        : app.dialogAction === "replace" ? (app.dialogTarget.name || "This addon") + " installs folders you already have: " + (app.dialogTarget.clashes || []).join(", ") + ". The current copies move to the trash."
                        : app.updateIds.map(id => "  •  " + (app.addons.find(a => a.id === id)?.name || id) + "  →  " + (app.checks[id]?.latest || "")).join("\n")
                    font.pixelSize: 13; color: UI.Theme.muted; wrapMode: Text.Wrap; lineHeight: 1.4
                }
                UI.SearchField {
                    id: addLocation
                    objectName: "addLocation"
                    visible: app.dialogAction === "add"
                    Layout.fillWidth: true
                    implicitHeight: 43
                    placeholderText: "curseforge.com/wow/addons/…  ·  wowinterface.com/downloads/…  ·  ~/Downloads/addon.zip"
                    onAccepted: { if (confirmButton.enabled) confirmButton.clicked() }
                }
                ColumnLayout {
                    visible: app.dialogAction === "add" && app.downloads.length > 0
                    Layout.fillWidth: true
                    spacing: 6
                    UI.Label { text: "RECENT DOWNLOADS"; color: UI.Theme.muted; font.pixelSize: 9; font.letterSpacing: 1.5 }
                    Repeater {
                        model: app.downloads
                        delegate: UI.ActionButton {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 32
                            text: modelData.name
                            onClicked: addLocation.text = modelData.path
                        }
                    }
                }
                UI.Label { visible: app.demo; text: "Preview only. Actions are disabled."; color: UI.Theme.warning; font.pixelSize: 12 }
                RowLayout {
                    Item { Layout.fillWidth: true }
                    UI.ActionButton { text: "Cancel"; onClicked: dialog.close() }
                    UI.ActionButton {
                        id: confirmButton
                        text: ({add: "Install", remove: "Move to trash", replace: "Replace and install", updateAll: "Update all"})[app.dialogAction] || "OK"
                        primary: app.dialogAction !== "remove"
                        danger: app.dialogAction === "remove"
                        enabled: !app.busy && (app.dialogAction !== "add" || addLocation.text.trim().length > 0)
                        onClicked: {
                            let action = app.dialogAction
                            dialog.close()
                            if (action === "add") app.execute({action: "install", location: addLocation.text.trim()})
                            else if (action === "remove") app.execute({action: "remove", id: app.dialogTarget.id})
                            else if (action === "replace") app.execute(app.dialogTarget.request)
                            else app.update(app.updateIds.slice())
                        }
                    }
                }
            }
        }
    }
}
