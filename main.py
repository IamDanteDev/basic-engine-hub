import sys

from PySide6.QtWidgets import QApplication

from hub.gui import Hub


def main() -> None:
    app = QApplication(sys.argv)
    window = Hub()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()