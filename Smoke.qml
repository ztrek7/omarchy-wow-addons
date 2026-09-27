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
            app.check(app.names(installed.results) === "Quest Compass, Trade Ledger", "update filter includes hand installs with a source")
            status.currentIndex = 4
            app.check(app.names(installed.results) === "Old Timers", "out of date filter")
            status.currentIndex = 2
            app.check(app.names(installed.results) === "Minimal Frames", "disabled filter")
            status.currentIndex = 0
            source.currentIndex = 5
            app.check(app.names(installed.results) === "Old Timers, Trade Ledger", "manual source filter")
            source.currentIndex = 1
            app.check(installed.results.length === 0, "CurseForge source filter")
            source.currentIndex = 2
            app.check(app.names(installed.results) === "Minimal Frames, Quest Compass", "WoWInterface source filter")
            source.currentIndex = 0
            sort.currentIndex = 1
            app.check(installed.results[0].name === "Trade Ledger", "Z–A sort")
            sort.currentIndex = 2
            app.check(installed.results[0].name === "BagSort", "recently installed sort")
            sort.currentIndex = 3
            app.check(app.names(installed.results.slice(0, 3)) === "Quest Compass, Trade Ledger, Old Timers", "needs attention sort")
            sort.currentIndex = 0
            search.text = "COMPASS"
            app.check(app.names(installed.results) === "Quest Compass", "case-insensitive search")
            search.text = "questcompass_options"
            app.check(installed.results.length === 1, "search matches folder names")
            search.text = ""
            installed.selectedId = "wowi:9001"
            app.check(app.updateIds.length === 2, "two updates available")
            app.check(app.find(app.windowItem, "nav-installed").contentItem.text.indexOf("2 ↑") > 0, "update count in navigation")
            app.checkUpdates(true)
            app.check(!app.checking, "demo mode never checks the network")

            let browse = app.browseView
            let game = app.find(browse, "gameFilter"), hide = app.find(browse, "hideInstalled")
            let bsort = app.find(browse, "browseSort"), category = app.find(browse, "categoryFilter")
            let updated = app.find(browse, "updatedFilter"), bsearch = app.find(browse, "browseSearch")
            app.check(game && hide && bsort && category && updated && bsearch, "browse controls exist")
            let entries = r => r.map(x => x.entry)
            let byName = name => app.catalog.find(e => e.name === name)
            app.check(browse.results.every(x => x.refs.some(r => browse.fitsRef(r))), "default shows addons made for this game")
            app.check(!entries(browse.results).some(e => e.name === "Retail Only Meter"), "CurseForge flavour filter")
            let forGame = browse.results.length
            game.currentIndex = 1
            app.check(browse.results.length === app.catalog.length && forGame < app.catalog.length, "any game version shows everything once")
            app.check(app.names(entries(browse.results.slice(0, 2))) === "Trade Ledger, Quest Compass", "most downloaded sums every site's downloads")
            app.check(browse.results[1].downloads === 1250000 + 482000, "downloads total")
            bsort.currentIndex = 2
            app.check(browse.results[0].entry.name === "Arcane Bags", "name sort")
            bsort.currentIndex = 3
            app.check(browse.results[0].entry.name === "Trade Ledger Classic Fix", "reverse name sort")
            bsort.currentIndex = 1
            app.check(browse.results.every((x, i) => i === 0 || browse.results[i - 1].updated >= x.updated), "recently updated sort")
            bsort.currentIndex = 0
            app.check(app.entryState(byName("Quest Compass")) === "update", "installed from one site, matched in a merged entry")
            app.check(app.entryState(byName("Minimal Frames")) === "installed", "installed state")
            app.check(app.entryState(byName("Trade Ledger")) === "update", "hand install matched through its TOC source")
            app.check(app.entryState(byName("Trade Ledger Classic Fix")) === "replace", "fork using the same folder needs confirmation")
            app.check(browse.bestRef(byName("Quest Compass")).source === "curseforge", "installs from the most recently updated site")

            let curse = app.find(browse, "source-curseforge"), wowi = app.find(browse, "source-wowinterface"), tukui = app.find(browse, "source-tukui")
            app.check(curse && wowi && tukui && curse.checked && wowi.checked && tukui.checked, "all sources on by default")
            app.check(tukui.text.indexOf("⚠") > 0, "source errors are flagged")
            let total = browse.results.length
            app.setSource("curseforge", false)
            app.check(!entries(browse.results).some(e => e.name === "Forge Timers") && entries(browse.results).some(e => e.name === "Quest Compass"), "turning CurseForge off keeps merged entries")
            app.check(browse.bestRef(byName("Quest Compass")).source === "wowinterface", "install falls back to an enabled site")
            app.setSource("wowinterface", false)
            app.setSource("tukui", false)
            app.check(browse.results.length === 0, "all sources off")
            app.setSource("curseforge", true); app.setSource("wowinterface", true); app.setSource("tukui", true)
            app.check(browse.results.length === total, "sources back on")

            hide.checked = true
            app.check(!entries(browse.results).some(e => ["Quest Compass", "Minimal Frames", "Trade Ledger", "Trade Ledger Classic Fix"].indexOf(e.name) >= 0), "hide installed")
            hide.checked = false
            updated.currentIndex = 1
            app.check(browse.results.every(x => x.updated >= Date.now() - 31 * 86400000) && browse.results.length > 0, "updated past month")
            updated.currentIndex = 0
            category.currentIndex = 1 + browse.categories.findIndex(c => c.name === "Unit Mods")
            app.check(browse.results.length > 0 && browse.results.every(x => x.entry.category === "Unit Mods"), "category filter")
            category.currentIndex = 0
            bsearch.text = "timers"
            app.check(browse.results.length === 11, "browse search: " + browse.results.length)
            bsearch.text = ""
            game.currentIndex = 0

            app.shot("installed", () => {
                app.page = "browse"
                Qt.callLater(() => app.shot("browse", () => {
                    browse.openDetails(app.catalog.find(e => e.name === "Quest Compass"))
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
