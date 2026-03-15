#!/usr/bin/env python3
"""
Smart Notes API - 动态加载笔记
提供 /api/notes 接口，扫描 notes/ 目录返回所有笔记
"""

import os
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

NOTES_DIR = Path(__file__).parent / "notes"

class NotesAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/notes':
            self.serve_notes_list()
        elif parsed.path == '/api/note':
            # 获取单个笔记内容
            query = parse_qs(parsed.query)
            path = query.get('path', [None])[0]
            if path:
                self.serve_note_content(path)
            else:
                self.send_error(400, "Missing path parameter")
        else:
            self.send_error(404)
    
    def serve_notes_list(self):
        """返回所有笔记的元数据列表"""
        notes = []
        
        # 递归扫描 notes/ 目录
        for md_file in NOTES_DIR.rglob("*.md"):
            rel_path = md_file.relative_to(NOTES_DIR.parent)
            
            # 推断分类（根据目录结构）
            parts = md_file.relative_to(NOTES_DIR).parts
            if len(parts) > 1:
                category = parts[0]  # 第一级目录作为分类
            else:
                category = "uncategorized"
            
            # 读取内容（用于搜索和预览）
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except:
                content = ""
            
            notes.append({
                "name": md_file.stem,  # 文件名（不含扩展名）
                "path": str(rel_path),
                "category": category,
                "content": content
            })
        
        # 返回JSON
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(notes, ensure_ascii=False).encode('utf-8'))
    
    def serve_note_content(self, path):
        """返回单个笔记的内容"""
        note_path = NOTES_DIR.parent / path
        
        if not note_path.exists() or not note_path.is_file():
            self.send_error(404, "Note not found")
            return
        
        try:
            with open(note_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except Exception as e:
            self.send_error(500, str(e))
    
    def log_message(self, format, *args):
        # 静默日志
        pass

def run_server(port=9877):
    server = HTTPServer(('0.0.0.0', port), NotesAPIHandler)
    print(f"Smart Notes API running on http://localhost:{port}")
    print(f"Notes directory: {NOTES_DIR}")
    server.serve_forever()

if __name__ == '__main__':
    run_server()
