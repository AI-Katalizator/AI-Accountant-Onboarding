# -*- coding: utf-8 -*-
# Портировано из ScanReader (MIT, (c) 2026 ScanReader Contributors,
# https://github.com/Riper21/ScanReader, src/scan_reader/core/utils.py).
# Изменения: оставлены только get_logger (упрощён) и coerce_to_str.
import logging
import os
import sys
from typing import Any


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
        logger.propagate = False
        logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
    return logger


def coerce_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, bool):
        return "Да" if v else "Нет"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return ", ".join(coerce_to_str(x) for x in v if x is not None and str(x).strip())
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            if val is not None and str(val).strip():
                parts.append(f"{k}: {coerce_to_str(val) if isinstance(val, (dict, list)) else str(val).strip()}")
        return "; ".join(parts)
    return str(v).strip()
