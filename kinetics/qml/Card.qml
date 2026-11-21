import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

Rectangle {
    id: card
    property string title
    property string subtitle
    property color accent: Kirigami.Theme.highlightColor
    default property alias content: body.data

    Layout.fillWidth: true
    implicitHeight: col.implicitHeight + Kirigami.Units.largeSpacing * 2
    radius: 6
    border.color: Qt.rgba(1, 1, 1, 0.09)
    gradient: Gradient {
        GradientStop { position: 0.0; color: Qt.lighter(Kirigami.Theme.backgroundColor, 1.32) }
        GradientStop { position: 0.14; color: Qt.lighter(Kirigami.Theme.backgroundColor, 1.10) }
        GradientStop { position: 1.0; color: Kirigami.Theme.backgroundColor }
    }

    ColumnLayout {
        id: col
        anchors { fill: parent; margins: Kirigami.Units.largeSpacing }
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            visible: card.title !== ""
            Rectangle { width: 3; height: t.height; radius: 1; color: card.accent }
            QQC2.Label {
                id: t
                text: card.title
                font.bold: true
                font.capitalization: Font.AllUppercase
                font.letterSpacing: 1.2
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                opacity: 0.85
            }
            Item { Layout.fillWidth: true }
            QQC2.Label {
                text: card.subtitle
                opacity: 0.55
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                elide: Text.ElideRight
                Layout.maximumWidth: card.width * 0.5
            }
        }
        ColumnLayout {
            id: body
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
        }
    }
}
