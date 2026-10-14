# -*- coding: utf-8 -*-
"""WebGL 崩溃栈符号解析工具入口(打包入口)。"""
import sys

from gui import run_gui


def main() -> int:
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
