"""Cross-platform release smoke check; uses demo data and an isolated copy."""
import array
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'output' / 'test-artifacts'
DATE = '2026-11-06'
OUTRO_SECONDS = float(json.loads((ROOT / 'web/assets/outro-config.json').read_text(encoding='utf8'))['duration'])
EXPORT_SECONDS = 5 + OUTRO_SECONDS


def run(args, **kwargs):
    return subprocess.run([str(value) for value in args], check=True, **kwargs)


def metadata(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def audio_rms(path, start, duration):
    raw = subprocess.check_output([
        'ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(path), '-t', str(duration),
        '-vn', '-ac', '1', '-ar', '48000', '-f', 'f32le', '-'])
    samples = array.array('f')
    samples.frombytes(raw)
    assert samples, 'No decoded audio samples'
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def check_missing_headless_runtime(project):
    spec = importlib.util.spec_from_file_location('release_bootstrap', project / 'bootstrap.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PYTHON = Path(sys.executable)
    with tempfile.TemporaryDirectory(prefix='sectorflow browser check ') as directory:
        old = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
        try:
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = directory
            with sync_playwright() as playwright:
                full_browser = Path(playwright.chromium.executable_path)
            full_browser.parent.mkdir(parents=True, exist_ok=True)
            full_browser.touch()
            # A full-browser path exists, but the headless component is absent.
            assert not module.runtime_ready(), 'Startup accepted a missing export browser'
        finally:
            if old is None:
                os.environ.pop('PLAYWRIGHT_BROWSERS_PATH', None)
            else:
                os.environ['PLAYWRIGHT_BROWSERS_PATH'] = old
    print('PASS startup detects missing headless component even if full-browser file exists', flush=True)


def browser_checks(base_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        # CDN and upstream API availability must not affect this smoke test.
        page.route('**/*', lambda route: route.continue_()
                   if urlparse(route.request.url).hostname in ('127.0.0.1', 'localhost')
                   else route.abort())
        try:
            page.goto(base_url, wait_until='domcontentloaded')
            assert page.locator('#duration').input_value() == '24'
            page.wait_for_function('window.sectorFlow && window.sectorFlow.endingDuration === 9')
            page.click('#cover-tab')
            page.wait_for_function('window.sectorCover?.ready()')
            font = page.evaluate('''async () => {
                await document.fonts.load('500 24px "SectorFlow Sans"', '行业主力资金流向123');
                return Array.from(document.fonts).filter(f => f.family.includes('SectorFlow Sans'))
                    .map(f => f.status);
            }''')
            assert font and all(status == 'loaded' for status in font), font
            assert 'SectorFlow Sans' in page.locator('body').evaluate('(e)=>getComputedStyle(e).fontFamily')
            for format_name in ('portrait34', 'portrait916'):
                page.select_option('#cover-format', format_name)
                page.wait_for_function('window.sectorCover.ready()')
                with page.expect_download() as pending:
                    page.click('#cover-export')
                destination = ARTIFACTS / f'{format_name}.jpg'
                pending.value.save_as(destination)
                assert destination.read_bytes()[:2] == b'\xff\xd8'
                assert 0 < destination.stat().st_size <= 500000
                image = next(s for s in metadata(destination)['streams'] if s['codec_type'] == 'video')
                expected = (1200, 1600) if format_name == 'portrait34' else (1080, 1920)
                assert (image['width'], image['height']) == expected, image
                print(f'PASS cover {format_name}: {destination.stat().st_size} bytes', flush=True)
            page.click('#video-tab')
            page.wait_for_function('window.sectorFlow && !loading')
            for category, title in (
                    ('industry', '行业主力资金流向'),
                    ('concept', '热门概念主力资金流向')):
                with urlopen(base_url + f'api/data?date={DATE}&mode=demo&category={category}&source=top', timeout=10) as response:
                    snapshot = json.load(response)
                assert snapshot['mock'] and snapshot['industries'] and snapshot['times']
                assert snapshot['meta']['category'] == category
                await_load = '''async ([date, category]) => {
                    document.querySelector('#date').value=date;
                    document.querySelector('#data-mode-select').value='demo';
                    document.querySelector('#source-select').value='top';
                    document.querySelector('#category-select').value=category;
                    await window.sectorFlow.load(false);
                }'''
                page.evaluate(await_load, [DATE, category])
                page.wait_for_function('window.sectorFlow.ready()')
                assert page.locator('#industry-title').inner_text() == title
                series = page.evaluate('()=>chart.getOption().series.map(s=>s.lineStyle.type)')
                assert series and all(style == 'solid' for style in series), series
                page.locator('#stage').screenshot(path=str(ARTIFACTS / f'{category}.png'))
                print(f'PASS {category}: demo API and solid-line chart', flush=True)
            page.route('**/api/export', lambda route: route.fulfill(
                status=500, content_type='application/json',
                body=json.dumps({'error': '测试渲染组件缺失提示'}, ensure_ascii=False)))
            page.uncheck('#music-enabled')
            page.click('#video')
            page.wait_for_function('document.querySelector("#export-feedback").dataset.state === "error"')
            assert page.locator('#export-feedback').is_visible()
            assert page.locator('#export-feedback').get_attribute('role') == 'alert'
            assert '测试渲染组件缺失提示' in page.locator('#export-feedback').inner_text()
            assert page.locator('#video').is_enabled()
            assert page.locator('#video').inner_text() == '↓ 导出视频'
            print('PASS visible export failure feedback and button recovery', flush=True)

        except Exception:
            page.screenshot(path=str(ARTIFACTS / 'browser-failure.png'), full_page=True)
            raise
        finally:
            browser.close()


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # The user's real data and videos must never be overwritten by a smoke test.
    with tempfile.TemporaryDirectory(prefix='sectorflow release ') as temporary:
        project = Path(temporary)
        for path in ROOT.glob('*.py'):
            shutil.copy2(path, project / path.name)
        shutil.copytree(ROOT / 'web', project / 'web')
        check_missing_headless_runtime(project)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base_url = f'http://127.0.0.1:{port}/'
        environment = dict(os.environ, PYTHONUTF8='1')
        with (ARTIFACTS / 'server.log').open('w', encoding='utf8') as log:
            server = subprocess.Popen(
                [sys.executable, str(project / 'server.py'), '--port', str(port)],
                cwd=project, env=environment, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError('Test server exited; see server.log')
                    try:
                        with urlopen(base_url, timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Test server startup timed out')
                browser_checks(base_url)
                music = project / 'test-tone.wav'
                run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                     'sine=frequency=440:duration=2', str(music)])
                run([sys.executable, project / 'export.py', '--date', DATE, '--mode', 'demo',
                     '--source', 'top', '--category', 'industry', '--type', 'video',
                     '--duration', '3', '--fps', '10', '--music', music, '--volume', '.4'],
                    cwd=project, env=environment, timeout=300)
                video = project / 'output' / f'{DATE}_top_fund_flow.mp4'
                info = metadata(video)
                assert abs(float(info['format']['duration']) - EXPORT_SECONDS) < .15, info['format']['duration']
                assert any(s['codec_type'] == 'audio' for s in info['streams'])
                visual = next(s for s in info['streams'] if s['codec_type'] == 'video')
                assert (visual['width'], visual['height']) == (1080, 1920)
                late_rms = audio_rms(video, 6, .4)
                assert late_rms > .005, late_rms
                assert audio_rms(video, EXPORT_SECONDS-.2, .15) < late_rms * .3
                shutil.copy2(video, ARTIFACTS / 'smoke-video.mp4')
                print(f'PASS video: {EXPORT_SECONDS:g} seconds, 1080x1920, music continues into outro and fades out', flush=True)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    print('All release smoke checks passed.', flush=True)


if __name__ == '__main__':
    main()
