import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

RowLayout {
    property alias key: k.text
    property alias value: v.text
    property bool mono: true
    Layout.fillWidth: true
    QQC2.Label {
        id: k
        opacity: 0.6
        Layout.minimumWidth: 88
        Layout.maximumWidth: 112
        wrapMode: Text.Wrap
        Layout.alignment: Qt.AlignTop
        font.pointSize: Kirigami.Theme.smallFont.pointSize
    }
    QQC2.Label {
        id: v
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        horizontalAlignment: Text.AlignRight
        wrapMode: Text.Wrap
        font.family: mono ? "JetBrains Mono" : Kirigami.Theme.defaultFont.family
        font.pointSize: Kirigami.Theme.smallFont.pointSize
    }
}
