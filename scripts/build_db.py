#!/usr/bin/env python3
"""
Oxford Dictionary - MDX TXT to SQLite Converter
将解析后的 MDX 文本文件转换为 SQLite 数据库，支持快速搜索。
"""
import sqlite3
import os
import sys
import re
from tqdm import tqdm

# 路径配置
TXT_PATH = "/tmp/oxford_extract/牛津高阶英汉双解词典（第10版）V3.mdx.txt"
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "oxford.db")


def parse_txt_to_entries(txt_path):
    """解析 MDX TXT 文件，逐条生成 (word, html, is_link, link_target)"""
    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 每条记录以 </> 分隔
    records = content.split('</>\n')
    
    for record in tqdm(records, desc="解析词条"):
        record = record.strip()
        if not record:
            continue
        
        lines = record.split('\n', 1)
        if len(lines) < 1:
            continue
        
        word = lines[0].strip()
        rest = lines[1].strip() if len(lines) > 1 else ''
        
        if rest.startswith('@@@LINK='):
            # 这是一个链接/别名
            target = rest[len('@@@LINK='):].strip()
            yield (word, '', True, target)
        else:
            # 这是一个完整的词条
            yield (word, rest, False, '')


def build_database(txt_path, db_path):
    """构建 SQLite 数据库"""
    # 确保 data 目录存在
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # 删除已存在的数据库
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建主表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            html TEXT,
            is_link INTEGER DEFAULT 0,
            link_target TEXT
        )
    ''')
    
    # 创建索引 - 加速前缀搜索
    cursor.execute('CREATE INDEX idx_word ON entries(word)')
    
    # 启用 WAL 模式提升并发性能
    cursor.execute('PRAGMA journal_mode=WAL')
    
    # 批量插入
    batch = []
    batch_size = 1000
    
    for entry in parse_txt_to_entries(txt_path):
        word, html, is_link, link_target = entry
        batch.append((word, html, 1 if is_link else 0, link_target))
        
        if len(batch) >= batch_size:
            cursor.executemany(
                'INSERT INTO entries (word, html, is_link, link_target) VALUES (?, ?, ?, ?)',
                batch
            )
            batch = []
    
    # 插入剩余
    if batch:
        cursor.executemany(
            'INSERT INTO entries (word, html, is_link, link_target) VALUES (?, ?, ?, ?)',
            batch
        )
    
    conn.commit()
    
    # 统计
    cursor.execute('SELECT COUNT(*) FROM entries')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM entries WHERE is_link = 1')
    links = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n✅ 数据库构建完成!")
    print(f"   总词条: {total}")
    print(f"   别名/链接: {links}")
    print(f"   数据库大小: {os.path.getsize(db_path) / 1024 / 1024:.1f} MB")
    print(f"   位置: {db_path}")
    
    return total


if __name__ == '__main__':
    print("=" * 50)
    print("📖 牛津高阶英汉双解词典 - 数据库构建")
    print("=" * 50)
    print(f"\n📂 源文件: {TXT_PATH}")
    print(f"💾 目标数据库: {DB_PATH}")
    print()
    
    if not os.path.exists(TXT_PATH):
        print(f"❌ 源文件不存在: {TXT_PATH}")
        print("请先运行: mdict -x <mdx文件> -d /tmp/oxford_extract")
        sys.exit(1)
    
    total = build_database(TXT_PATH, DB_PATH)
    
    # 输出示例查询
    print("\n📝 查询示例:")
    print("   sqlite3 data/oxford.db \"SELECT word FROM entries WHERE word LIKE 'hello%' LIMIT 5\"")
