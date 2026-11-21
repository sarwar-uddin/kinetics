import QtQuick
import org.kde.kirigami as Kirigami

// A human figure with the compartments drawn where they actually are. Each
// organ fills with colour in proportion to how much of the substance is in it
// at the cursor time, and particles travel the real routes: entry site to
// blood, blood to brain, blood to tissue and back, blood to liver and out.
Item {
    id: root
    required property var session
    property color accent: Kirigami.Theme.highlightColor

    readonly property var st: session.bodyState
    readonly property string route: st.route ?? "oral"
    readonly property bool isIV: route === "iv"
    readonly property bool isLung: ["smoked", "vaped", "vaporised"].indexOf(route) >= 0
    readonly property bool isNasal: route === "insufflated"
    readonly property bool isSkin: ["patch", "transdermal"].indexOf(route) >= 0
    readonly property bool isBuccal: ["gum", "oral_pouch", "sublingual"].indexOf(route) >= 0
    readonly property bool isGut: !isIV && !isLung && !isNasal && !isSkin && !isBuccal

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
        onTriggered: { canvas.phase = (canvas.phase + 0.009) % 1; canvas.requestPaint() }
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        anchors.margins: 8
        property real phase: 0

        // ---- the figure, in a 0..100 x 0..200 coordinate space
        function silhouette(ctx, s, ox, oy) {
            function X(v) { return ox + v * s }
            function Y(v) { return oy + v * s }
            ctx.beginPath()
            // head
            ctx.ellipse(X(39), Y(4), 22 * s, 26 * s)
            ctx.closePath()
            ctx.fill()
            // neck + torso + legs as one rounded body
            ctx.beginPath()
            ctx.moveTo(X(44), Y(28))
            ctx.lineTo(X(56), Y(28))
            ctx.lineTo(X(58), Y(36))
            ctx.lineTo(X(76), Y(44))   // shoulder right
            ctx.quadraticCurveTo(X(82), Y(48), X(80), Y(60))
            ctx.lineTo(X(76), Y(104))  // arm right
            ctx.quadraticCurveTo(X(75), Y(110), X(70), Y(109))
            ctx.quadraticCurveTo(X(66), Y(108), X(67), Y(101))
            ctx.lineTo(X(69), Y(62))
            ctx.lineTo(X(66), Y(58))
            ctx.lineTo(X(64), Y(96))   // hip right
            ctx.lineTo(X(62), Y(190))  // leg right
            ctx.quadraticCurveTo(X(61), Y(196), X(55), Y(195))
            ctx.quadraticCurveTo(X(50), Y(194), X(51), Y(188))
            ctx.lineTo(X(52), Y(110))
            ctx.lineTo(X(48), Y(110))
            ctx.lineTo(X(49), Y(188))  // leg left
            ctx.quadraticCurveTo(X(50), Y(194), X(45), Y(195))
            ctx.quadraticCurveTo(X(39), Y(196), X(38), Y(190))
            ctx.lineTo(X(36), Y(96))
            ctx.lineTo(X(34), Y(58))
            ctx.lineTo(X(31), Y(62))
            ctx.lineTo(X(33), Y(101))  // arm left
            ctx.quadraticCurveTo(X(34), Y(108), X(30), Y(109))
            ctx.quadraticCurveTo(X(25), Y(110), X(24), Y(104))
            ctx.lineTo(X(20), Y(60))
            ctx.quadraticCurveTo(X(18), Y(48), X(24), Y(44))
            ctx.lineTo(X(42), Y(36))
            ctx.closePath()
            ctx.fill()
        }

        function organ(ctx, x, y, w, h, frac, color, round) {
            const f = Math.max(0, Math.min(1, frac))
            ctx.save()
            ctx.beginPath()
            if (round) ctx.ellipse(x - w / 2, y - h / 2, w, h)
            else ctx.roundedRect(x - w / 2, y - h / 2, w, h, 4, 4)
            ctx.fillStyle = Qt.rgba(1, 1, 1, 0.07)
            ctx.fill()
            if (f > 0.004) {
                ctx.clip()
                const g = ctx.createLinearGradient(x, y - h / 2, x, y + h / 2)
                g.addColorStop(0, Qt.lighter(color, 1.5))
                g.addColorStop(1, Qt.darker(color, 1.4))
                ctx.globalAlpha = 0.25 + 0.75 * Math.min(1, f * 1.6)
                ctx.fillStyle = g
                ctx.fill()
                ctx.globalAlpha = 1
            }
            ctx.restore()
            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.22)
            ctx.lineWidth = 1
            ctx.beginPath()
            if (round) ctx.ellipse(x - w / 2, y - h / 2, w, h)
            else ctx.roundedRect(x - w / 2, y - h / 2, w, h, 4, 4)
            ctx.stroke()
        }

        function label(ctx, x, y, text, value, align, dim) {
            const fg = Kirigami.Theme.textColor
            ctx.textAlign = align
            ctx.font = "9px 'Oxygen', sans-serif"
            ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, dim ? 0.4 : 0.8)
            ctx.fillText(text, x, y)
            if (value) {
                ctx.font = "9px 'JetBrains Mono'"
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, dim ? 0.3 : 0.6)
                ctx.fillText(value, x, y + 11)
            }
        }

        function stream(ctx, pts, intensity, color, speed) {
            if (intensity <= 0.002) return
            const n = 4
            for (let i = 0; i < n; i++) {
                const f = ((phase * speed) + i / n) % 1
                // walk the polyline
                let total = 0
                for (let k = 1; k < pts.length; k++)
                    total += Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
                let want = f * total, px = pts[0][0], py = pts[0][1]
                for (let k = 1; k < pts.length; k++) {
                    const seg = Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
                    if (want <= seg) {
                        const r = seg > 0 ? want / seg : 0
                        px = pts[k - 1][0] + (pts[k][0] - pts[k - 1][0]) * r
                        py = pts[k - 1][1] + (pts[k][1] - pts[k - 1][1]) * r
                        break
                    }
                    want -= seg
                    px = pts[k][0]; py = pts[k][1]
                }
                const a = Math.min(1, intensity * 5) * Math.sin(Math.PI * f)
                ctx.fillStyle = Qt.rgba(color.r, color.g, color.b, a)
                ctx.beginPath(); ctx.arc(px, py, 2.2, 0, 2 * Math.PI); ctx.fill()
            }
        }

        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const st = root.st
            if (!st || st.blood === undefined) return
            const col = Qt.color(root.session.mixed ? (st.color || root.accent)
                                                     : root.session.info.color)
            const fg = Kirigami.Theme.textColor

            // fit the 100x200 figure into the available height
            const s = Math.min(height / 205, width / 190)
            const ox = width / 2 - 50 * s
            const oy = (height - 200 * s) / 2
            function X(v) { return ox + v * s }
            function Y(v) { return oy + v * s }

            // ---- body outline, tinted by how much is in the blood overall
            ctx.fillStyle = Qt.rgba(1, 1, 1, 0.045)
            silhouette(ctx, s, ox, oy)
            ctx.save()
            ctx.beginPath()
            silhouette(ctx, s, ox, oy)
            ctx.clip()
            // bloodstream wash through the whole body
            ctx.fillStyle = Qt.rgba(col.r, col.g, col.b,
                                    0.10 + 0.42 * Math.min(1, st.blood * 1.5))
            ctx.fillRect(0, 0, width, height)
            ctx.restore()
            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.16)
            ctx.lineWidth = 1
            ctx.save(); ctx.beginPath(); silhouette(ctx, s, ox, oy); ctx.restore()

            // ---- flows
            const absorbing = st.gut
            const brainFlow = st.blood
            const elimFlow = st.blood
            // entry -> blood (core)
            const entry = root.isLung ? [X(50), Y(50)]
                        : root.isNasal ? [X(50), Y(16)]
                        : root.isSkin ? [X(78), Y(70)]
                        : root.isBuccal ? [X(50), Y(22)]
                        : root.isIV ? [X(26), Y(80)]
                        : [X(50), Y(74)]
            stream(ctx, [entry, [X(50), Y(56)]], absorbing + (root.isIV ? st.blood : 0), col, 2.2)
            // blood -> brain
            stream(ctx, [[X(50), Y(50)], [X(50), Y(20)]], brainFlow, col, 1.4)
            // blood -> liver -> out
            stream(ctx, [[X(50), Y(56)], [X(38), Y(66)], [X(44), Y(100)], [X(44), Y(118)]],
                   elimFlow, col, 1.0)
            // blood <-> peripheral tissue (two-compartment only)
            if (st.twoCompartment) {
                stream(ctx, [[X(56), Y(60)], [X(72), Y(80)]], st.blood, col, 0.8)
                stream(ctx, [[X(30), Y(84)], [X(46), Y(62)]], st.peripheral, col, 0.5)
            }

            // ---- organs
            organ(ctx, X(50), Y(16), 26 * s, 22 * s, st.brain, col, true)          // brain
            organ(ctx, X(50), Y(52), 30 * s, 16 * s, st.blood, col, false)         // heart/blood
            organ(ctx, X(41), Y(70), 20 * s, 13 * s, st.eliminated * 0.8, "#c87b4a", false)  // liver
            if (root.isGut)
                organ(ctx, X(52), Y(86), 24 * s, 16 * s, st.gut, Qt.darker(col, 1.4), false) // gut
            if (root.isLung) {
                organ(ctx, X(40), Y(50), 13 * s, 20 * s, st.gut, Qt.darker(col, 1.3), true)
                organ(ctx, X(60), Y(50), 13 * s, 20 * s, st.gut, Qt.darker(col, 1.3), true)
            }
            organ(ctx, X(44), Y(104), 9 * s, 12 * s, st.eliminated, "#8fb8d9", true)  // kidney
            if (st.twoCompartment) {
                organ(ctx, X(76), Y(84), 11 * s, 30 * s, st.peripheral, Qt.lighter(col, 1.2), false)
                organ(ctx, X(26), Y(84), 11 * s, 30 * s, st.peripheral, Qt.lighter(col, 1.2), false)
            }

            // ---- labels
            const mg = (v) => v >= 100 ? v.toFixed(0) + " mg"
                             : v >= 1 ? v.toFixed(1) + " mg"
                             : (v * 1000).toFixed(0) + " µg"
            label(ctx, X(72), Y(14), "Brain", Math.round(st.brain * 100) + "% of peak", "left", false)
            label(ctx, X(72), Y(50), "Bloodstream", mg(st.bloodMg), "left", false)
            // enzyme names run long ("Plasma and liver esterases (pseudo…)"); the
            // canvas has no eliding, so shorten before drawing
            let enz = st.enzyme || ""
            if (enz.length > 22) enz = enz.replace(/\s*\(.*\)\s*/, "")
            if (enz.length > 22) enz = enz.slice(0, 21) + "…"
            label(ctx, X(28), Y(70), "Liver", enz, "right", false)
            if (root.isGut) label(ctx, X(78), Y(88), root.isBuccal ? "Mouth" : "Gut", mg(st.gutMg), "left", st.gut < 0.01)
            if (root.isLung) label(ctx, X(26), Y(44), "Lungs", mg(st.gutMg), "right", st.gut < 0.01)
            label(ctx, X(28), Y(106), "Kidneys", mg(st.eliminatedMg) + " gone", "right", false)
            if (st.twoCompartment)
                label(ctx, X(76), Y(122), "Tissue / fat", mg(st.peripheralMg), "center", st.peripheral < 0.01)

            // entry-site caption
            const entryName = root.isIV ? "intravenous" : root.isLung ? "inhaled"
                            : root.isNasal ? "nasal" : root.isSkin ? "transdermal"
                            : root.isBuccal ? "buccal" : "swallowed"
            ctx.textAlign = "center"
            ctx.font = "9px 'Oxygen', sans-serif"
            ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.45)
            ctx.fillText(entryName + (st.firstPassPct > 2 && root.isGut
                         ? " · first pass −" + st.firstPassPct + "%" : ""),
                         X(50), Y(202))

            // ---- metabolite bar across the bottom
            const mets = st.metabolites
            if (mets && mets.length) {
                const by = height - 26
                const bh = 13
                const done = Math.min(1, st.eliminated)
                let x = 0
                const palette = ["#6fb3d9", "#7fc47f", "#d9a441", "#b08fd9", "#8fd4c4"]
                ctx.textAlign = "left"
                ctx.font = "9px 'Oxygen', sans-serif"
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.5)
                ctx.fillText("Metabolites formed", 0, by - 5)
                for (let i = 0; i < mets.length; i++) {
                    const m = mets[i]
                    const mw = m.frac * width
                    const c = m.danger ? "#e0455a" : (m.active ? "#d9a441" : palette[i % palette.length])
                    const g = ctx.createLinearGradient(0, by, 0, by + bh)
                    g.addColorStop(0, Qt.lighter(c, 1.35))
                    g.addColorStop(1, Qt.darker(c, 1.3))
                    ctx.fillStyle = g
                    ctx.fillRect(x, by, Math.max(0, mw - 1), bh)
                    x += mw
                }
                ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.12)
                ctx.strokeRect(0, by, width, bh)
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.4)
                ctx.textAlign = "right"
                ctx.fillText(Math.round(done * 100) + "% metabolised", width, by - 5)
            }
        }
    }

    // hover key for the metabolite bar
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        onPositionChanged: (e) => {
            const mets = root.st.metabolites || []
            if (e.y < canvas.height - 30 || !mets.length) { tip.visible = false; return }
            let x = 0, found = null
            for (const m of mets) {
                const w = m.frac * canvas.width
                if (e.x >= x && e.x < x + w) { found = m; break }
                x += w
            }
            if (found) {
                tip.text = found.name + " — " + found.mg.toFixed(found.mg < 10 ? 2 : 0) + " mg"
                        + (found.danger ? "  (reactive)" : found.active ? "  (active)" : "")
                tip.x = Math.min(Math.max(0, e.x - tip.width / 2), root.width - tip.width)
                tip.y = e.y - 26
                tip.visible = true
            } else tip.visible = false
        }
        onExited: tip.visible = false
    }

    Rectangle {
        id: tip
        property alias text: tipLabel.text
        visible: false
        width: tipLabel.width + 14
        height: tipLabel.height + 8
        radius: 4
        color: Qt.rgba(0, 0, 0, 0.85)
        border.color: Qt.rgba(1, 1, 1, 0.2)
        Text {
            id: tipLabel
            anchors.centerIn: parent
            color: "#ffffff"
            font.pointSize: Kirigami.Theme.smallFont.pointSize
        }
    }
}
