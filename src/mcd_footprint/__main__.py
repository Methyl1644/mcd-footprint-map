#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""允许 `python -m mcd_footprint` 直接运行。"""
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcd_footprint.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
