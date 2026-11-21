import QtQuick
import org.kde.kirigami as Kirigami

// Where the substance is at the cursor time. The compartments fill and drain
// from the model, and particles drift along the path at a speed set by the
// actual flux, so a fast-absorbing route visibly rushes.
Item {
    id: root
    required property var session
    property color accent: Kirigami.Theme.highlightColor

    readonly property var st: session.bodyState
    readonly property bool isIV: session.info.route === "iv"
    readonly property bool isLung: ["smoked", "vaped"].indexOf(session.info.route) >= 0
    readonly property bool isBuccal: ["gum", "oral_pouch", "patch"].indexOf(session.info.route) >= 0

    // the entry compartment is named for the route
    readonly property string entryName: isIV ? "Vein" : isLung ? "Lungs"
                                       : session.info.route === "patch" ? "Skin"
                                       : isBuccal ? "Mouth" : "Stomach / gut"

    onStChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()

    Rectangle {
        anchors.fill: parent
        radius: 6
        border.color: Qt.rgba(1, 1, 1, 0.09)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.lighter(Kirigami.Theme.backgroundColor, 1.2) }
            GradientStop { position: 1.0; color: Qt.darker(Kirigami.Theme.backgroundColor, 1.2) }
        }
    }

    Timer {
        interval: 33; running: root.visible; repeat: true
        onTriggered: { canvas.phase = (canvas.phase + 0.012) % 1; canvas.requestPaint() }
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        anchors.margins: 10
        property real phase: 0

        function vessel(ctx, x, y, w, h, frac, color, label, amount, unit) {
            // glass tube with a liquid level — the Oxygen look
            ctx.save()
            ctx.beginPath(); ctx.roundedRect(x, y, w, h, 6, 6)
            const bg = ctx.createLinearGradient(x, y, x + w, y)
            bg.addColorStop(0, Qt.rgba(1, 1, 1, 0.05))
            bg.addColorStop(0.5, Qt.rgba(1, 1, 1, 0.10))
            bg.addColorStop(1, Qt.rgba(1, 1, 1, 0.04))
            ctx.fillStyle = bg; ctx.fill()
            ctx.clip()

            const fh = Math.max(0, Math.min(1, frac)) * h
            if (fh > 0.5) {
                const lg = ctx.createLinearGradient(x, y + h - fh, x, y + h)
                lg.addColorStop(0, Qt.lighter(color, 1.5))
                lg.addColorStop(0.3, color)
                lg.addColorStop(1, Qt.darker(color, 1.6))
                ctx.fillStyle = lg
                ctx.fillRect(x, y + h - fh, w, fh)
                // meniscus highlight
                ctx.fillStyle = Qt.rgba(1, 1, 1, 0.45)
                ctx.fillRect(x, y + h - fh, w, 1.5)
            }
            ctx.restore()

            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.22)
            ctx.lineWidth = 1
            ctx.beginPath(); ctx.roundedRect(x, y, w, h, 6, 6); ctx.stroke()
            // gloss
            const gl = ctx.createLinearGradient(x, y, x, y + h * 0.45)
            gl.addColorStop(0, Qt.rgba(1, 1, 1, 0.20))
            gl.addColorStop(1, Qt.rgba(1, 1, 1, 0))
            ctx.fillStyle = gl
            ctx.beginPath(); ctx.roundedRect(x + 1, y + 1, w - 2, h * 0.45, 5, 5); ctx.fill()

            const fg = Kirigami.Theme.textColor
            ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.85)
            ctx.font = "11px 'Oxygen', sans-serif"
            ctx.textAlign = "center"
            ctx.fillText(label, x + w / 2, y - 8)
            ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.6)
            ctx.font = "10px 'JetBrains Mono'"
            ctx.fillText(amount, x + w / 2, y + h + 15)
        }

        function flow(ctx, x0, y, x1, intensity, color) {
            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.12)
            ctx.lineWidth = 1
            ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke()
            if (intensity <= 0.001) return
            const n = 5
            for (let i = 0; i < n; i++) {
                const f = ((phase * (0.4 + intensity * 3) * 4) + i / n) % 1
                const px = x0 + (x1 - x0) * f
                const a = Math.min(1, intensity * 6) * Math.sin(Math.PI * f)
                ctx.fillStyle = Qt.rgba(color.r, color.g, color.b, a * 0.9)
                ctx.beginPath(); ctx.arc(px, y, 2.4, 0, 2 * Math.PI); ctx.fill()
            }
            // arrow head
            ctx.fillStyle = Qt.rgba(1, 1, 1, 0.25)
            ctx.beginPath()
            ctx.moveTo(x1, y); ctx.lineTo(x1 - 5, y - 3.5); ctx.lineTo(x1 - 5, y + 3.5)
            ctx.closePath(); ctx.fill()
        }

        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const st = root.st
            const s = root.session
            const col = Qt.color(s.info.color)
            const fg = Kirigami.Theme.textColor

            const n = 3
            const gap = 34
            const w = (width - gap * (n - 1)) / n
            const h = height * 0.44
            const y = height * 0.26
            const xs = [0, w + gap, 2 * (w + gap)]

            // flows: scaled by how fast each is actually moving right now
            const absorbRate = st.gut * 0.5
            const elimRate = Math.max(0, st.blood) * 0.4

            flow(ctx, xs[0] + w + 3, y + h / 2, xs[1] - 4, absorbRate, col)
            flow(ctx, xs[1] + w + 3, y + h / 2, xs[2] - 4, elimRate, col)

            vessel(ctx, xs[0], y, w, h, st.gut, Qt.darker(col, 1.3),
                   root.entryName, st.gutMg.toFixed(st.gutMg < 10 ? 2 : 0) + " mg")
            vessel(ctx, xs[1], y, w, h, st.blood, col,
                   "Bloodstream", st.bloodMg.toFixed(st.bloodMg < 10 ? 2 : 0) + " mg")
            vessel(ctx, xs[2], y, w, h, st.eliminated, Qt.rgba(0.45, 0.45, 0.5, 1),
                   "Metabolised / excreted",
                   st.eliminatedMg.toFixed(st.eliminatedMg < 10 ? 2 : 0) + " mg")

            // first-pass note under the absorption arrow
            ctx.font = "9px 'Oxygen', sans-serif"
            ctx.textAlign = "center"
            ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.45)
            const fpct = Math.round((1 - s.info.bioavailability) * 100)
            if (!root.isIV && fpct > 2)
                ctx.fillText("first pass −" + fpct + "%", (xs[0] + w + xs[1]) / 2, y + h / 2 - 12)
            ctx.fillText(root.isIV ? "direct" : "absorption", (xs[0] + w + xs[1]) / 2, y + h / 2 + 20)
            ctx.fillText(s.info.enzyme, (xs[1] + w + xs[2]) / 2, y + h / 2 + 20)

            // metabolite bar along the bottom
            const mets = st.metabolites
            if (mets && mets.length) {
                const by = y + h + 42
                const bh = 16
                let x = 0
                const total = mets.reduce((a, m) => a + m.frac, 0)
                const palette = ["#6fb3d9", "#7fc47f", "#d9a441", "#e0455a", "#b08fd9"]
                ctx.textAlign = "left"
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.55)
                ctx.font = "10px 'Oxygen', sans-serif"
                ctx.fillText("Metabolites formed so far", 0, by - 6)
                for (let i = 0; i < mets.length; i++) {
                    const m = mets[i]
                    const mw = total > 0 ? (m.frac / Math.max(total, 1e-9)) * width * Math.min(1, total) : 0
                    const danger = m.name.indexOf("NAPQI") >= 0
                    const c = danger ? "#e0455a" : palette[i % palette.length]
                    const g = ctx.createLinearGradient(0, by, 0, by + bh)
                    g.addColorStop(0, Qt.lighter(c, 1.4))
                    g.addColorStop(1, Qt.darker(c, 1.3))
                    ctx.fillStyle = g
                    ctx.fillRect(x, by, Math.max(0, mw - 1), bh)
                    x += mw
                }
                ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.12)
                ctx.strokeRect(0, by, width, bh)
                // key
                let kx = 0
                ctx.font = "9px 'Oxygen', sans-serif"
                for (let i = 0; i < mets.length; i++) {
                    const m = mets[i]
                    const danger = m.name.indexOf("NAPQI") >= 0
                    const c = danger ? "#e0455a" : palette[i % palette.length]
                    const label = m.name.split(" (")[0] + " " + m.mg.toFixed(m.mg < 10 ? 1 : 0) + "mg"
                    const tw = ctx.measureText(label).width + 16
                    if (kx + tw > width) break
                    ctx.fillStyle = c
                    ctx.fillRect(kx, by + bh + 8, 8, 8)
                    ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, danger ? 0.95 : 0.65)
                    ctx.fillText(label, kx + 11, by + bh + 16)
                    kx += tw + 6
                }
            }
        }
    }
}
