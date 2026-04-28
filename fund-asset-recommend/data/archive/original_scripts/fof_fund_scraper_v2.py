#!/usr/bin/env python3
"""
火富牛数据抓取 - 支持登录状态保存
首次运行需要登录，之后会自动复用登录状态
"""

import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

FUND_ID = "4f3027afbe1adcf3"
BASE_URL = "https://mp.fof99.com"
STATE_FILE = "fof_browser_state.json"

def get_browser_with_storage():
    """启动浏览器并加载保存的登录状态"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        # 尝试加载已保存的登录状态
        if os.path.exists(STATE_FILE):
            print(f"加载已保存的登录状态: {STATE_FILE}")
            context = browser.new_context(storage_state=STATE_FILE)
        else:
            print("未找到登录状态，需要手动登录")
            context = browser.new_context()
        
        page = context.new_page()
        return browser, context, page

def save_login_state(context):
    """保存登录状态到文件"""
    storage = context.storage_state()
    with open(STATE_FILE, "w") as f:
        json.dump(storage, f)
    print(f"登录状态已保存到: {STATE_FILE}")

def main():
    print("="*60)
    print("火富牛数据抓取工具 (支持登录状态保存)")
    print("="*60)
    print(f"基金ID: {FUND_ID}")
    print("\n使用方法:")
    print("1. 首次运行需要手动登录")
    print("2. 登录后状态会自动保存到本地")
    print("3. 下次运行会自动使用保存的登录状态")
    print("="*60 + "\n")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        # 加载或创建登录状态
        if os.path.exists(STATE_FILE):
            print("加载已保存的登录状态...")
            context = browser.new_context(storage_state=STATE_FILE)
        else:
            print("首次使用，需要登录...")
            context = browser.new_context()
        
        page = context.new_page()
        
        # 访问页面
        page.goto(f"{BASE_URL}/fund/view/{FUND_ID}")
        
        # 检查是否需要登录
        # 等待页面加载
        page.wait_for_timeout(3000)
        
        # 尝试检测登录状态（根据页面元素判断）
        # 如果出现登录相关的元素，可能需要登录
        try:
            # 等待某个登录后才有的元素出现
            page.wait_for_selector(".user-info, .username, [class*='login']", timeout=5000)
            print("检测到已登录状态")
            needs_login = False
        except:
            print("可能需要登录，请在浏览器中完成登录...")
            needs_login = True
        
        if needs_login:
            print("\n请在浏览器中登录，完成后回到终端按回车...")
            input()
            # 登录成功后保存状态
            save_login_state(context)
            print("状态已保存")
        
        print("\n请在浏览器中操作，找到基金数据后按回车保存...")
        input()
        
        # 等待动画完成
        page.wait_for_timeout(2000)
        
        # 截图
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_file = f"fund_screenshot_{timestamp}.png"
        page.screenshot(path=screenshot_file, full_page=True)
        print(f"\n截图保存: {screenshot_file}")
        
        # 获取页面内容
        page_text = page.evaluate("document.body.innerText")
        
        # 保存完整 HTML
        html_file = f"fund_data_{timestamp}.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"HTML保存: {html_file}")
        
        # 提取关键数据
        lines = [l.strip() for l in page_text.split('\n') if l.strip()]
        net_value_data = []
        
        for i, line in enumerate(lines):
            if '净值' in line or '周' in line or '累计' in line or '收益' in line:
                context_lines = lines[max(0,i-2):min(len(lines),i+3)]
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
        
        json_file = f"fund_data_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"数据保存: {json_file}")
        
        # 打印关键数据
        print("\n" + "="*60)
        print("提取到的数据:")
        print("="*60)
        for item in net_value_data[:10]:
            print(f"\n{item['line']}")
        
        # 询问是否更新登录状态
        print("\n" + "="*60)
        update = input("更新保存的登录状态吗? (y/n): ")
        if update.lower() == 'y':
            save_login_state(context)
        
        print("\n完成!")
        browser.close()

if __name__ == "__main__":
    main()
