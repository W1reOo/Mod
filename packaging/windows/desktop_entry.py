"""Windowed entry point used by PyInstaller (never launches an external browser)."""
import ctypes
import logging
import os
import sys
from modmanager.__main__ import default_state, main


def report_failure(message):
    try:
        folder = default_state()
        folder.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=folder / 'desktop-error.log', encoding='utf-8', level=logging.ERROR)
        logging.exception('Desktop startup failed')
        message += f'\n\n错误日志：{folder / "desktop-error.log"}'
    except OSError:
        pass
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, message, 'ModHarbor · 启动失败', 0x10)
    elif sys.stderr:
        print(message, file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except SystemExit as exc:
        if exc.code:
            report_failure(str(exc.code))
    except Exception as exc:
        report_failure(
            f'无法启动 ModHarbor：{exc}\n\n'
            '请确认 Microsoft Edge WebView2 Runtime 已安装。\n'
            '官方下载：https://developer.microsoft.com/microsoft-edge/webview2/\n'
            '如提示另一实例正在运行，请先关闭已打开的 ModHarbor。'
        )
