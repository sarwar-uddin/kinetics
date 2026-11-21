import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: win
    required property var session
    title: "Kinetics"
    width: 1600
    height: 960
    minimumWidth: 1050
    minimumHeight: 700

    readonly property color accent: session.info.color
    property bool compareMode: false
    property var compareData: null

    function refreshCompare() {
        compareData = compareMode ? session.compareRoutes() : null
    }
    onCompareModeChanged: refreshCompare()
    Connections {
        target: win.session
        function onSubstanceChanged() { win.refreshCompare() }
        function onPersonChanged() { win.refreshCompare() }
    }

    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.ToolBar
    pageStack.initialPage: Kirigami.Page {
        padding: 0
        title: win.session.info.name

        actions: [
            Kirigami.Action {
                icon.name: "office-chart-line-stacked"
                text: "Compare routes"
                checkable: true
                checked: win.compareMode
                visible: win.session.info.routes.length > 1
                onTriggered: win.compareMode = !win.compareMode
            },
            Kirigami.Action {
                icon.name: "user-identity"
                text: "Who's taking it"
                onTriggered: personSheet.open()
            },
            Kirigami.Action {
                icon.name: "documentinfo"
                text: "Sources"
                onTriggered: sourcesSheet.open()
            }
        ]

        RowLayout {
            anchors.fill: parent
            spacing: 0

            // ---------------- left: substance picker + doses ----------------
            QQC2.ScrollView {
                id: leftScroll
                Layout.preferredWidth: Kirigami.Units.gridUnit * 19
                Layout.minimumWidth: Kirigami.Units.gridUnit * 19
                Layout.maximumWidth: Kirigami.Units.gridUnit * 19
                Layout.fillHeight: true
                contentWidth: availableWidth
                QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

                ColumnLayout {
                    width: leftScroll.availableWidth
                    spacing: Kirigami.Units.smallSpacing

                    Item { implicitHeight: Kirigami.Units.smallSpacing }

                    Repeater {
                        model: win.session.substances
                        delegate: QQC2.ItemDelegate {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.smallSpacing
                            Layout.rightMargin: Kirigami.Units.smallSpacing
                            highlighted: win.session.substanceId === modelData.id
                            onClicked: win.session.selectSubstance(modelData.id)
                            contentItem: RowLayout {
                                spacing: Kirigami.Units.smallSpacing
                                Rectangle {
                                    width: 10; height: 10; radius: 5
                                    color: modelData.color
                                    border.color: Qt.rgba(1, 1, 1, 0.35)
                                }
                                ColumnLayout {
                                    spacing: 0
                                    Layout.fillWidth: true
                                    QQC2.Label { text: modelData.name; font.bold: true }
                                    QQC2.Label {
                                        text: modelData["class"]
                                        opacity: 0.55
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    }
                                }
                            }
                        }
                    }

                    Kirigami.Separator { Layout.fillWidth: true; Layout.margins: Kirigami.Units.smallSpacing }

                    DosePanel {
                        session: win.session
                        Layout.fillWidth: true
                        Layout.leftMargin: Kirigami.Units.smallSpacing
                        Layout.rightMargin: Kirigami.Units.smallSpacing
                    }

                    Item { implicitHeight: Kirigami.Units.largeSpacing }
                }
            }

            Kirigami.Separator { Layout.fillHeight: true }

            // ---------------- centre: the curve + the body ----------------
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: Kirigami.Units.gridUnit * 22
                Layout.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.largeSpacing

                CurveView {
                    id: curve
                    session: win.session
                    accent: win.accent
                    compare: win.compareData
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 240
                }

                // window + cursor controls
                RowLayout {
                    Layout.fillWidth: true
                    QQC2.Label {
                        text: "Window"
                        opacity: 0.6
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                    Repeater {
                        model: [["6 h", 6], ["12 h", 12], ["24 h", 24], ["48 h", 48], ["1 wk", 168]]
                        QQC2.Button {
                            required property var modelData
                            text: modelData[0]
                            flat: true
                            checkable: true
                            checked: Math.abs(win.session.hours - modelData[1]) < 0.01
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            onClicked: win.session.setHours(modelData[1])
                        }
                    }
                    Item { Layout.fillWidth: true }
                    QQC2.Label {
                        text: "+" + win.session.clock(win.session.cursor)
                        font.family: "JetBrains Mono"
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        opacity: 0.8
                    }
                    QQC2.Slider {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 120
                        Layout.maximumWidth: 260
                        from: 0; to: win.session.hours
                        value: win.session.cursor
                        onMoved: win.session.setCursor(value)
                    }
                }

                BodyView {
                    session: win.session
                    accent: win.accent
                    visible: !win.compareMode
                    Layout.fillWidth: true
                    Layout.preferredHeight: 248
                }

                // route comparison table
                Card {
                    visible: win.compareMode
                    title: "Same dose, different route"
                    subtitle: "why how you take it matters more than how much"
                    accent: win.accent
                    Layout.fillWidth: true
                    Repeater {
                        model: win.compareData || []
                        delegate: ColumnLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: 0
                            RowLayout {
                                Layout.fillWidth: true
                                Rectangle {
                                    width: 10; height: 3
                                    color: ["#e0455a", "#6fb3d9", "#d9a441", "#7fc47f", "#b08fd9"][index % 5]
                                }
                                QQC2.Label {
                                    text: modelData.route.replace(/_/g, " ")
                                    font.bold: true
                                    Layout.minimumWidth: 96
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                }
                                QQC2.Label {
                                    text: "peak " + modelData.cmax + " at +" + modelData.tmax
                                          + "  ·  " + modelData.f + " absorbed"
                                    font.family: "JetBrains Mono"
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    opacity: 0.8
                                }
                                Item { Layout.fillWidth: true }
                            }
                            QQC2.Label {
                                Layout.fillWidth: true
                                Layout.leftMargin: 20
                                Layout.bottomMargin: 6
                                text: modelData.note
                                wrapMode: Text.Wrap
                                opacity: 0.55
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                            }
                        }
                    }
                }
            }

            Kirigami.Separator { Layout.fillHeight: true }

            // ---------------- right: readings + explanation ----------------
            QQC2.ScrollView {
                id: rightScroll
                Layout.preferredWidth: Kirigami.Units.gridUnit * 22
                Layout.minimumWidth: Kirigami.Units.gridUnit * 22
                Layout.maximumWidth: Kirigami.Units.gridUnit * 22
                Layout.fillHeight: true
                contentWidth: availableWidth
                QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

                ColumnLayout {
                    width: rightScroll.availableWidth
                    spacing: Kirigami.Units.largeSpacing

                    Item { implicitHeight: 1 }

                    // at the cursor
                    Card {
                        Layout.leftMargin: Kirigami.Units.largeSpacing
                        Layout.rightMargin: Kirigami.Units.largeSpacing
                        title: "At +" + win.session.clock(win.session.cursor)
                        subtitle: win.session.cursorInfo.phase
                        accent: win.accent

                        RowLayout {
                            QQC2.Label {
                                text: {
                                    const c = win.session.cursorInfo.conc
                                    return c < 0.1 ? c.toFixed(4) : c < 10 ? c.toFixed(2) : c.toFixed(1)
                                }
                                font.family: "JetBrains Mono"
                                font.pointSize: 24
                                font.weight: Font.Light
                                color: win.accent
                            }
                            QQC2.Label {
                                text: win.session.stats.unit
                                opacity: 0.6
                                Layout.alignment: Qt.AlignBottom
                                Layout.bottomMargin: 6
                            }
                            Item { Layout.fillWidth: true }
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: win.session.cursorInfo.level
                            visible: text !== ""
                            wrapMode: Text.Wrap
                            color: "#e8c35a"
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: win.session.cursorInfo.text
                            wrapMode: Text.Wrap
                            opacity: 0.8
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                        KV {
                            key: "Absorbed"
                            value: win.session.cursorInfo.absorbedPct.toFixed(0) + "% of the dose"
                        }
                    }

                    // the numbers
                    Card {
                        Layout.leftMargin: Kirigami.Units.largeSpacing
                        Layout.rightMargin: Kirigami.Units.largeSpacing
                        title: "Pharmacokinetics"
                        accent: win.accent
                        KV { key: "Peak"; value: win.session.stats.cmax }
                        KV { key: "Time to peak"; value: "+" + win.session.stats.tmax }
                        KV { key: "Reaches blood"; value: win.session.stats.absorbedMg }
                        KV { key: "Half-life"; value: win.session.stats.halfLife }
                        KV { key: "Rate"; value: win.session.stats.clearRate }
                        KV {
                            key: "Down to half"
                            value: "+" + (win.session.stats.halfGone || "—")
                            visible: !win.session.stats.saturable
                        }
                        KV {
                            key: "Down to a quarter"
                            value: "+" + (win.session.stats.quarterLeft || "—")
                            visible: !win.session.stats.saturable
                        }
                        KV {
                            key: "Essentially gone"
                            value: win.session.stats.practicallyGone || ""
                            visible: !win.session.stats.saturable
                            mono: false
                        }
                        KV {
                            key: "Back to zero"
                            value: "+" + (win.session.stats.backToZero || "—")
                            visible: !!win.session.stats.saturable
                        }
                        KV { key: "Distribution"; value: win.session.stats.vd }
                        KV { key: "Total exposure"; value: win.session.stats.auc }

                        QQC2.Label {
                            Layout.fillWidth: true
                            Layout.topMargin: 4
                            visible: !!win.session.stats.flipFlop
                            text: win.session.stats.flipFlop || ""
                            wrapMode: Text.Wrap
                            color: "#e8c35a"
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            Layout.topMargin: 4
                            visible: !!win.session.stats.saturable
                            text: win.session.info.eliminationNote
                            wrapMode: Text.Wrap
                            opacity: 0.7
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                    }

                    // personal factors in play
                    Card {
                        Layout.leftMargin: Kirigami.Units.largeSpacing
                        Layout.rightMargin: Kirigami.Units.largeSpacing
                        title: "Your factors"
                        subtitle: win.session.activeFactors.length === 0 ? "none set" : ""
                        accent: "#d9a441"
                        visible: win.session.activeFactors.length > 0
                        Repeater {
                            model: win.session.activeFactors
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 1
                                QQC2.Label {
                                    text: "● " + modelData.name
                                    font.bold: true
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                }
                                QQC2.Label {
                                    Layout.fillWidth: true
                                    Layout.bottomMargin: 4
                                    text: modelData.note
                                    wrapMode: Text.Wrap
                                    opacity: 0.7
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                }
                            }
                        }
                    }

                    // what it does and where it goes
                    Card {
                        Layout.leftMargin: Kirigami.Units.largeSpacing
                        Layout.rightMargin: Kirigami.Units.largeSpacing
                        title: win.session.info.name
                        subtitle: win.session.info.formula
                        accent: win.accent
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: win.session.info.summary
                            wrapMode: Text.Wrap
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                        Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: 4; opacity: 0.4 }
                        QQC2.Label {
                            text: "How it acts"
                            font.bold: true
                            opacity: 0.75
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: win.session.info.mechanism
                            wrapMode: Text.Wrap
                            opacity: 0.8
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                        }
                    }

                    // metabolic pathways
                    Card {
                        Layout.leftMargin: Kirigami.Units.largeSpacing
                        Layout.rightMargin: Kirigami.Units.largeSpacing
                        title: "Breakdown"
                        subtitle: "via " + win.session.info.enzyme
                        accent: win.accent
                        Repeater {
                            model: win.session.info.pathways
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 1
                                RowLayout {
                                    Layout.fillWidth: true
                                    QQC2.Label {
                                        text: modelData.name
                                        font.bold: true
                                        color: modelData.danger ? "#e0455a" : Kirigami.Theme.textColor
                                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    }
                                    QQC2.Label {
                                        visible: !!modelData.active
                                        text: modelData.danger ? "reactive" : "active"
                                        color: modelData.danger ? "#e0455a" : "#d9a441"
                                        font.pointSize: Kirigami.Theme.smallFont.pointSize - 1
                                    }
                                    Item { Layout.fillWidth: true }
                                    QQC2.Label {
                                        text: Math.round(modelData.fraction * 100) + "%"
                                        font.family: "JetBrains Mono"
                                        opacity: 0.7
                                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    }
                                }
                                QQC2.Label {
                                    Layout.fillWidth: true
                                    Layout.bottomMargin: 5
                                    text: modelData.note
                                    wrapMode: Text.Wrap
                                    opacity: 0.65
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                }
                            }
                        }
                    }

                    Item { implicitHeight: Kirigami.Units.largeSpacing }
                }
            }
        }
    }

    // ------------------------------------------------------------- sheets
    Kirigami.OverlaySheet {
        id: personSheet
        title: "Who's taking it"
        parent: win.QQC2.Overlay.overlay

        ColumnLayout {
            spacing: Kirigami.Units.largeSpacing

            QQC2.Label {
                Layout.fillWidth: true
                Layout.maximumWidth: 460
                text: "The same dose behaves differently in different people. These are the factors with well-documented effects on the substances here."
                wrapMode: Text.Wrap
                opacity: 0.7
            }

            RowLayout {
                QQC2.Label { text: "Body weight"; Layout.minimumWidth: 140 }
                QQC2.SpinBox {
                    from: 30; to: 200
                    value: win.session.person.weight
                    onValueModified: win.session.setPersonField("weight", value)
                }
                QQC2.Label { text: "kg"; opacity: 0.6 }
            }

            RowLayout {
                QQC2.Label { text: "Body-water fraction"; Layout.minimumWidth: 140 }
                QQC2.ComboBox {
                    model: ["male", "female"]
                    currentIndex: win.session.person.sex === "female" ? 1 : 0
                    onActivated: win.session.setPersonField("sex", currentIndex === 1 ? "female" : "male")
                }
                QQC2.Label {
                    text: "affects alcohol only"
                    opacity: 0.5
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                }
            }

            QQC2.CheckBox {
                text: "Smoker — induces CYP1A2, clears caffeine about twice as fast"
                checked: win.session.person.smoker
                onToggled: win.session.setPersonField("smoker", checked)
            }
            QQC2.CheckBox {
                text: "Regular heavy drinking — induces CYP2E1 (alcohol, paracetamol)"
                checked: win.session.person.chronicAlcohol
                onToggled: win.session.setPersonField("chronicAlcohol", checked)
            }
            QQC2.CheckBox {
                text: "Oral contraceptives — inhibits CYP1A2, roughly doubles caffeine half-life"
                checked: win.session.person.oralContraceptives
                onToggled: win.session.setPersonField("oralContraceptives", checked)
            }
            RowLayout {
                QQC2.Label { text: "CYP2A6 (nicotine)"; Layout.minimumWidth: 140 }
                QQC2.ComboBox {
                    model: ["slow", "normal", "fast"]
                    currentIndex: ["slow", "normal", "fast"].indexOf(win.session.person.cyp2a6)
                    onActivated: win.session.setPersonField("cyp2a6", model[currentIndex])
                }
            }

            QQC2.Label {
                Layout.fillWidth: true
                Layout.maximumWidth: 460
                text: "Saved to ~/.config/kinetics/person.json. These shift the curve by the multipliers reported in the cited literature; they are population averages, and real variation between individuals is wider than any of them."
                wrapMode: Text.Wrap
                opacity: 0.55
                font.pointSize: Kirigami.Theme.smallFont.pointSize
            }
        }
    }

    Kirigami.OverlaySheet {
        id: sourcesSheet
        title: "Where the numbers come from"
        parent: win.QQC2.Overlay.overlay

        ColumnLayout {
            spacing: Kirigami.Units.largeSpacing

            QQC2.Label {
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                text: "Every parameter for " + win.session.info.name + " is taken from the following. Values are population means; the published ranges are wider."
                wrapMode: Text.Wrap
                opacity: 0.7
            }
            Repeater {
                model: win.session.info.sources
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.maximumWidth: 560
                    spacing: 1
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: modelData.text
                        wrapMode: Text.Wrap
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                    QQC2.Label {
                        text: "used for: " + modelData["for"]
                        opacity: 0.55
                        font.italic: true
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                }
            }
            Kirigami.Separator { Layout.fillWidth: true }
            QQC2.Label {
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                text: "This is a teaching model, not a clinical tool. It uses one- or two-compartment kinetics with population-average parameters, so it shows the shape of what happens — not what will happen to any particular person."
                wrapMode: Text.Wrap
                opacity: 0.6
                font.pointSize: Kirigami.Theme.smallFont.pointSize
            }
        }
    }
}
