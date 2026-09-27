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
            status.currentIndex = 5
            app.check(app.names(installed.results) === "Old Timers", "missing requirements filter")
            app.check(installed.badges(installed.results[0])[0].text === "Needs TimerLib", "missing requirement badge")
            status.currentIndex = 0
            source.currentIndex = 3
            app.check(app.names(installed.results) === "Old Timers, Trade Ledger", "manual source filter")
            source.currentIndex = 1
            app.check(app.names(installed.results) === "BagSort", "CurseForge source filter")
            source.currentIndex = 2
            app.check(app.names(installed.results) === "Minimal Frames, Quest Compass", "WoWInterface source filter")
            source.currentIndex = 0
            sort.currentIndex = 1
            app.check(installed.results[0].name === "Trade Ledger", "Z–A sort")
            sort.currentIndex = 2
            app.check(installed.results[0].name === "BagSort", "recently installed sort")
            sort.currentIndex = 3
            app.check(app.names(installed.results.slice(0, 3)) === "Old Timers, Quest Compass, Trade Ledger", "needs attention sort puts missing requirements first")
            sort.currentIndex = 0
            search.text = "COMPASS"
            app.check(app.names(installed.results) === "Quest Compass", "case-insensitive search")
            search.text = "questcompass_options"
            app.check(installed.results.length === 1, "search matches folder names")
            search.text = ""
            // Installed addons use their Browse listing's icon.
            app.check(app.rowEntries["wowi:9001"]?.name === "Quest Compass", "installed addon matched to its listing")
            app.check(app.rowEntries["local:TradeLedger"]?.name === "Trade Ledger", "hand install matched through its TOC source")
            app.check(!app.rowEntries["local:OldTimers"], "no listing, no icon")
            let logo = Qt.resolvedUrl("assets/sources/curseforge.png").toString()
            app.cfLogos = {"quest-compass": logo}
            app.check(app.iconFor(app.rowEntries["wowi:9001"]) === logo, "same icon as Browse")
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
            app.check(JSON.stringify(game.model) === JSON.stringify(["WoW Classic Era 1.15.7", "WoW Retail 12.1.0", "Any game version"]), "game menu lists detected games: " + JSON.stringify(game.model))
            app.check(game.currentIndex === 0, "game menu starts on the game in use")
            let forGame = browse.results.length
            game.activated(2)
            app.check(browse.anyGame && game.currentIndex === 2, "any game version")
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

            let curse = app.find(browse, "source-curseforge"), wowi = app.find(browse, "source-wowinterface")
            app.check(curse && wowi && curse.checked && wowi.checked, "both sources on by default")
            app.check(!app.find(browse, "source-tukui"), "only CurseForge and WoWInterface")
            app.check(wowi.text.indexOf("⚠") > 0 && curse.text.indexOf("⚠") < 0, "source errors are flagged")
            app.check(!app.catalog.some(e => e.sources.some(r => r.source === "github" || r.source === "tukui")), "no other sources in the catalog")
            let total = browse.results.length
            app.setSource("curseforge", false)
            app.check(!entries(browse.results).some(e => e.name === "Forge Timers") && entries(browse.results).some(e => e.name === "Quest Compass"), "turning CurseForge off keeps merged entries")
            app.check(browse.bestRef(byName("Quest Compass")).source === "wowinterface", "install falls back to an enabled site")
            app.setSource("wowinterface", false)
            app.check(browse.results.length === 0, "all sources off")
            app.setSource("curseforge", true); app.setSource("wowinterface", true)
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
            game.activated(0)
            app.check(!browse.anyGame && browse.results.length === forGame, "back to the game in use")
            app.check(app.fullDate(Date.UTC(2026, 8, 21, 12)) === "September 21, 2026", "full dates")
            let report = app.reportDetails()
            app.check(report.indexOf("Game: WoW Classic Era 1.15.7") >= 0 && report.indexOf(Quickshell.env("HOME")) < 0, "report details: " + report)
            bsearch.forceActiveFocus(); bsearch.text = "bags"
            app.check(browse.clearSearch() && bsearch.text === "", "Escape clears a search first")

            // Only claim what a site lists: a 2019 addon for 1.13.2 is Classic Era, not WoW Forever.
            let shaman = byName("Old Blue Shaman")
            app.check(browse.listedText(shaman.sources) === "Listed for WoW Classic Era", "Classic Era addon listed as such: " + browse.listedText(shaman.sources))
            let era = app.setup
            let forever = {key: "_classic_beta_", name: "WoW Forever Beta", version: "1.60.1", interface: 16001, major: 1, flavour: "forever_classic", addons: "/tmp/demo/x", path: "/tmp/demo/x"}
            app.setup = Object.assign({}, era, {flavor: forever, flavors: era.flavors.concat([forever])})
            app.check(browse.listedText(shaman.sources) === "Listed for WoW Classic Era 1.13.2", "not claimed for WoW Forever: " + browse.listedText(shaman.sources))
            app.check(!entries(browse.results).some(e => e.name === "Old Blue Shaman"), "Classic Era addon hidden for WoW Forever")
            app.check(entries(browse.results).some(e => e.name === "Trade Ledger"), "addon tagged for WoW Forever shown")
            app.check(browse.listedText(byName("Trade Ledger").sources) === "Listed for WoW Forever", "Forever tag named without Beta")
            app.check(browse.results.every(x => x.refs.some(r => (r.flavours || []).indexOf("forever_classic") >= 0)), "every result is listed for WoW Forever")
            app.setup = era

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
