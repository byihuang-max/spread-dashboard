#!/usr/bin/env python3
"""
火富牛数据抓取 - 简易版
手动操作 + 自动保存
"""

import json
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

FUND_ID = "4f3027afbe1adcf3"
BASE_URL = "https://mp.fof99.com"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        print("="*60)
        print("火富牛数据抓取工具")
        print("="*60)
        print(f"基金ID: {FUND_ID}")
        print("\n使用方法:")
        print("1. 浏览器会自动打开火富牛")
        print("2. 请手动: 登录 -> 找到基金 -> 选择周报 -> 点击分析")
        print("3. 看到数据后，在终端按回车保存数据")
        print("="*60)
        
        page.goto(f"{BASE_URL}/fund/view/{FUND_ID}")
        
        print("\n请在浏览器中操作，完成后按回车...")
        input()
        
        # 等待一下让动画完成
        page.wait_for_timeout(2000)
        
        # 截图
        screenshot_file = f"fund_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        page.screenshot(path=screenshot_file, full_page=True)
        print(f"\n截图保存: {screenshot_file}")
        
        # 获取页面文本
        page_text = page.evaluate("document.body.innerText")
        
        # 提取关键数据
        lines = page_text.split('\n')
        clean_lines = [l.strip() for l in lines if l.strip()]
        
        # 查找净值相关行
        net_value_data = []
        for i, line in enumerate(clean_lines):
            if '净值' in line or '周' in line or '累计' in line:
                # 获取相邻的几行
                context_lines = clean_lines[max(0,i-2):min(len(clean_lines),i+3)]
                net_value_data.append({
                    'line': line,
                    'context': context_lines
                })
        
        # 保存数据
        output = {
            "fundId": FUND_ID,
            "timestamp": datetime.now().isoformat(),
            "rawText": page_text,
            "netValueFound": net_value_data
        }
        
        json_file = f"fund_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"数据保存: {json_file}")
        
        # 打印关键数据
        print("\n" + "="*60)
        print("提取到的数据:")
        print("="*60)
        for item in net_value_data[:10]:
            print(f"\n{item['line']}")
        
        print("\n\n完成!")
        browser.close()

if __name__ == "__main__":
    main()
