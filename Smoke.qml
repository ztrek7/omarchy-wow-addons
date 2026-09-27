import QtQuick
import Quickshell
import "."

// Run with WOW_ADDONS_DEMO=1 quickshell -n -p Smoke.qml. Uses tests/demo.json only.
// Set SMOKE_SHOTS to a folder to save screenshots of each page.
App {
    id: app
    function find(item, name) {
        if (item.objectName === name) return item
        for (let child of item.children || []) {
            let match = find(child, name)
            if (match) return match
        }
        return null
    }
    function check(condition, message) {
        if (!condition) { console.error("SMOKE FAILED: " + message); Qt.exit(1); throw new Error(message) }
    }
    function names(list) { return list.map(x => x.name).join(", ") }
    property var steps: []
    property int step: 0
    function shot(name, next) {
        let folder = Quickshell.env("SMOKE_SHOTS")
        if (!folder) { next(); return }
        app.windowItem.grabToImage(result => { result.saveToFile(folder + "/" + name + ".png"); next() })
    }
    Timer {
        interval: 1000
        running: true
        onTriggered: {
            app.check(app.demo, "demo mode (set WOW_ADDONS_DEMO=1)")
            let installed = app.installedView
            let status = app.find(installed, "statusFilter"), source = app.find(installed, "sourceFilter")
            let sort = app.find(installed, "installedSort"), search = app.find(installed, "installedSearch")
            app.check(status && source && sort && search, "installed controls exist")
            app.check(installed.results.length === 5, "all five installed addons listed: " + app.names(installed.results))
            app.check(installed.results[0].name === "BagSort", "sorted by name")
            status.currentIndex = 3
            app.check(app.names(installed.results) === "Quest Compass", "update filter")
            status.currentIndex = 4
            app.check(app.names(installed.results) === "Old Timers", "out of date filter")
            status.currentIndex = 2
            app.check(app.names(installed.results) === "Minimal Frames", "disabled filter")
            status.currentIndex = 0
            source.currentIndex = 3
            app.check(app.names(installed.results) === "Old Timers, Trade Ledger", "manual source filter")
            source.currentIndex = 0
            sort.currentIndex = 1
            app.check(installed.results[0].name === "Trade Ledger", "Z–A sort")
            sort.currentIndex = 2
            app.check(installed.results[0].name === "BagSort", "recently installed sort")
            sort.currentIndex = 3
            app.check(installed.results[0].name === "Quest Compass" && installed.results[1].name === "Old Timers", "needs attention sort")
            sort.currentIndex = 0
            search.text = "COMPASS"
            app.check(app.names(installed.results) === "Quest Compass", "case-insensitive search")
            search.text = "questcompass_options"
            app.check(installed.results.length === 1, "search matches folder names")
            search.text = ""
            installed.selectedId = "wowi:9001"
            app.check(app.updateIds.length === 1, "one update available")

            let browse = app.browseView
            let game = app.find(browse, "gameFilter"), hide = app.find(browse, "hideInstalled")
            let bsort = app.find(browse, "browseSort"), category = app.find(browse, "categoryFilter")
            let updated = app.find(browse, "updatedFilter"), bsearch = app.find(browse, "browseSearch")
            app.check(game && hide && bsort && category && updated && bsearch, "browse controls exist")
            app.check(browse.results.every(e => e.gameVersions.some(v => v.startsWith("1."))), "default shows addons made for 1.x")
            let forGame = browse.results.length
            game.currentIndex = 1
            app.check(browse.results.length === app.catalog.length && forGame < app.catalog.length, "any game version")
            app.check(browse.results[0].name === "Quest Compass", "most downloaded first")
            bsort.currentIndex = 4
            app.check(browse.results[0].name === "Arcane Bags", "name sort")
            bsort.currentIndex = 3
            app.check(browse.results.every((e, i) => i === 0 || browse.results[i - 1].updated >= e.updated), "recently updated sort")
            bsort.currentIndex = 0
            app.check(app.entryState(app.catalog[0]) === "update" && app.entryState(app.catalog[1]) === "installed" && app.entryState(app.catalog[2]) === "replace", "install states")
            hide.checked = true
            app.check(!browse.results.some(e => ["9001", "9002", "9003"].indexOf(e.id) >= 0), "hide installed")
            hide.checked = false
            updated.currentIndex = 1
            app.check(browse.results.every(e => e.updated >= Date.now() - 31 * 86400000) && browse.results.length > 0, "updated past month")
            updated.currentIndex = 0
            category.currentIndex = 1 + browse.categories.findIndex(c => c.name === "Unit Mods")
            app.check(browse.results.length > 0 && browse.results.every(e => e.category === "Unit Mods"), "category filter")
            category.currentIndex = 0
            bsearch.text = "timers"
            app.check(browse.results.length === 10 && browse.results.every(e => e.name.indexOf("Timers") > 0), "browse search")
            bsearch.text = ""
            game.currentIndex = 0

            app.shot("installed", () => {
                app.page = "browse"
                Qt.callLater(() => app.shot("browse", () => {
                    browse.openDetails(app.catalog[0])
                    detailsTimer.start()
                }))
            })
        }
    }
    Timer {
        id: detailsTimer
        interval: 400
        onTriggered: {
            app.check(app.browseView.detailsOpen && app.browseView.info?.name === "Quest Compass", "details popup shows fetched details")
            app.browseView.closeDetails()
            app.page = "settings"
            Qt.callLater(() => app.shot("settings", () => { console.log("SMOKE PASSED"); Qt.quit() }))
        }
    }
}
