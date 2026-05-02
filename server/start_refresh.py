#!/usr/bin/env python3
"""
GAMT 刷新服务 + Cloudflare Tunnel 启动脚本
1. 启动 refresh_server.py（端口 9876）
2. 启动 cloudflared quick tunnel
3. 把 tunnel URL 写入 tunnel_url.json（前端读取）
4. git push 让 Cloudflare Pages 拿到最新 URL

用法：python3 start_refresh.py
停止：python3 start_refresh.py --stop
"""

import subprocess, sys, os, time, json, signal, re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL_FILE = os.path.join(BASE_DIR, 'tunnel_url.json')
TUNNEL_LOG = '/tmp/cf-tunnel.log'
SERVER_LOG = '/tmp/gamt-refresh.log'


def stop_all():
    """停止所有相关进程"""
    subprocess.run(['pkill', '-f', 'refresh_server.py'], capture_output=True)
    subprocess.run(['pkill', '-f', 'cloudflared tunnel'], capture_output=True)
    print(" 已停止所有服务")


def start_server():
    """启动 refresh_server"""
    subprocess.run(['pkill', '-f', 'refresh_server.py'], capture_output=True)
    time.sleep(1)
    subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, 'server', 'refresh_server.py')],
        cwd=BASE_DIR,
        stdout=open(SERVER_LOG, 'w'),
        stderr=subprocess.STDOUT
    )
    time.sleep(2)
    # Verify
    try:
        import urllib.request
        r = urllib.request.urlopen('http://localhost:9876/api/status', timeout=3)
        print(" refresh_server 启动成功 (端口 9876)")
        return True
    except:
        print(" refresh_server 启动失败")
        return False


def start_tunnel():
    """启动 cloudflared quick tunnel, 返回 URL"""
    subprocess.run(['pkill', '-f', 'cloudflared tunnel'], capture_output=True)
    time.sleep(1)

    with open(TUNNEL_LOG, 'w') as log:
        subprocess.Popen(
            ['cloudflared', 'tunnel', '--url', 'http://localhost:9876', '--protocol', 'http2'],
            stdout=log, stderr=subprocess.STDOUT
        )

    # 等待 tunnel URL 出现
    print("⏳ 等待 Cloudflare Tunnel...")
    for i in range(30):
        time.sleep(1)
        try:
            with open(TUNNEL_LOG) as f:
                content = f.read()
            match = re.search(r'(https://[a-z0-9-]+\.trycloudflare\.com)', content)
            if match:
                url = match.group(1)
                print(f" Tunnel: {url}")
                return url
        except:
            pass
    print(" Tunnel 启动超时")
    return None


def save_url(url):
    """写入 tunnel_url.json"""
    data = {
        'url': url,
        'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(URL_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f" URL 写入 {URL_FILE}")


def git_push():
    """推送 tunnel_url.json"""
    try:
        subprocess.run(['git', 'add', 'tunnel_url.json'], cwd=BASE_DIR, check=True)
        result = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=BASE_DIR)
        if result.returncode == 0:
            print("  （URL 没变，跳过 push）")
            return
        subprocess.run(['git', 'commit', '-m', 'auto: update tunnel URL'], cwd=BASE_DIR, check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], cwd=BASE_DIR, check=True, capture_output=True, timeout=15)
        print(" git push 完成")
    except Exception as e:
        print(f"⚠ git push 失败: {e}")


def main():
    if '--stop' in sys.argv:
        stop_all()
        return

    print(" GAMT 刷新服务启动")
    print("=" * 40)

    # 1. 启动 server
    if not start_server():
        return

    # 2. 启动 tunnel
    url = start_tunnel()
    if not url:
        print("⚠ Tunnel 失败，只能本机使用")
        return

    # 3. 保存 URL + push
    save_url(url)
    git_push()

    print()
    print(f" 外网地址: {url}")
    print(f" 本机地址: http://localhost:9876")
    print(f"停止: python3 {__file__} --stop")


if __name__ == '__main__':
    main()
