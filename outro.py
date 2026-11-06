"""Append the supplied branded outro, keeping its sound separate from chart music."""
import json
from pathlib import Path
import subprocess


def append_outro(prefix, outro, dest, prefix_duration, fps=30):
    prefix, outro, dest = Path(prefix), Path(outro), Path(dest)
    if not outro.is_file():
        raise ValueError('缺少自定义片尾视频，请恢复 web/assets/custom-outro.mp4')
    def probe(path):
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,color_space,color_range:format=duration',
                                 '-of', 'json', str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        if result.returncode:
            raise RuntimeError('无法读取视频音轨：' + result.stderr[-500:])
        return json.loads(result.stdout)
    prefix_info, outro_info = probe(prefix), probe(outro)
    outro_duration = float(outro_info['format']['duration'])
    has_prefix_audio = any(stream['codec_type'] == 'audio' for stream in prefix_info['streams'])
    has_outro_audio = any(stream['codec_type'] == 'audio' for stream in outro_info['streams'])
    if not has_outro_audio:
        raise ValueError('自定义片尾没有音轨，无法保留原声，请检查素材')
    args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(prefix), '-i', str(outro)]
    if not has_prefix_audio:
        args += ['-f', 'lavfi', '-t', str(prefix_duration), '-i', 'anullsrc=r=48000:cl=stereo']
    prefix_audio = '0:a:0' if has_prefix_audio else '2:a:0'
    def video_filter(info, fill_frame=False):
        video = next(stream for stream in info['streams'] if stream['codec_type'] == 'video')
        # Our untagged PNG-rendered prefix was encoded by FFmpeg using BT.601.
        # The supplied clip is tagged BT.709. Convert both explicitly before concat.
        matrix = 'bt709' if video.get('color_space') == 'bt709' else 'bt601'
        input_range = 'full' if video.get('color_range') == 'pc' else 'limited'
        aspect = 'increase' if fill_frame else 'decrease'
        framing = 'crop=1080:1920' if fill_frame else 'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black'
        return (f'scale=1080:1920:force_original_aspect_ratio={aspect}:force_divisible_by=2:in_color_matrix={matrix}'
                f':out_color_matrix=bt709:in_range={input_range}:out_range=limited,'
                f'{framing},setsar=1,fps={fps},format=yuv420p,'
                'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709')
    filters = (f'[0:v:0]{video_filter(prefix_info)},trim=duration={prefix_duration},setpts=PTS-STARTPTS[pv];'
               f'[1:v:0]{video_filter(outro_info, fill_frame=True)},trim=duration={outro_duration},setpts=PTS-STARTPTS[ov];'
               f'[{prefix_audio}]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={prefix_duration},asetpts=PTS-STARTPTS[pa];'
               f'[1:a:0]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={outro_duration},asetpts=PTS-STARTPTS[oa];'
               '[pv][pa][ov][oa]concat=n=2:v=1:a=1[v][a]')
    args += ['-filter_complex', filters, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'veryfast',
             '-crf', '18', '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-colorspace', 'bt709',
             '-color_primaries', 'bt709', '-color_trc', 'bt709', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '192k',
             '-movflags', '+faststart', str(dest)]
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if result.returncode:
        raise RuntimeError('片尾拼接失败：' + result.stderr[-1200:])
