# -*- coding: utf-8 -*-
"""HTTP API для n8n (только стандартная библиотека Python).

GET  /health                       -> {"ok": true, ...}
POST /read  {"path": "...", "vision": "auto|never|always", "model": "..."}  -> карточка документа

path — путь к PDF так, как его видит n8n. Разрешены только файлы внутри FILES_ROOTS.
PATH_MAP="/n8n/path=/local/path;..." переводит пути n8n в пути этого контейнера (если смонтировано иначе).
"""
import json
import os
import sys
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import reader  # noqa: E402
from app import vision  # noqa: E402

PORT = int(os.getenv("PORT", "8011"))
ROOTS = [os.path.realpath(p) for p in os.getenv("FILES_ROOTS", "/files").split(";") if p]
PATH_MAP = [tuple(x.split("=", 1)) for x in os.getenv("PATH_MAP", "").split(";") if "=" in x]


def resolve(p: str) -> str:
    for src, dst in PATH_MAP:
        if p.startswith(src):
            p = dst + p[len(src):]
    rp = os.path.realpath(p)
    if not any(rp == r or rp.startswith(r + os.sep) for r in ROOTS):
        raise PermissionError(f"путь вне разрешённых папок: {p}")
    if not os.path.isfile(rp):
        raise FileNotFoundError(f"файл не найден: {p}")
    return rp


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            ok = None
            try:
                with urllib.request.urlopen(vision.OLLAMA_URL.rstrip("/") + "/api/tags", timeout=3) as r:
                    tags = [m.get("name") for m in json.loads(r.read().decode()).get("models", [])]
                ok = vision.MODEL in tags or (vision.MODEL + ":latest") in tags
            except Exception:
                tags = None
            self._send(200, {"ok": True, "version": reader.VERSION, "files_roots": ROOTS,
                             "vision_model": vision.MODEL, "ollama_url": vision.OLLAMA_URL,
                             "ollama_reachable": tags is not None, "vision_model_present": ok,
                             "ocr_available": __import__("app.ocr", fromlist=["x"]).available(),
                             "ocr_settings": __import__("app.ocr", fromlist=["x"]).settings(),
                             "scan_mode": os.getenv("DOCREADER_SCAN_MODE", "ocr")})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.split("?")[0] != "/read":
            return self._send(404, {"ok": False, "error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            path = resolve(str(req.get("path", "")))
            mode = str(req.get("vision", "auto"))
            if mode not in ("auto", "never", "always"):
                mode = "auto"
            card = reader.read(path, vision=mode, model=req.get("model") or None, scan=req.get("scan") or None,
                               our_inn=str(req.get("our_inn") or "") or None)
            if req.get("merge_xlsx_b64") and card.get("merge"):
                # папка файлов смонтирована только на чтение — Excel «Способ 1/2/Итог/Почему» отдаём base64
                import base64, tempfile
                from app import merge as M
                fd, tmp = tempfile.mkstemp(suffix=".xlsx")
                os.close(fd)
                M.write_xlsx(card, tmp)
                card["merge_xlsx_b64"] = base64.b64encode(open(tmp, "rb").read()).decode()
                os.unlink(tmp)
            if not req.get("include_text", True):
                card.pop("doc_text", None)
            card["ok"] = True
            card["file"] = os.path.basename(path)
            self._send(200, card)
        except (PermissionError, FileNotFoundError) as e:
            self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):
        sys.stderr.write("[docreader] " + (fmt % args) + "\n")


if __name__ == "__main__":
    print(f"docreader {reader.VERSION} on :{PORT}, roots={ROOTS}, model={vision.MODEL}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
