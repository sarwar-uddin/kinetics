import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// Concentration against time, with the dose markers, the effect bands and a
// draggable cursor. Drawn on a Canvas so the phases can be shaded directly.
Item {
    id: root
    required property var session
    property color accent: Kirigami.Theme.highlightColor
    property var compare: null          // [{route, points, ...}] when comparing

    readonly property real padL: 64
    readonly property real padR: 18
    readonly property real padT: 18
    readonly property real padB: 42
    readonly property real plotW: Math.max(10, width - padL - padR)
    readonly property real plotH: Math.max(10, height - padT - padB)
    property real yMax: 1

    function xOf(t) { return padL + t / Math.max(session.hours, 0.001) * plotW }
    function yOf(c) { return padT + plotH - Math.min(c / yMax, 1) * plotH }
    function tOf(x) { return Math.max(0, Math.min(session.hours,
                        (x - padL) / plotW * session.hours)) }

    function recomputeScale() {
        let curveTop = 0
        for (const p of session.series) curveTop = Math.max(curveTop, p[1])
        if (compare)
            for (const s of compare)
                for (const p of s.points) curveTop = Math.max(curveTop, p[1])

        // Include an effect line only if it sits just above the curve, and
        // compare against the *curve's* maximum — comparing against a running
        // total lets each level drag the next one into range, and the axis runs
        // away to the highest line on the list.
        let top = curveTop
        for (const lv of session.effectLevels)
            if (lv.y <= curveTop * 1.35) top = Math.max(top, lv.y * 1.02)

        yMax = top > 0 ? top * 1.14 : 1
        plot.requestPaint()
    }

    Connections {
        target: root.session
        function onCurveChanged() { root.recomputeScale() }
        function onCursorChanged() { plot.requestPaint() }
        function onDosesChanged() { plot.requestPaint() }
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

        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const s = root.session
            const L = root.padL, T = root.padT, W = root.plotW, H = root.plotH
            const fg = Kirigami.Theme.textColor

            // ---- grid
            ctx.font = "10px 'JetBrains Mono'"
            ctx.textBaseline = "middle"
            const yStep = niceStep(root.yMax, 5)
            ctx.textAlign = "right"
            for (let v = 0; v <= root.yMax; v += yStep) {
                const y = root.yOf(v)
                ctx.strokeStyle = Qt.rgba(1, 1, 1, v === 0 ? 0.22 : 0.07)
                ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + W, y); ctx.stroke()
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.55)
                ctx.fillText(v.toFixed(yStep < 0.01 ? 3 : yStep < 1 ? 2 : 0), L - 8, y)
            }
            const xStep = niceStep(s.hours, 8)
            ctx.textAlign = "center"
            for (let v = 0; v <= s.hours + 1e-9; v += xStep) {
                const x = root.xOf(v)
                ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.07)
                ctx.beginPath(); ctx.moveTo(x, T); ctx.lineTo(x, T + H); ctx.stroke()
                ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.55)
                ctx.fillText(v % 1 === 0 ? v + "h" : v.toFixed(1) + "h", x, T + H + 14)
            }

            // ---- effect level bands
            ctx.textAlign = "left"
            for (const lv of s.effectLevels) {
                if (lv.y > root.yMax) continue
                const y = root.yOf(lv.y)
                ctx.setLineDash([3, 4])
                ctx.strokeStyle = Qt.rgba(1, 0.85, 0.3, 0.35)
                ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(L + W, y); ctx.stroke()
                ctx.setLineDash([])
                ctx.fillStyle = Qt.rgba(1, 0.85, 0.3, 0.55)
                ctx.font = "9px 'Oxygen', sans-serif"
                ctx.fillText(lv.label, L + 6, y - 7)
                ctx.font = "10px 'JetBrains Mono'"
            }

            // ---- comparison curves (route comparison mode)
            if (root.compare) {
                const palette = ["#e0455a", "#6fb3d9", "#d9a441", "#7fc47f", "#b08fd9"]
                root.compare.forEach((series, i) => {
                    ctx.strokeStyle = palette[i % palette.length]
                    ctx.lineWidth = 2
                    ctx.beginPath()
                    series.points.forEach((p, j) => {
                        const x = root.xOf(p[0]), y = root.yOf(p[1])
                        if (j === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
                    })
                    ctx.stroke()
                    // key
                    const ky = T + 14 + i * 15
                    ctx.fillStyle = palette[i % palette.length]
                    ctx.fillRect(L + W - 112, ky - 4, 10, 3)
                    ctx.fillStyle = Qt.rgba(fg.r, fg.g, fg.b, 0.8)
                    ctx.font = "10px 'Oxygen', sans-serif"
                    ctx.fillText(series.route.replace(/_/g, " "), L + W - 98, ky - 2)
                    ctx.font = "10px 'JetBrains Mono'"
                })
                return
            }

            // ---- the curve, filled under
            const pts = s.series
            if (pts.length < 2) return
            const grad = ctx.createLinearGradient(0, T, 0, T + H)
            const col = root.accent
            grad.addColorStop(0, Qt.rgba(col.r, col.g, col.b, 0.42))
            grad.addColorStop(1, Qt.rgba(col.r, col.g, col.b, 0.02))
            ctx.fillStyle = grad
            ctx.beginPath()
            ctx.moveTo(root.xOf(pts[0][0]), T + H)
            for (const p of pts) ctx.lineTo(root.xOf(p[0]), root.yOf(p[1]))
            ctx.lineTo(root.xOf(pts[pts.length - 1][0]), T + H)
            ctx.closePath(); ctx.fill()

            ctx.strokeStyle = Qt.lighter(col, 1.25)
            ctx.lineWidth = 2
            ctx.lineJoin = "round"
            ctx.beginPath()
            pts.forEach((p, i) => {
                const x = root.xOf(p[0]), y = root.yOf(p[1])
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
            })
            ctx.stroke()

            // ---- dose markers
            for (const d of s.doses) {
                const x = root.xOf(d.time)
                if (x > L + W) continue
                ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.3)
                ctx.setLineDash([2, 3])
                ctx.beginPath(); ctx.moveTo(x, T + H); ctx.lineTo(x, T + H - 14); ctx.stroke()
                ctx.setLineDash([])
                ctx.fillStyle = Qt.lighter(col, 1.4)
                ctx.beginPath()
                ctx.moveTo(x, T + H - 16); ctx.lineTo(x - 4, T + H - 24)
                ctx.lineTo(x + 4, T + H - 24); ctx.closePath(); ctx.fill()
            }

            // ---- cursor
            const cx = root.xOf(s.cursor)
            const cv = s.cursorInfo.conc
            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.5)
            ctx.lineWidth = 1
            ctx.beginPath(); ctx.moveTo(cx, T); ctx.lineTo(cx, T + H); ctx.stroke()
            const cy = root.yOf(cv)
            ctx.fillStyle = "#ffffff"
            ctx.beginPath(); ctx.arc(cx, cy, 4, 0, 2 * Math.PI); ctx.fill()
            ctx.strokeStyle = col; ctx.lineWidth = 2
            ctx.beginPath(); ctx.arc(cx, cy, 4, 0, 2 * Math.PI); ctx.stroke()

            // readout box
            const label = cv.toFixed(cv < 0.1 ? 4 : cv < 10 ? 2 : 1) + " " + s.stats.unit
            ctx.font = "11px 'JetBrains Mono'"
            const tw = ctx.measureText(label).width + 14
            const bx = Math.min(Math.max(cx - tw / 2, L), L + W - tw)
            ctx.fillStyle = Qt.rgba(0, 0, 0, 0.78)
            ctx.strokeStyle = Qt.rgba(col.r, col.g, col.b, 0.9)
            ctx.lineWidth = 1
            ctx.beginPath(); ctx.roundedRect(bx, T + 2, tw, 20, 4, 4)
            ctx.fill(); ctx.stroke()
            ctx.fillStyle = "#ffffff"
            ctx.textAlign = "center"
            ctx.fillText(label, bx + tw / 2, T + 12)
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.CrossCursor
        onPositionChanged: (e) => { if (pressed || containsMouse) root.session.setCursor(root.tOf(e.x)) }
        onPressed: (e) => root.session.setCursor(root.tOf(e.x))
    }
}
