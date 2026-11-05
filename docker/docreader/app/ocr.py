# -*- coding: utf-8 -*-
"""OCR скана: ocrmypdf + tesseract -> PDF с невидимым текстовым слоем (координаты слов сохраняются).
Настройки через переменные окружения: DOCREADER_OCR_DPI (300), DOCREADER_OCR_LANG (rus+eng),
DOCREADER_OCR_DESKEW (1), DOCREADER_OCR_CLEAN (1), DOCREADER_OCR_TIMEOUT (240 c)."""
import os
import shutil
import subprocess
import tempfile
import time


def settings() -> dict:
    return {"dpi": int(os.getenv("DOCREADER_OCR_DPI", "300")), "lang": os.getenv("DOCREADER_OCR_LANG", "rus+eng"),
            "deskew": os.getenv("DOCREADER_OCR_DESKEW", "1") == "1", "clean": os.getenv("DOCREADER_OCR_CLEAN", "1") == "1",
            "timeout": int(os.getenv("DOCREADER_OCR_TIMEOUT", "240"))}


def available() -> bool:
    return bool(shutil.which("ocrmypdf") and shutil.which("tesseract"))


def ocr_pdf(path: str, out_dir: str = None, **over) -> dict:
    """-> {ok, pdf, elapsed_s, settings, error}"""
    st = dict(settings(), **over)
    out_dir = out_dir or tempfile.mkdtemp(prefix="docreader_ocr_")
    out = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + f"__ocr{st['dpi']}.pdf")
    cmd = ["ocrmypdf", "-q", "-l", st["lang"], "--force-ocr", "--oversample", str(st["dpi"])]
    if st["deskew"]:
        cmd.append("--deskew")
    if st["clean"]:
        cmd.append("--clean")
    t0 = time.time()
    if not available():
        return {"ok": False, "pdf": "", "elapsed_s": 0, "settings": st, "error": "ocrmypdf/tesseract не установлены"}
    try:
        r = subprocess.run(cmd + [path, out], capture_output=True, text=True, timeout=st["timeout"])
        ok = r.returncode == 0 and os.path.exists(out)
        err = "" if ok else (r.stderr.strip()[-2000:] or f"код возврата {r.returncode}")
    except subprocess.TimeoutExpired:
        ok, err = False, f"OCR не уложился в {st['timeout']} с"
    return {"ok": ok, "pdf": out if ok else "", "elapsed_s": round(time.time() - t0, 1), "settings": st, "error": err}
