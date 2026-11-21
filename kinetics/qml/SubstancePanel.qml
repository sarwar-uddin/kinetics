import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// Searchable, category-grouped substance list. Clicking replaces the active
// track; the + button adds it alongside, which is how combinations are built.
ColumnLayout {
    id: panel
    required property var session
    property string filter: ""
    spacing: Kirigami.Units.smallSpacing

    function matches(s) {
        if (filter === "") return true
        const f = filter.toLowerCase()
        return s.name.toLowerCase().indexOf(f) >= 0
            || s["class"].toLowerCase().indexOf(f) >= 0
            || s.category.toLowerCase().indexOf(f) >= 0
    }

    Kirigami.SearchField {
        Layout.fillWidth: true
        Layout.margins: Kirigami.Units.smallSpacing
        placeholderText: "Search substances…"
        onTextChanged: panel.filter = text
    }

    Repeater {
        model: panel.session.categories
        delegate: ColumnLayout {
            id: catBlock
            required property string modelData
            readonly property var items: panel.session.substances.filter(
                s => s.category === modelData && panel.matches(s))
            Layout.fillWidth: true
            spacing: 1
            visible: items.length > 0

            QQC2.Label {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.smallSpacing
                Layout.topMargin: Kirigami.Units.smallSpacing
                text: catBlock.modelData
                font.bold: true
                font.capitalization: Font.AllUppercase
                font.letterSpacing: 1.1
                font.pointSize: Kirigami.Theme.smallFont.pointSize - 1
                opacity: 0.5
            }

            Repeater {
                model: catBlock.items
                delegate: QQC2.ItemDelegate {
                    id: row
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.smallSpacing
                    Layout.rightMargin: Kirigami.Units.smallSpacing
                    highlighted: panel.session.info.id === modelData.id
                    onClicked: panel.session.selectSubstance(modelData.id)
                    contentItem: RowLayout {
                        spacing: Kirigami.Units.smallSpacing
                        Rectangle {
                            width: 9; height: 9; radius: 4.5
                            color: row.modelData.color
                            border.color: Qt.rgba(1, 1, 1, 0.3)
                        }
                        ColumnLayout {
                            spacing: -2
                            Layout.fillWidth: true
                            QQC2.Label {
                                text: row.modelData.name
                                font.bold: true
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            QQC2.Label {
                                text: row.modelData["class"]
                                opacity: 0.5
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                font.pointSize: Kirigami.Theme.smallFont.pointSize - 1
                            }
                        }
                        QQC2.ToolButton {
                            icon.name: "list-add"
                            implicitWidth: 22; implicitHeight: 22
                            visible: row.hovered && panel.session.tracks.length < 6
                            opacity: 0.8
                            onClicked: panel.session.addTrack(row.modelData.id)
                            QQC2.ToolTip.text: "Add alongside — see the combination"
                            QQC2.ToolTip.visible: hovered
                            QQC2.ToolTip.delay: 400
                        }
                    }
                }
            }
        }
    }
}
