#!/usr/bin/env python3
"""
Oxford Dictionary Web Server
============================
基于 Python 内置 http.server，零依赖。
提供牛津高阶英汉双解词典的网页查询服务。

端口: 8310（自定义冷门端口）
"""

import http.server
import json
import os
import sqlite3
import urllib.parse
import html as html_mod

# ============================================================
# 配置
# ============================================================
PORT = 8310
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "oxford.db")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


class OxfordDictionaryHandler(http.server.SimpleHTTPRequestHandler):
    """牛津词典 HTTP 请求处理器"""

    def __init__(self, *args, **kwargs):
        # 设置静态文件目录为项目根目录（方便 index.html 等文件被直接访问）
        super().__init__(*args, directory=PROJECT_ROOT, **kwargs)

    def do_GET(self):
        """处理 GET 请求"""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # ---- API 路由 ----
        if path == '/api/search':
            self.handle_search(params)
        elif path == '/api/lookup':
            self.handle_lookup(params)
        elif path == '/api/suggest':
            self.handle_suggest(params)
        elif path.startswith('/data/') and path.endswith('.css'):
            self.serve_static_file(path, 'text/css')
        elif path.startswith('/data/') and path.endswith('.js'):
            self.serve_static_file(path, 'application/javascript')
        elif path == '/':
            self.serve_static_file('/index.html', 'text/html; charset=utf-8')
        else:
            super().do_GET()

    # ---- 数据库连接 ----
    def get_db(self):
        """获取数据库连接（每次请求独立连接，避免线程问题）"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- API: 搜索 ----
    def handle_search(self, params):
        """搜索词条 API: /api/search?q=xxx&limit=20"""
        query = params.get('q', [''])[0].strip().lower()
        limit = min(int(params.get('limit', ['20'])[0]), 100)

        if not query:
            self.send_json({'words': [], 'total': 0})
            return

        conn = self.get_db()
        cursor = conn.cursor()

        # 1. 精确匹配优先
        cursor.execute(
            'SELECT word, is_link, link_target FROM entries WHERE LOWER(word) = ? LIMIT 1',
            (query,)
        )
        exact = cursor.fetchone()

        # 2. 前缀匹配
        cursor.execute(
            '''SELECT word, is_link, link_target FROM entries 
               WHERE LOWER(word) LIKE ? AND LOWER(word) != ?
               ORDER BY LENGTH(word) ASC, word ASC 
               LIMIT ?''',
            (query + '%', query, limit + 1)
        )
        prefix_results = cursor.fetchall()

        conn.close()

        # 构建结果
        words = []
        seen = set()

        # 精确匹配放最前面
        if exact:
            words.append({
                'word': exact['word'],
                'is_link': bool(exact['is_link']),
                'link_target': exact['link_target']
            })
            seen.add(exact['word'].lower())

        # 添加前缀匹配
        for row in prefix_results:
            w = row['word']
            if w.lower() not in seen:
                words.append({
                    'word': w,
                    'is_link': bool(row['is_link']),
                    'link_target': row['link_target']
                })
                seen.add(w.lower())
                if len(words) >= limit:
                    break

        self.send_json({'words': words, 'total': len(words)})

    # ---- API: 查词 ----
    def handle_lookup(self, params):
        """查词 API: /api/lookup?word=hello"""
        word = params.get('word', [''])[0].strip().lower()

        if not word:
            self.send_json({'error': '请提供要查询的单词'}, status=400)
            return

        conn = self.get_db()
        cursor = conn.cursor()

        # 查找词条
        cursor.execute(
            'SELECT word, html, is_link, link_target FROM entries WHERE LOWER(word) = ?',
            (word,)
        )
        entry = cursor.fetchone()

        if not entry:
            conn.close()
            self.send_json({'error': f'未找到单词 "{word}"'}, status=404)
            return

        result = {
            'word': entry['word'],
            'html': entry['html'],
            'is_link': bool(entry['is_link']),
            'link_target': entry['link_target'],
        }

        # 如果是别名链接，查找目标词条
        if entry['is_link'] and entry['link_target']:
            target = entry['link_target'].strip()
            cursor.execute(
                'SELECT word, html FROM entries WHERE LOWER(word) = ? AND is_link = 0',
                (target.lower(),)
            )
            target_entry = cursor.fetchone()
            if target_entry:
                result['target_word'] = target_entry['word']
                result['html'] = target_entry['html']

        conn.close()

        # 处理 HTML 中的自定义链接
        if result['html']:
            result['html'] = self.process_entry_html(result['html'])

        self.send_json({'entry': result})

    # ---- API: 自动补全 ----
    def handle_suggest(self, params):
        """自动补全 API: /api/suggest?q=hel"""
        query = params.get('q', [''])[0].strip().lower()

        if not query or len(query) < 1:
            self.send_json({'suggestions': []})
            return

        conn = self.get_db()
        cursor = conn.cursor()

        cursor.execute(
            '''SELECT word FROM entries 
               WHERE LOWER(word) LIKE ? AND is_link = 0
               ORDER BY LENGTH(word) ASC, word ASC 
               LIMIT 10''',
            (query + '%',)
        )
        results = cursor.fetchall()
        conn.close()

        suggestions = [row['word'] for row in results]
        self.send_json({'suggestions': suggestions})

    # ---- 处理 HTML ----
    def process_entry_html(self, html):
        """处理词条 HTML，转换自定义链接为标准链接"""
        if not html:
            return html

        import re

        # 修正 CSS/JS 路径（原数据使用相对路径，需改为 /data/ 前缀）
        html = re.sub(
            r'href="oald10\.css"',
            r'href="/data/oald10.css"',
            html
        )
        html = re.sub(
            r'src="oald10\.js"',
            r'src="/data/oald10.js"',
            html
        )

        # 处理 entry:// 链接 -> #lookup=word
        html = re.sub(
            r'href="entry://([^"]+)"',
            r'href="#lookup=\1" class="entry-link"',
            html
        )

        # 处理 sound:// 链接 -> 替换为占位
        html = re.sub(
            r'href="sound://([^"]+)"',
            r'href="#" data-sound="\1" class="sound-link"',
            html
        )

        # 处理 <a href="#relatedentries"> 页面内锚点跳转
        html = re.sub(
            r'href="#([^"]+)"',
            r'href="#related-\1"',
            html
        )

        return html

    # ---- 静态文件服务 ----
    def serve_static_file(self, path, content_type):
        """服务静态文件"""
        file_path = os.path.join(PROJECT_ROOT, path.lstrip('/'))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'max-age=3600')
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404, 'File not found')

    # ---- 辅助：JSON 响应 ----
    def send_json(self, data, status=200):
        """发送 JSON 响应"""
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    # ---- 抑制无意义的日志 ----
    def log_message(self, format, *args):
        """自定义日志格式"""
        msg = format % args
        # 不记录静态文件请求
        if msg.startswith('"GET /data/') or msg.startswith('"GET /favicon'):
            return
        print(f"[{self.log_date_time_string()}] {msg}")


# ============================================================
# 启动服务
# ============================================================
def main():
    # 检查数据库
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库文件不存在: {DB_PATH}")
        print("请先运行: python3 scripts/build_db.py")
        return

    db_size = os.path.getsize(DB_PATH) / 1024 / 1024
    print(f"\n{'='*50}")
    print(f"📖 牛津高阶英汉双解词典 Web 版")
    print(f"{'='*50}")
    print(f"   数据库: {DB_PATH}")
    print(f"   数据库大小: {db_size:.1f} MB")
    print(f"   服务地址: http://localhost:{PORT}")
    print(f"   搜索示例: http://localhost:{PORT}/?q=hello")
    print(f"   按 Ctrl+C 停止服务")
    print(f"{'='*50}\n")

    server = http.server.HTTPServer(('127.0.0.1', PORT), OxfordDictionaryHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
        server.server_close()


if __name__ == '__main__':
    main()
