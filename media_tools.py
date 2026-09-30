"""Non-destructive clip models and FFmpeg command construction."""
import json,math,subprocess,shutil
from dataclasses import dataclass,asdict
from functools import lru_cache
from pathlib import Path

VIDEO_FORMATS={
 'mp4':('libx264','aac',['-crf','20','-movflags','+faststart']),
 'mkv':('libx264','aac',['-crf','20']),
 'mov':('libx264','aac',['-crf','20','-movflags','+faststart']),
 'webm':('libvpx-vp9','libopus',['-crf','30','-b:v','0']),
 'avi':('mpeg4','libmp3lame',['-q:v','3']),
 'mpg':('mpeg2video','mp2',['-q:v','3']),
 'ogv':('libtheora','libvorbis',['-q:v','7']),
 'gif':('gif',None,[])}
AUDIO_FORMATS={'mp3':('libmp3lame',['-q:a','2']),'flac':('flac',[]),'wav':('pcm_s16le',[]),
 'ogg':('libvorbis',['-q:a','6']),'opus':('libopus',['-b:a','160k']),
 'm4a':('aac',['-b:a','192k']),'aac':('aac',['-b:a','192k']),
 'aiff':('pcm_s16be',[]),'ac3':('ac3',['-b:a','384k'])}

@lru_cache(maxsize=1)
def encoders():
    if not shutil.which('ffmpeg'):return set()
    text=subprocess.run(['ffmpeg','-hide_banner','-encoders'],capture_output=True,text=True,timeout=10,check=True).stdout
    return {line.split()[1] for line in text.splitlines() if len(line.split())>=2 and len(line.split()[0])==6}

def video_formats():return [fmt for fmt,(video,audio,extra) in VIDEO_FORMATS.items() if video in encoders() and (not audio or audio in encoders())]
def audio_formats():return [fmt for fmt,(codec,extra) in AUDIO_FORMATS.items() if codec in encoders()]

def probe(path):
    result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(Path(path).resolve())],capture_output=True,text=True,timeout=30)
    if result.returncode:raise ValueError(result.stderr.strip() or 'Could not read media metadata. Install ffmpeg/ffprobe.')
    data=json.loads(result.stdout);video=next((s for s in data.get('streams',[]) if s.get('codec_type')=='video'),None)
    duration=float(data.get('format',{}).get('duration') or (video or {}).get('duration') or 0)
    if not math.isfinite(duration) or duration<=0:raise ValueError('This media has no finite duration.')
    return {'duration':duration,'width':(video or {}).get('width',0),'height':(video or {}).get('height',0),
            'audio':any(s.get('codec_type')=='audio' for s in data.get('streams',[])),'video':bool(video)}

@dataclass
class Clip:
    path:str
    source_in:float
    source_out:float
    start:float
    info:dict
    @property
    def duration(self):return self.source_out-self.source_in
    @property
    def end(self):return self.start+self.duration
    def validate(self):
        if not all(math.isfinite(v) for v in (self.source_in,self.source_out,self.start)):raise ValueError('Invalid clip times.')
        if self.start<0 or self.source_in<0 or self.duration<.04 or self.source_out>self.info['duration']+.03:raise ValueError('Clip trim is outside its source.')

def validate_timeline(clips):
    if not clips:raise ValueError('Add at least one clip.')
    ordered=sorted(clips,key=lambda c:c.start);end=0.
    for clip in ordered:
        clip.validate()
        if clip.start<end-.002:raise ValueError('Clips overlap. Move them apart or stitch the timeline.')
        end=clip.end
    return ordered

def split_clip(clip,position):
    offset=position-clip.start
    if offset<.04 or clip.duration-offset<.04:raise ValueError('Place the playhead inside the selected clip.')
    return [Clip(clip.path,clip.source_in,clip.source_in+offset,clip.start,dict(clip.info)),
            Clip(clip.path,clip.source_in+offset,clip.source_out,position,dict(clip.info))]

def stitch(clips):
    cursor=0.
    for clip in sorted(clips,key=lambda c:c.start):clip.start=cursor;cursor=clip.end

def video_codec_args(fmt):
    video,audio,extra=VIDEO_FORMATS[fmt]
    return ['-c:v',video,*extra]+(['-c:a',audio] if audio else ['-an'])+(['-pix_fmt','yuv420p'] if fmt!='gif' else [])

def timeline_args(clips,fmt='mp4',width=1280,height=720,fps=30):
    clips=validate_timeline(clips)
    if fmt not in VIDEO_FORMATS:raise ValueError('Unsupported video format.')
    if not (16<=width<=7680 and 16<=height<=4320 and 1<=fps<=60):raise ValueError('Invalid export dimensions or frame rate.')
    width=width//2*2;height=height//2*2;audio=fmt!='gif';args=[];filters=[];labels=[];cursor=0.;segment=0
    def label():
        nonlocal segment
        number=segment;segment+=1;labels.append(f'[v{number}]'+(f'[a{number}]' if audio else ''));return number
    for index,clip in enumerate(clips):
        if clip.start>cursor+.002:
            number=label();gap=clip.start-cursor
            filters.append(f'color=c=black:s={width}x{height}:r={fps}:d={gap:.6f},setpts=PTS-STARTPTS[v{number}]')
            if audio:filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={gap:.6f},asetpts=PTS-STARTPTS[a{number}]')
        args+=['-ss',f'{clip.source_in:.6f}','-t',f'{clip.duration:.6f}','-i',str(Path(clip.path).resolve())]
        number=label()
        filters.append(f'[{index}:v:0]setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p,tpad=stop_mode=clone:stop_duration={clip.duration:.6f},trim=duration={clip.duration:.6f}[v{number}]')
        if audio:
            source=f'[{index}:a:0]aresample=48000,aformat=channel_layouts=stereo' if clip.info.get('audio') else 'anullsrc=r=48000:cl=stereo'
            filters.append(f'{source},asetpts=PTS-STARTPTS,apad,atrim=duration={clip.duration:.6f}[a{number}]')
        cursor=clip.end
    filters.append(''.join(labels)+f'concat=n={segment}:v=1:a={int(audio)}[v]'+('[a]' if audio else ''))
    args+=['-filter_complex',';'.join(filters),'-map','[v]']+(['-map','[a]'] if audio else [])
    return args+video_codec_args(fmt)+['-t',f'{cursor:.6f}']

def conversion_args(path,fmt):
    args=['-i',str(Path(path).resolve())]
    if fmt in AUDIO_FORMATS:
        codec,extra=AUDIO_FORMATS[fmt];return args+['-vn','-c:a',codec,*extra]
    if fmt in VIDEO_FORMATS:
        return args+['-map','0:v:0','-map','0:a:0?','-vf','scale=trunc(iw/2)*2:trunc(ih/2)*2']+video_codec_args(fmt)
    raise ValueError('Unsupported media output format.')
