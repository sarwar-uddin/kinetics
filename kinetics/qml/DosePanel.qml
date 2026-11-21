import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// Build the intake schedule: presets, a custom amount, and the list of what's
// been added with the time each was taken.
ColumnLayout {
    id: panel
    required property var session
    spacing: Kirigami.Units.smallSpacing

    Card {
        title: "Intake"
        subtitle: panel.session.doses.length + (panel.session.doses.length === 1 ? " dose" : " doses")
        accent: panel.session.info.color

        // route
        RowLayout {
            Layout.fillWidth: true
            visible: panel.session.info.routes.length > 1
            QQC2.Label { text: "Route"; opacity: 0.6; Layout.minimumWidth: 46
                         font.pointSize: Kirigami.Theme.smallFont.pointSize }
            QQC2.ComboBox {
                Layout.fillWidth: true
                model: panel.session.info.routes
                currentIndex: Math.max(0, panel.session.info.routes.indexOf(panel.session.info.route))
                onActivated: panel.session.setRoute(panel.session.info.routes[currentIndex])
                displayText: currentText.replace(/_/g, " ")
                delegate: QQC2.ItemDelegate {
                    required property var modelData
                    width: parent ? parent.width : 0
                    text: modelData.replace(/_/g, " ")
                }
            }
        }

        QQC2.Label {
            Layout.fillWidth: true
            text: panel.session.info.routeNote
            wrapMode: Text.Wrap
            opacity: 0.6
            font.pointSize: Kirigami.Theme.smallFont.pointSize
        }

        Kirigami.Separator { Layout.fillWidth: true; opacity: 0.4 }

        // presets
        QQC2.Label { text: "Add at " + timeField.text + " h:"; opacity: 0.6
                     font.pointSize: Kirigami.Theme.smallFont.pointSize }
        Flow {
            Layout.fillWidth: true
            spacing: 4
            Repeater {
                model: panel.session.info.presets
                QQC2.Button {
                    required property var modelData
                    text: modelData.label
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    onClicked: {
                        if (modelData.route && modelData.route !== panel.session.info.route)
                            panel.session.setRoute(modelData.route)
                        panel.session.addDose(parseFloat(timeField.text) || 0,
                                              modelData.mg, modelData.label)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            QQC2.Label { text: "at"; opacity: 0.6
                         font.pointSize: Kirigami.Theme.smallFont.pointSize }
            QQC2.TextField {
                id: timeField
                text: "0"
                Layout.preferredWidth: 52
                horizontalAlignment: Text.AlignRight
                validator: DoubleValidator { bottom: 0; top: 168 }
            }
            QQC2.Label { text: "h  ·  custom"; opacity: 0.6
                         font.pointSize: Kirigami.Theme.smallFont.pointSize }
            QQC2.TextField {
                id: amountField
                Layout.fillWidth: true
                placeholderText: "mg"
                horizontalAlignment: Text.AlignRight
                validator: DoubleValidator { bottom: 0 }
                onAccepted: addBtn.clicked()
            }
            QQC2.Button {
                id: addBtn
                text: "Add"
                enabled: parseFloat(amountField.text) > 0
                onClicked: {
                    panel.session.addDose(parseFloat(timeField.text) || 0,
                                          parseFloat(amountField.text), "")
                    amountField.clear()
                }
            }
        }
    }

    Card {
        title: "Schedule"
        accent: panel.session.info.color
        visible: panel.session.doses.length > 0

        Repeater {
            model: panel.session.doses
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                QQC2.Label {
                    text: "+" + modelData.clock
                    font.family: "JetBrains Mono"
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    opacity: 0.7
                    Layout.minimumWidth: 58
                }
                QQC2.Label {
                    Layout.fillWidth: true
                    text: modelData.label
                    elide: Text.ElideRight
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                }
                QQC2.Label {
                    text: modelData.amount >= 1000
                          ? (modelData.amount / 1000).toFixed(1) + " g"
                          : modelData.amount + " mg"
                    font.family: "JetBrains Mono"
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    opacity: 0.8
                }
                QQC2.ToolButton {
                    icon.name: "edit-delete-remove"
                    implicitWidth: 24; implicitHeight: 24
                    onClicked: panel.session.removeDose(modelData.index)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            QQC2.Button {
                text: "Clear"
                icon.name: "edit-clear-all"
                flat: true
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                onClicked: panel.session.clearDoses()
            }
            Item { Layout.fillWidth: true }
            QQC2.Label {
                text: "repeat"
                opacity: 0.6
                font.pointSize: Kirigami.Theme.smallFont.pointSize
            }
            QQC2.ComboBox {
                id: repeatEvery
                Layout.preferredWidth: 74
                model: ["4 h", "6 h", "8 h", "12 h", "24 h"]
                currentIndex: 4
                font.pointSize: Kirigami.Theme.smallFont.pointSize
            }
            QQC2.SpinBox {
                id: repeatTimes
                from: 1; to: 30
                value: 6
                Layout.preferredWidth: 90
            }
            QQC2.Button {
                text: "Add"
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                onClicked: panel.session.repeatDose(
                    parseFloat(repeatEvery.currentText), repeatTimes.value,
                    panel.session.doses.length ? panel.session.doses[0].amount : 0)
                QQC2.ToolTip.text: "Repeat the first dose on a schedule — shows accumulation"
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: 400
            }
        }
    }
}
