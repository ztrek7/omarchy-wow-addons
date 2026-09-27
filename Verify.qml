import QtQuick
import Quickshell
import "."

// Read-only check against the configured game folder and the live catalog.
// Set VERIFY_SHOTS to a folder to save screenshots.
App {
    id: app
    property double started: Date.now()
    function shot(name, next) {
        let folder = Quickshell.env("VERIFY_SHOTS")
        if (!folder) { next(); return }
        app.windowItem.grabToImage(result => { result.saveToFile(folder + "/" + name + ".png"); next() })
    }
    Timer {
        interval: 250
        running: true
        repeat: true
        property int attempts: 0
        onTriggered: {
            attempts++
            if ((app.busy || !app.catalog.length) && attempts < 240) return
            stop()
            if (app.failed || !app.game || !app.catalog.length) {
                console.error("LIVE VERIFY FAILED: " + app.status + " · " + app.catalogMessage)
                Qt.exit(1)
                return
            }
            let t = Date.now()
            let shown = app.browseView.results.length
            console.log("catalog " + app.catalog.length + " entries, " + shown + " for this game, filter+sort " + (Date.now() - t) + " ms, ready after " + (Date.now() - app.started) + " ms")
            app.shot("live-installed", () => {
                app.page = "browse"
                browseShot.start()
            })
        }
    }
    // Give catalog thumbnails time to arrive before the capture.
    Timer {
        id: browseShot
        interval: 3000
        onTriggered: app.shot("live-browse", () => {
            console.log("LIVE VERIFY PASSED: " + app.addons.length + " addons in " + app.gameLabel())
            Qt.quit()
        })
    }
}
