# -*- coding: utf-8 -*-
"""教伴 —— 教学办公助手程序入口。"""

import os
import sys
import traceback

from PyQt5.QtCore import QCoreApplication, Qt
from PyQt5.QtWidgets import QApplication

from app.config import APP_NAME, load_config
from app.ui.first_run_dialog import FirstRunDialog
from app.ui.main_window import MainWindow
from app.ui.styles import MAIN_STYLE


def configure_win7_runtime() -> None:
    """在创建 QApplication 前启用 Windows 7 可用的显示兼容设置。"""
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    # 老显卡驱动和远程桌面环境下优先稳定性，避免 OpenGL 白屏或崩溃。
    os.environ.setdefault("QT_OPENGL", "software")
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if hasattr(Qt, "AA_UseSoftwareOpenGL"):
        QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)


def log_exception(exc_type, exc_value, exc_traceback) -> None:
    """把未捕获异常写入本机日志，便于在没有开发环境的电脑上反馈问题。"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    try:
        from app.config import data_dir
        path = os.path.join(data_dir(), "error.log")
        with open(path, "a", encoding="utf-8") as handle:
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=handle)
    except Exception:
        pass


def main() -> int:
    sys.excepthook = log_exception
    configure_win7_runtime()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(MAIN_STYLE)
    if not load_config().get("first_run_done", False):
        FirstRunDialog().exec_()
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
