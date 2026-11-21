import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// Concentration against time. With one substance the axis is in real units;
// with several it switches to each curve's own peak, because mg/L of alcohol
// and µg/L of fentanyl share no meaningful scale — but their overlap in time
// is exactly what matters.
Item {
    id: root
    required property var session
    property color accent: Kirigami.Theme.highlightColor
    property var compare: null

    readonly property real padL: 64
    readonly property real padR: 18
    readonly property real padT: 20
    readonly property real padB: 44
    readonly property real plotW: Math.max(10, width - padL - padR)
    readonly property real plotH: Math.max(10, height - padT - padB)
    property real yMax: 1
    readonly property bool relative: session.mixed || !!compare === false && false

    function xOf(t) { return padL + t / Math.max(session.hours, 0.001) * plotW }
    function yOf(c) { return padT + plotH - Math.min(c / yMax, 1.02) * plotH }
    function tOf(x) { return Math.max(0, Math.min(session.hours,
                        (x - padL) / plotW * session.hours)) }

    function recomputeScale() {
        let curveTop = 0
        if (compare) {
            for (const s of compare) for (const p of s.points) curveTop = Math.max(curveTop, p[1])
        } else if (session.mixed) {
            curveTop = 1.0
        } else {
            for (const s of session.series)
                for (const p of s.points) curveTop = Math.max(curveTop, p[1])
        }
        // An effect line joins the axis only if it sits just above the curve.
        // Comparing against a running maximum lets each line drag in the next,
        // and the axis runs away to the highest one on the list.
        let top = curveTop
        if (!session.mixed)
            for (const lv of session.effectLevels)
                if (lv.y <= curveTop * 1.35) top = Math.max(top, lv.y * 1.02)
        yMax = top > 0 ? top * 1.14 : 1
        plot.requestPaint()
    }

    Connections {
        target: root.session
        function onCurveChanged() { root.recomputeScale() }
        function onTracksChanged() { root.recomputeScale() }
        function onCursorChanged() { plot.requestPaint() }
    }
    onCompareChanged: recomputeScale()
    onWidthChanged: recomputeScale()
    onHeightChanged: recomputeScale()
    Component.onCompleted: recomputeScale()

    Rectangle {
        anchors.fill: parent
        radius: 6
        border.color: Qt.rgba(1, 1, 1, 0.09)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.lighter(Kirigami.Theme.backgroundColor, 1.25) }
            GradientStop { position: 1.0; color: Qt.darker(Kirigami.Theme.backgroundColor, 1.25) }
        }
    }

    Canvas {
        id: plot
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative

        function niceStep(range, target) {
            const raw = range / target
            const mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10))
            const n = raw / mag
            return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag
        }

        function strokeSeries(ctx, pts, color, w, dash) {
            ctx.strokeStyle = color
            ctx.lineWidth = w
            ctx.lineJoin = "round"
            if (dash) ctx.setLineDash(dash)
            ctx.beginPath()
            pts.forEach((p, i) => {
                const x = root.xOf(p[0]), y = root.yOf(p[1])
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
            })
            ctx.stroke()
            if (dash) ctx.setLineDash([])
        }

        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const s = root.session
            const L = root.padL, T = root.padT, W = root.plotW, H = root.plotH
            const fg = Kirigami.Theme.textColor
            const mixed = s.mixed

            // ---- grid
            ctx.font = "10px 'JetBrains Mono'"
            ctx.textBaseline = "middle"
            const yStep = niceStep(root.yMax, 5)
            ctx.textAlign = "right"
            for (let v = 0; v <= root.yMax * 1.001; v += yStep) {
                const y = root.yOf(v)
                ctx.strokeStyle = Qt.rgba(1, 1, 1, v === 0 ? 0.22 : 0.07)
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + W, y); ctx.stroke()
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.55)
                const txt = mixed ? Math.round(v * 100) + "%"
                          : v.toFixed(yStep < 0.01 ? 3 : yStep < 1 ? 2 : 0)
                ctx.fillText(txt, L - 8, y)
            }
            const xStep = niceStep(s.hours, 8)
            ctx.textAlign = "center"
            for (let v = 0; v <= s.hours + 1e-9; v += xStep) {
                const x = root.xOf(v)
                ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.07)
                ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, T + H); ctx.stroke()
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.55)
                ctx.fillText(v >= 24 ? (v / 24).toFixed(v % 24 ? 1 : 0) + "d"
                                     : (v % 1 === 0 ? v + "h" : v.toFixed(1) + "h"), x, T + H + 15)
            }
            ctx.save()
            ctx.translate(14, T + H / 2)
            ctx.rotate(-Math.PI / 2)
            ctx.textAlign = "center"
            ctx.font = "9px 'Oxygen', sans-serif"
            ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.5)
            ctx.fillText(mixed ? "share of each substance's own peak"
                               : "blood concentration (" + s.stats.unit + ")", 0, 0)
            ctx.restore()

            // ---- effect level lines (single-substance only)
            ctx.textAlign = "left"
            if (!mixed) {
                for (const lv of s.effectLevels) {
                    if (lv.y > root.yMax) continue
                    const y = root.yOf(lv.y)
                    ctx.setLineDash([3, 4])
                    ctx.strokeStyle = Qt.rgba(1, 0.85, 0.3, 0.32)
                    ctx.lineWidth = 1
                    ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + W, y); ctx.stroke()
                    ctx.setLineDash([])
                    ctx.fillStyle = Qt.rgba(1, 0.85, 0.3, 0.5)
                    ctx.font = "9px 'Oxygen', sans-serif"
                    ctx.fillText(lv.label, L + 6, y - 7)
                    ctx.font = "10px 'JetBrains Mono'"
                }
            }

            // ---- route comparison overrides everything
            if (root.compare) {
                const palette = ["#e0455a", "#6fb3d9", "#d9a441", "#7fc47f", "#b08fd9"]
                root.compare.forEach((series, i) => {
                    strokeSeries(ctx, series.points, palette[i % palette.length], 2)
                    const ky = T + 14 + i * 15
                    ctx.fillStyle = palette[i % palette.length]
                    ctx.fillRect(L + W - 118, ky - 4, 10, 3)
                    ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.8)
                    ctx.font = "10px 'Oxygen', sans-serif"
                    ctx.fillText(series.route.replace(/_/g, " "), L + W - 104, ky - 2)
                })
                return
            }

            // ---- the curves
            const all = s.series
            for (const tr of all) {
                const pts = tr.active || mixed ? (mixed ? tr.rel : tr.points) : tr.points
                if (!pts || pts.length < 2) continue
                const col = mixed ? Qt.color(tr.color) : root.accent

                if (!mixed || tr.active) {
                    const grad = ctx.createLinearGradient(0, T, 0, T + H)
                    grad.addColorStop(0, Qt.rgba(col.r, col.g, col.b, mixed ? 0.22 : 0.4))
                    grad.addColorStop(1, Qt.rgba(col.r, col.g, col.b, 0.02))
                    ctx.fillStyle = grad
                    ctx.beginPath()
                    ctx.moveTo(root.xOf(pts[0][0]), T + H)
                    for (const p of pts) ctx.lineTo(root.xOf(p[0]), root.yOf(p[1]))
                    ctx.lineTo(root.xOf(pts[pts.length - 1][0]), T + H)
                    ctx.closePath(); ctx.fill()
                }
                strokeSeries(ctx, pts, Qt.lighter(col, 1.25), tr.active ? 2.2 : 1.5)

                // effect-site curve, dashed, when it lags meaningfully behind
                if (s.showEffect && tr.hasEffectLag && (tr.active || mixed)) {
                    const epts = mixed ? tr.effect
                               : tr.effect.map(p => [p[0], p[1] * (tr.points.length
                                    ? Math.max.apply(null, tr.points.map(q => q[1])) : 1)])
                    strokeSeries(ctx, epts, Qt.rgba(1, 1, 1, 0.45), 1.3, [5, 4])
                }
            }

            // ---- key when mixed
            if (mixed) {
                all.forEach((tr, i) => {
                    const ky = T + 13 + i * 14
                    ctx.fillStyle = tr.color
                    ctx.fillRect(L + W - 112, ky - 4, 10, 3)
                    ctx.font = "10px 'Oxygen', sans-serif"
                    ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, tr.active ? 0.95 : 0.6)
                    ctx.textAlign = "left"
                    ctx.fillText(tr.name, L + W - 98, ky - 2)
                })
            }

            // ---- dose markers for the active track
            const active = all[s.activeTrack] || all[0]
            for (const d of s.doses) {
                const x = root.xOf(d.time)
                if (x > L + W) continue
                ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.28)
                ctx.setLineDash([2, 3])
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(x, T + H); ctx.lineTo(x, T + H - 13); ctx.stroke()
                ctx.setLineDash([])
                ctx.fillStyle = mixed && active ? Qt.lighter(active.color, 1.3)
                                                : Qt.lighter(root.accent, 1.4)
                ctx.beginPath()
                ctx.moveTo(x, T + H - 15); ctx.lineTo(x - 4, T + H - 23)
                ctx.lineTo(x + 4, T + H - 23); ctx.closePath(); ctx.fill()
            }

            // ---- cursor
            const cx = root.xOf(s.cursor)
            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.5)
            ctx.lineWidth = 1
            ctx.beginPath(); ctx.moveTo(cx, T); ctx.lineTo(cx, T + H); ctx.stroke()

            let boxes = []
            for (const tr of all) {
                const pts = mixed ? tr.rel : tr.points
                if (!pts || !pts.length) continue
                // nearest sample to the cursor
                let best = pts[0], bd = 1e9
                for (const p of pts) {
                    const d = Math.abs(p[0] - s.cursor)
                    if (d < bd) { bd = d; best = p }
                }
                const cy = root.yOf(best[1])
                const col = mixed ? Qt.color(tr.color) : root.accent
                ctx.fillStyle = "#ffffff"
                ctx.beginPath(); ctx.arc(cx, cy, 3.5, 0, 2 * Math.PI); ctx.fill()
                ctx.strokeStyle = col; ctx.lineWidth = 2
                ctx.beginPath(); ctx.arc(cx, cy, 3.5, 0, 2 * Math.PI); ctx.stroke()
                if (tr.active) {
                    const v = mixed ? Math.round(best[1] * 100) + "% of peak"
                            : best[1].toFixed(best[1] < 0.1 ? 4 : best[1] < 10 ? 2 : 1)
                              + " " + tr.unit
                    boxes.push([v, col])
                }
            }
            if (boxes.length) {
                ctx.font = "11px 'JetBrains Mono'"
                const tw = ctx.measureText(boxes[0][0]).width + 14
                const bx = Math.min(Math.max(cx - tw / 2, L), L + W - tw)
                ctx.fillStyle = Qt.rgba(0, 0, 0, 0.8)
                ctx.strokeStyle = boxes[0][1]
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.roundedRect(bx, T + 1, tw, 20, 4, 4)
                ctx.fill(); ctx.stroke()
                ctx.fillStyle = "#ffffff"
                ctx.textAlign = "center"
                ctx.fillText(boxes[0][0], bx + tw / 2, T + 11)
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.CrossCursor
        onPositionChanged: (e) => { if (pressed || containsMouse) root.session.setCursor(root.tOf(e.x)) }
        onPressed: (e) => root.session.setCursor(root.tOf(e.x))
    }

    QQC2.Label {
        anchors { right: parent.right; bottom: parent.bottom; margins: 6 }
        visible: root.session.showEffect && root.session.series.some(t => t.hasEffectLag)
        text: "– – –  effect site (what the brain sees)"
        color: Qt.rgba(1, 1, 1, 0.45)
        font.pointSize: Kirigami.Theme.smallFont.pointSize
    }
}
