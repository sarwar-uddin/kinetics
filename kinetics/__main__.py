import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

from .session import Session

HERE = Path(__file__).resolve().parent


def main() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("kinetics")
    app.setApplicationDisplayName("Kinetics")
    app.setDesktopFileName("io.github.sarwar_uddin.Kinetics")
    app.setWindowIcon(QIcon.fromTheme("io.github.sarwar_uddin.Kinetics",
                                      QIcon.fromTheme("applications-science")))
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    session = Session()
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"session": session})
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
