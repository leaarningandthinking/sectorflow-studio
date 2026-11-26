"""Exercise cover auto/manual choices, stale replies, and real JPEG downloads."""
from pathlib import Path
import json, shutil, socket, subprocess, sys, tempfile, time
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'output/test-artifacts'
ART.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='sectorflow covers ') as directory:
    root = Path(directory)
    for path in ROOT.glob('*.py'):
        shutil.copy2(path, root/path.name)
    shutil.copytree(ROOT/'web', root/'web')
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
    url = f'http://127.0.0.1:{port}/'
    with (root/'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, str(root/'server.py'), '--port', str(port)], stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    if urlopen(url, timeout=1).status == 200: break
                except OSError: time.sleep(.1)
            actual = json.load(urlopen(url+'api/cover-market?date=2026-11-26&source=top'))
            assert actual['available'] is False
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width':1440,'height':1000}, accept_downloads=True)
                held = []
                def market(route):
                    q = parse_qs(urlparse(route.request.url).query)
                    date, source = q['date'][0], q['source'][0]
                    result = {'date':date,'source':source,'available':date in ('2026-11-09','2026-11-10'),
                              'total':0 if date.endswith('09') else -12.34, 'total_exact':'0' if date.endswith('09') else '-12.34',
                              'color':'red' if date.endswith('09') else 'blue','as_of':'15:00'}
                    if date == '2026-11-08': held.append((route,result))
                    else: route.fulfill(json=result)
                page.route('**/api/cover-market?*', market)
                page.route('**/api/data?*', lambda route: route.abort())
                page.goto(url); page.click('#cover-tab')
                page.wait_for_function('window.sectorCover?.ready()')
                assert page.evaluate('sectorCover.state().selection') == 'auto'
                def date(value):
                    page.locator('#cover-date').fill(value)
                date('2026-11-09')
                page.wait_for_function('sectorCover.ready() && sectorCover.state().judged && sectorCover.state().color === "red"')
                date('2026-11-10')
                page.wait_for_function('sectorCover.ready() && sectorCover.state().judged && sectorCover.state().color === "blue"')
                page.select_option('#cover-color-mode', 'red')
                date('2026-11-10')
                page.evaluate('window.dispatchEvent(new Event("sectorflow-data-updated"))')
                page.wait_for_timeout(150)
                assert page.evaluate('sectorCover.state().color') == 'red'
                page.select_option('#cover-color-mode', 'auto')
                page.wait_for_function('sectorCover.state().judged && sectorCover.state().color === "blue"')
                date('2026-11-08'); page.wait_for_timeout(100)
                date('2026-11-09')
                page.wait_for_function('sectorCover.state().judged && sectorCover.state().marketDate === "2026-11-09"')
                for route,result in held: route.fulfill(json=result)
                page.wait_for_timeout(100)
                assert page.evaluate('sectorCover.state().color') == 'red'
                date('2026-11-26')
                page.wait_for_function('!sectorCover.state().judged && sectorCover.ready()')
                assert page.evaluate('sectorCover.state().color') == 'red'
                assert '未自动判定' in page.locator('#cover-color-reason').inner_text()
                date('2026-11-09')
                for color in ('blue','red'):
                    page.select_option('#cover-color-mode', color)
                    for fmt in ('portrait34','portrait916'):
                        page.select_option('#cover-format',fmt)
                        page.wait_for_function('sectorCover.ready()')
                        with page.expect_download() as download: page.click('#cover-export')
                        path = ART/f'cover-{color}-{fmt}.jpg'; download.value.save_as(path)
                        assert path.read_bytes()[:2] == b'\xff\xd8' and path.stat().st_size <= 500000
                        info = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height','-of','json',str(path)]))['streams'][0]
                        assert (info['width'],info['height']) == ((1200,1600) if fmt=='portrait34' else (1080,1920))
                        print(f'PASS {color} {fmt}: {path.stat().st_size} bytes',flush=True)
                browser.close()
            print('PASS zero/red, negative/blue, manual persistence, stale response, no-data fallback, four JPEG exports')
        finally:
            server.terminate();server.wait(timeout=10)
