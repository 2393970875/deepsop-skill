# -*- coding: utf-8 -*-
"""
竞品调研框架构建 - 全流程快速启动脚本
用法： uv run python scripts/run_all.py
"""

import shutil, os, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = r'C:\Users\胡康杰\Desktop'
IMG_DIR = os.path.join(WORK_DIR, '竞品调研脚本', 'product_imgs')
ORIG_FILE = os.path.join(WORK_DIR, '0613-竞品调研.xlsx')
OUTPUT_FILE = os.path.join(WORK_DIR, '竞品调研框架.xlsx')

steps = []

def run_step(name, script_path, *args):
    print(f'\n{"="*60}')
    print(f'  [步骤] {name}')
    print(f'  [脚本] {script_path}')
    print(f'{"="*60}')
    ret = os.system(f'cd /d "{SCRIPT_DIR}" && uv run python "{script_path}" {" ".join(args)}')
    if ret != 0:
        print(f'  ❌ 步骤失败: {name}')
        return False
    print(f'  ✅ 完成: {name}')
    return True

if __name__ == '__main__':
    print('''
    ╔══════════════════════════════════════╗
    ║    竞品调研框架构建 - 全流程        ║
    ╚══════════════════════════════════════╝
    ''')
    
    if not os.path.exists(ORIG_FILE):
        print(f'❌ 原始文件不存在: {ORIG_FILE}')
        sys.exit(1)
    
    print(f'原始文件: {ORIG_FILE}')
    print(f'输出文件: {OUTPUT_FILE}')
    print(f'图片目录: {IMG_DIR}')
    
    # 各步骤可按需取消注释执行
    print('''
    步骤列表:
    1. 重建Sheet4（关键词排名现状）框架
    2. 重建Sheet5~6（行业爆文分析+爆文拆解）框架  
    3. 从Sheet2填充Sheet3参数
    4. 嵌入商品图片
    5. 升级商品链接
    6. 修正缺参数商品
    7. 调整Sheet顺序
    8. 重建Sheet3精确样式
    
    请手动按顺序执行: uv run python scripts/<脚本名>
    ''')
