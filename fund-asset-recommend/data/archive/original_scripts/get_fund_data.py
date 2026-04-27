from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import pandas as pd
import time
import json
import os

COOKIE_FILE = os.path.expanduser("~/.openclaw/workspace/huofuniu_cookies.json")

def save_cookies(driver, cookie_file=COOKIE_FILE):
    """保存cookie到文件"""
    with open(cookie_file, 'w') as f:
        json.dump(driver.get_cookies(), f)
    print(f"✅ Cookie已保存到: {cookie_file}")

def load_cookies(driver, cookie_file=COOKIE_FILE):
    """从文件加载cookie"""
    if not os.path.exists(cookie_file):
        return False
    
    driver.get("https://mp.fof99.com")
    time.sleep(2)
    
    with open(cookie_file, 'r') as f:
        cookies = json.load(f)
    
    for cookie in cookies:
        # 移除selenium不需要的字段
        cookie.pop('sameSite', None)
        try:
            driver.add_cookie(cookie)
        except:
            pass
    
    driver.refresh()
    time.sleep(3)
    
    # 检查是否登录成功
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.ant-layout-header'))
        )
        print("✅ Cookie加载成功，已登录")
        return True
    except:
        print("⚠️ Cookie已失效，需要重新登录")
        return False

def wait_for_login(driver):
    """等待用户手动登录"""
    print("=" * 60)
    print("请在浏览器中登录火富牛...")
    print("登录完成后，在终端按回车继续...")
    print("=" * 60)
    input()
    
    # 登录后保存cookie
    save_cookies(driver)
    return True

def get_latest_week_data():
    """
    每周自动抓取：最新一条周频基金数据
    不需要改日期！不需要改参数！
    运行一次 = 拿最新一周数据
    """
    fund_url = "https://mp.fof99.com/fund/view/4f3027afbe1adcf3"

    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    # 保持浏览器窗口打开，便于调试
    # options.add_argument('--headless')  # 如果不需要看到浏览器，可以取消注释

    # 尝试使用系统ChromeDriver，如果没有则让用户手动安装
    try:
        driver = webdriver.Chrome(options=options)
    except:
        # 尝试常见位置
        chrome_paths = [
            "/usr/local/bin/chromedriver",
            "/Applications/Google Chrome.app/Contents/MacOS/chromedriver",
            "/opt/homebrew/bin/chromedriver"
        ]
        driver = None
        for path in chrome_paths:
            if os.path.exists(path):
                driver = webdriver.Chrome(service=Service(path), options=options)
                break
        if not driver:
            raise Exception("请先安装ChromeDriver：brew install chromedriver")

    try:
        # 先尝试加载cookie
        driver.get("https://mp.fof99.com")
        time.sleep(2)
        
        if os.path.exists(COOKIE_FILE):
            # 尝试加载cookie
            if load_cookies(driver, COOKIE_FILE):
                print("🔄 已使用保存的登录状态")
            else:
                # Cookie失效，等待用户重新登录
                wait_for_login(driver)
        else:
            # 第一次使用，需要登录
            print("🔐 首次使用，需要登录...")
            wait_for_login(driver)
        
        # 访问目标页面
        driver.get(fund_url)
        time.sleep(3)

        # 1. 选择周频
        dropdown = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'div.ant-select.ant-select-sm.ant-select-single[style*="width: 70px;"]')
            )
        )
        dropdown.click()
        time.sleep(1)

        weekly = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//div[@class="ant-select-item-option-content" and text()="周频"]')
            )
        )
        weekly.click()
        time.sleep(1)

        # 2. 点击开始分析
        analyze = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//button[@class="ant-btn ant-btn-danger ant-btn-sm"]/span[text()="开始分析"]')
            )
        )
        analyze.click()

        print("⏳ 正在加载数据...")
        time.sleep(10)

        # 3. 抓取所有行
        rows = driver.find_elements(
            By.CSS_SELECTOR,
            'div.virtual-content div[style*="overflow: hidden;"] div[class*="flex flex-nowrap border-b-ebeef5"]'
        )

        data = []
        for row in rows:
            cols = row.find_elements(By.CSS_SELECTOR, 'div[class*="flex items-center"]')
            if len(cols) == 5:
                date_str = cols[0].text.strip()
                nav = cols[1].text.strip()
                cum_nav = cols[2].text.strip()
                fq_nav = cols[3].text.strip()
                chg = cols[4].text.strip()
                data.append([date_str, nav, cum_nav, fq_nav, chg])

        df = pd.DataFrame(data, columns=['日期', '单位净值', '累计净值', '复权净值', '涨跌幅'])

        # ====================== 关键：自动取最新一条 ======================
        df_latest = df.head(1)  # 第一条就是最新日期

        # 保存
        date_name = df_latest['日期'].iloc[0].replace('-', '')
        filename = f"基金周频_{date_name}.xlsx"
        df_latest.to_excel(filename, index=False)

        print(f"\n✅ 最新一周数据已抓取：")
        print(df_latest)
        print(f"\n📁 文件已保存：{filename}")

    except Exception as e:
        print(f"❌ 出错：{e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == '__main__':
    get_latest_week_data()
