#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Factor Forge API 服务器
========================
连接前端 index.html 与后端蒸馏/存储逻辑。纯标准库，无 Flask 依赖。

路由:
  POST   /api/forge          multipart: pdf 或 text + source + no_advice → 蒸馏因子(不入库)
  GET    /api/factors        → 全部因子
  POST   /api/factors        json: {factors:[...]} → 批量入库
  PATCH  /api/factors/<id>   json: patch → 更新单条
  DELETE /api/factors/<id>   → 删除单条

启动: /opt/homebrew/bin/python3 server.py   (默认端口 7788)
"""
from __future__ import annotations
import sys, json, tempfile, os, traceback, email
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path("/Users/apple/Desktop/gamt-dashboard/factor-forge")
sys.path.insert(0, str(BASE))
import forge, store  # noqa: E402

PORT = 7788


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音默认日志
        sys.stderr.write("[api] " + (a[0] % a[1:]) + "\n")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path.rstrip("/") == "/api/factors":
            return self._json(200, store.all_factors())
        if self.path in ("/", "/index.html"):
            return self._serve_file(BASE / "index.html", "text/html")
        self._json(404, {"error": "not found"})

    def _serve_file(self, path, ctype):
        if not path.exists():
            return self._json(404, {"error": "file not found"})
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            if self.path.rstrip("/") == "/api/forge":
                return self._handle_forge()
            if self.path.rstrip("/") == "/api/factors":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                r = store.add_factors(payload.get("factors", []))
                return self._json(200, r)
            self._json(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            self._json(500, {"error": str(e)})

    def _parse_multipart(self):
        """用标准库 email 模块解析 multipart/form-data（Py3.13+ 无 cgi）。
        返回 {field_name: value_or_dict}。文件字段为 {'filename':..., 'data':bytes}。"""
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        # 构造一个完整 MIME 消息交给 email 解析
        header = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        msg = email.message_from_bytes(header + body)
        fields = {}
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = part.get("Content-Disposition", "")
            if "form-data" not in disp:
                continue
            name = part.get_param("name", header="Content-Disposition")
            filename = part.get_param("filename", header="Content-Disposition")
            payload = part.get_payload(decode=True)
            if filename:
                fields[name] = {"filename": filename, "data": payload or b""}
            else:
                fields[name] = (payload or b"").decode("utf-8", "replace")
        return fields

    def _handle_forge(self):
        form = self._parse_multipart()
        source = form.get("source", "") or ""
        no_advice = bool(form.get("no_advice", ""))
        text = form.get("text", "") or ""

        # PDF 优先
        pdf_field = form.get("pdf")
        if isinstance(pdf_field, dict) and pdf_field.get("data"):
            from extract_pdf import extract_pdf
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(pdf_field["data"])
                tmp = tf.name
            try:
                res = extract_pdf(tmp)
                text = res["text"]
                if not source:
                    source = Path(pdf_field["filename"]).stem
            finally:
                os.unlink(tmp)

        if len(text.strip()) < 100:
            return self._json(400, {"error": "正文太短或抽取失败（PDF 可能是扫描件，请粘贴正文）"})

        factors = forge.forge(text, source_hint=source, with_advice=not no_advice)
        self._json(200, {"factors": factors, "source": source})

    def do_PATCH(self):
        try:
            fid = self.path.rsplit("/", 1)[-1]
            length = int(self.headers.get("Content-Length", 0))
            patch = json.loads(self.rfile.read(length) or b"{}")
            ok = store.update_factor(fid, patch)
            self._json(200 if ok else 404, {"ok": ok})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def do_DELETE(self):
        fid = self.path.rsplit("/", 1)[-1]
        ok = store.delete_factor(fid)
        self._json(200 if ok else 404, {"ok": ok})


if __name__ == "__main__":
    print(f"Factor Forge API → http://localhost:{PORT}")
    print(f"前端 → http://localhost:{PORT}/index.html")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
