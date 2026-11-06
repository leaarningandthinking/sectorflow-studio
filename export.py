import argparse
import base64
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile

from playwright.sync_api import sync_playwright
from data_source import load_data
from audio import mix_music
from outro import append_outro

ROOT = Path(__file__).resolve().parent


def export(date='2026-10-20', duration=60, kind='cover', port=8765, fps=30,
           music=None, volume=.2, music_start=0, snapshot_path=None, mode="api", category="industry", source="top"):
    out = ROOT / 'output'
    out.mkdir(exist_ok=True)
    if kind == 'video' and not all(shutil.which(name) for name in ('ffmpeg','ffprobe')):
        raise RuntimeError('请先安装 FFmpeg，并确保 ffmpeg、ffprobe 已加入系统 PATH')
    snapshot = json.loads(Path(snapshot_path).read_text(encoding='utf8')) if snapshot_path else load_data(date, mode=mode, category=category, source=source)
    if category not in ('industry','concept') or snapshot.get('meta',{}).get('category','industry') != category:
        raise ValueError('导出数据类别不匹配，请重新加载数据')
    if source not in ('top','legacy') or snapshot.get('meta',{}).get('source_key','legacy') != source:
        raise ValueError('导出数据源不匹配，请重新加载对应数据源')
    suffix = ('_top' if source == 'top' else '') + ('_concept' if category == 'concept' else '')
    if snapshot.get('date') != date:
        raise ValueError('导出数据日期不匹配')
    html = (ROOT / 'web/index.html').read_text(encoding='utf8')
    html = html.replace('<script src="vendor/echarts.min.js"></script>', '')
    html = html.replace('<script src="app.js"></script>', '')
    # Standalone poster tools do not participate in offline chart/video rendering.
    html = re.sub(r'<script[^>]+src="cover\.js(?:\?[^"]*)?"[^>]*></script>', '', html)
    html = re.sub(r'<link[^>]+href="cover\.css(?:\?[^"]*)?"[^>]*>', '', html)
    # Exports render without a server; embed the original brand assets locally.
    for asset in (ROOT / 'web/assets').iterdir():
        if asset.suffix not in {'.png', '.mp4'}:
            continue
        encoded = base64.b64encode(asset.read_bytes()).decode('ascii')
        mime = 'image/png' if asset.suffix == '.png' else 'video/mp4'
        html = re.sub(r'src="assets/' + re.escape(asset.name) + r'(?:\?[^"]*)?"', lambda match: 'src="data:' + mime + ';base64,' + encoded + '"', html)
    font = ROOT / 'web/assets/fonts/SourceHanSansSC-VF.woff2'
    html = html.replace('assets/fonts/SourceHanSansSC-VF.woff2',
                        'data:font/woff2;base64,' + base64.b64encode(font.read_bytes()).decode('ascii'))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'], **(
            {'executable_path': '/usr/bin/chromium'} if Path('/usr/bin/chromium').exists() else {}))
        try:
            page = browser.new_page(viewport={'width': 1100, 'height': 1940}, device_scale_factor=1)
            page.set_content(html)
            page.add_script_tag(path=str(ROOT / 'web/vendor/echarts.min.js'))
            page.evaluate('(data)=>{window.__sectorFlowExport=true;window.__sectorFlowSnapshot=data;window.fetch=async()=>({ok:true,json:async()=>data})}', snapshot)
            page.add_script_tag(content=(ROOT / 'web/app.js').read_text(encoding='utf8'))
            page.wait_for_function('window.sectorFlow && window.sectorFlow.ready()', timeout=15000)
            page.add_style_tag(content='.export-exclude{display:none!important}.workspace,.studio-main,.preview-panel,.preview-canvas{padding:0!important;margin:0!important;display:block!important;height:auto!important;min-height:0!important;border:0!important;background:transparent!important;overflow:visible!important}.controls{display:none!important}.stage-wrap{width:1080px!important;height:1920px!important;box-shadow:none!important}.stage{transform:none!important}')
            page.evaluate('async()=>{await document.fonts.ready;await Promise.all(Array.from(document.images,img=>img.decode()))}')
            page.wait_for_function('(()=>{const video=document.querySelector("#outro-video");return video && video.readyState>=2 && Number.isFinite(video.duration) && video.duration>0})()', timeout=15000)
            stage = page.locator('#stage')
            if kind == 'cover':
                page.evaluate('window.sectorFlow.setFrame(window.sectorFlow.lastFrame())')
                dest = out / f'{date}{suffix}_cover.png'
                stage.screenshot(path=str(dest))
            else:
                n = round((duration + 1) * fps)
                dest = out / f'{date}{suffix}_fund_flow.mp4'
                with tempfile.TemporaryDirectory(prefix='sectorflow-render-') as tmp:
                    prefix = Path(tmp) / 'chart.mp4'
                    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                           '-f', 'image2pipe', '-vcodec', 'png', '-r', str(fps), '-i', '-',
                           '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
                           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(prefix)]
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
                    try:
                        last_key, last_png = None, None
                        for f in range(n):
                            if f / fps >= duration:
                                key = page.evaluate('()=>{window.sectorFlow.setFrame(window.sectorFlow.lastFrame());return \"close-hold\"}')
                            else:
                                key = page.evaluate('([t,d])=>window.sectorFlow.setExportFrame(t,d)', [f / fps, duration])
                            if key != last_key:
                                last_png = stage.screenshot(type='png')
                                last_key = key
                            proc.stdin.write(last_png)
                        proc.stdin.close()
                        err = proc.stderr.read()
                        code = proc.wait()
                        if code:
                            raise RuntimeError(err.decode(errors='replace'))
                    except Exception:
                        proc.kill()
                        proc.wait()
                        raise
                    append_outro(prefix, ROOT / 'web/assets/custom-outro.mp4', dest, n / fps, fps)
                    if music:
                        info = json.loads(subprocess.check_output(
                            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(dest)]))
                        mix_music(dest, music, float(info['format']['duration']), volume, music_start)
            print(dest)
        finally:
            browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default='2026-10-20')
    parser.add_argument('--duration', type=float, default=60, help='行情时长；另附1秒收盘停留及完整自定义片尾视频')
    parser.add_argument('--type', choices=['cover', 'video'], default='cover')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--music')
    parser.add_argument('--volume', type=float, default=.2)
    parser.add_argument('--music-start', type=float, default=0)
    parser.add_argument('--snapshot', help='锁定导出的JSON快照路径')
    parser.add_argument('--mode', choices=['api','demo'], default='api')
    parser.add_argument('--category', choices=['industry','concept'], default='industry')
    parser.add_argument('--source', choices=['top','legacy'], default='top')
    args = parser.parse_args()
    export(args.date, args.duration, args.type, args.port, args.fps,
           args.music, args.volume, args.music_start, args.snapshot, args.mode, args.category, args.source)
