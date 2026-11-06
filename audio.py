"""Local music validation and MP4 audio composition."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

MAX_MUSIC_BYTES = 50 * 1024 * 1024
MUSIC_EXTENSIONS = {'.mp3', '.m4a', '.wav'}


def audio_duration(path):
    if not shutil.which('ffprobe'):
        raise ValueError('音乐处理需要 FFmpeg，请安装 ffmpeg 和 ffprobe 并加入 PATH（Mac 可运行 brew install ffmpeg）')
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
         '-show_entries', 'stream=index:format=duration', '-of', 'json', str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    if result.returncode:
        raise ValueError('无法读取音乐，请选择有效的 MP3、M4A 或 WAV 文件')
    info = json.loads(result.stdout)
    duration = float(info.get('format', {}).get('duration', 0))
    if not info.get('streams') or not math.isfinite(duration) or duration <= 0:
        raise ValueError('音乐文件没有可用的音轨或时长')
    return duration


def mix_music(video, music, duration, volume=0.2, start=0):
    if not all(math.isfinite(x) for x in (duration, volume, start)) or not (duration > 0 and 0 <= volume <= 1 and start >= 0):
        raise ValueError('音乐音量或起播时间无效')
    if start >= audio_duration(music):
        raise ValueError('音乐起播时间必须小于音乐总时长')
    # Trim once, then loop the selected segment, so the skipped intro never returns.
    with tempfile.TemporaryDirectory(prefix='sectorflow-audio-') as tmp:
        segment = Path(tmp) / 'segment.wav'
        merged = Path(tmp) / 'merged.mp4'
        def run(args):
            result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y'] + args,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
            if result.returncode:
                raise RuntimeError('音乐合成失败：' + result.stderr[-1000:])
        run(['-ss', str(start), '-i', str(music), '-t', str(duration), '-vn',
             '-ac', '2', '-ar', '48000', '-c:a', 'pcm_s16le', str(segment)])
        fade_in, fade_out = min(1, duration / 3), min(2, duration / 3)
        filters = (f'volume={volume},afade=t=in:st=0:d={fade_in},'
                   f'afade=t=out:st={duration-fade_out}:d={fade_out}')
        info = json.loads(subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json', str(video)]))
        has_audio = any(s['codec_type'] == 'audio' for s in info['streams'])
        graph = f'[1:a:0]{filters}[music];'
        if has_audio:
            graph += '[0:a:0][music]amix=inputs=2:duration=longest:normalize=0[a]'
        else:
            graph += '[music]anull[a]'
        run(['-i', str(video), '-stream_loop', '-1', '-i', str(segment),
             '-filter_complex', graph, '-map', '0:v:0', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac',
             '-b:a', '192k', '-t', str(duration),
             '-movflags', '+faststart', str(merged)])
        shutil.copyfile(merged, video)
