"""Install the local runtime and start SectorFlow on macOS or Windows."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen
import venv
import webbrowser

os.environ.setdefault('PYTHONUTF8', '1')

ROOT = Path(__file__).resolve().parent
ENV = ROOT / '.venv'
PYTHON = ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
MARKER = ENV / '.sectorflow-setup'


def run(args):
    subprocess.run([str(item) for item in args], cwd=ROOT, check=True)


def ffmpeg_ready():
    missing = [name for name in ('ffmpeg', 'ffprobe') if not shutil.which(name)]
    if not missing:
        return True
    print('缺少视频处理工具：' + '、'.join(missing), flush=True)
    if sys.platform == 'darwin':
        print('请安装 Homebrew 后运行：brew install ffmpeg')
    elif os.name == 'nt':
        print('请安装包含 ffmpeg.exe 和 ffprobe.exe 的 FFmpeg，并将 bin 文件夹加入 PATH。')
        print('下载入口：https://ffmpeg.org/download.html#build-windows')
    else:
        print('请安装 FFmpeg，并确保 ffmpeg 和 ffprobe 已加入 PATH。')
    print('安装完成后重新打开启动文件。')
    return False


def runtime_ready():
    if not PYTHON.is_file():
        return False
    result = subprocess.run(
        [str(PYTHON), '-c', 'import playwright; from playwright.sync_api import sync_playwright; '
         'from pathlib import Path; p=sync_playwright().start(); '
         'ok=Path(p.chromium.executable_path).is_file(); p.stop(); raise SystemExit(0 if ok else 1)'],
        cwd=ROOT, capture_output=True)
    return result.returncode == 0


def open_when_ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            return
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            pass
        time.sleep(.2)
    print('浏览器未自动打开，请手动访问：' + url, flush=True)


def main():
    parser = argparse.ArgumentParser(description='安装并启动资金流向工作台')
    parser.add_argument('--check', action='store_true', help='只检查环境，不安装或启动')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        print('请安装 Python 3.10 或更新版本，再重新启动。')
        return 1
    if not 1 <= args.port <= 65535:
        print('端口必须在 1—65535 之间。')
        return 1
    tools_ready = ffmpeg_ready()
    if args.check:
        ready = runtime_ready()
        print('Python：' + sys.version.split()[0])
        print('本地浏览器运行环境：' + ('已就绪' if ready else '未安装，请运行安装并启动文件'))
        return 0 if ready and tools_ready else 1
    if not tools_ready:
        return 1
    requirements = ROOT / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if not PYTHON.is_file():
        print('正在创建项目专用运行环境…', flush=True)
        venv.EnvBuilder(with_pip=True).create(ENV)
    configured = MARKER.is_file() and MARKER.read_text(encoding='utf8') == fingerprint
    if not configured or not runtime_ready():
        print('首次安装依赖及 Chromium，需要联网，请稍候…', flush=True)
        run([PYTHON, '-m', 'pip', 'install', '-r', requirements])
        run([PYTHON, '-m', 'playwright', 'install', 'chromium'])
        MARKER.write_text(fingerprint, encoding='utf8')
    url = f'http://127.0.0.1:{args.port}/'
    print('正在启动：' + url + '\n保持此窗口打开；按 Ctrl+C 停止服务。', flush=True)
    process = subprocess.Popen([str(PYTHON), str(ROOT / 'server.py'), '--port', str(args.port)], cwd=ROOT)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url, process), daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
        process.wait()
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as error:
        print('启动未完成：' + str(error), flush=True)
        raise SystemExit(1)
