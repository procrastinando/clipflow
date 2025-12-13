import os
import sys
import json
import uuid
import time
import re
import threading
import subprocess
import concurrent.futures
import shutil
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from yt_dlp import YoutubeDL
from groq import Groq

# --- PATH CONFIGURATION ---
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    FFMPEG_BIN = os.path.join(BASE_DIR, 'ffmpeg.exe')
    TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
    STATIC_DIR = os.path.join(BASE_DIR, 'static')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    local_ffmpeg = os.path.join(BASE_DIR, 'ffmpeg.exe')
    FFMPEG_BIN = local_ffmpeg if os.path.exists(local_ffmpeg) else 'ffmpeg'
    TEMPLATE_DIR = 'templates'
    STATIC_DIR = 'static'

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

# --- CONFIG ---
MAX_CPU = 4
GROQ_BITRATE = '27k'
DOWNLOAD_FOLDER = os.path.abspath('/youtube') 
TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'temp')

# Ensure directories exist
try:
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
except PermissionError:
    print(f"ERROR: Permission denied creating {DOWNLOAD_FOLDER}. Please run as Administrator/Root or change permissions.")
    
os.makedirs(TEMP_FOLDER, exist_ok=True)

jobs = {}

# --- UTILS ---
def sanitize_filename(name):
    """
    Sanitizes a string to be safe for filenames/directories.
    Removes characters like / \ : * ? " < > |
    """
    if not name: return "untitled"
    s = re.sub(r'[\\/*?:"<>|]', '', name)
    s = s.strip()
    return s if s else "untitled"

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

def generate_srt(segments):
    srt_content = ""
    for i, segment in enumerate(segments):
        start = format_timestamp(segment['start'])
        end = format_timestamp(segment['end'])
        text = segment['text'].strip()
        srt_content += f"{i + 1}\n{start} --> {end}\n{text}\n\n"
    return srt_content

def run_ffmpeg(command):
    subprocess.run(command, shell=True, check=True)

def make_progress_hook(job_id, task_key):
    def progress_hook(d):
        if d['status'] == 'downloading':
            try:
                p = d.get('_percent_str', '0%').replace('%','')
                jobs[job_id]['tasks'][task_key]['progress'] = p
                jobs[job_id]['tasks'][task_key]['detail'] = f"{d.get('_percent_str')} @ {d.get('_speed_str', 'N/A')}"
                jobs[job_id]['tasks'][task_key]['status'] = 'running'
            except: 
                pass
        elif d['status'] == 'finished':
            jobs[job_id]['tasks'][task_key]['progress'] = '100'
            jobs[job_id]['tasks'][task_key]['status'] = 'done'
            jobs[job_id]['tasks'][task_key]['detail'] = 'Download complete'
    return progress_hook

def process_conversion(job_id, data):
    jobs[job_id]['status'] = 'running'
    
    url = data['url']
    video_quality = data['video_quality']
    audio_quality = data['audio_quality'] 
    groq_api_key = data['groq_api_key']
    gen_subtitles = data['gen_subtitles']
    translate_subs = data.get('translate_subs', False)
    
    temp_id = str(uuid.uuid4())
    audio_base = os.path.join(TEMP_FOLDER, f"{temp_id}_audio")
    video_base = os.path.join(TEMP_FOLDER, f"{temp_id}_video")
    opus_path = os.path.join(TEMP_FOLDER, f"{temp_id}_groq.opus")
    
    meta_info = {'channel': 'Unknown', 'title': 'Video', 'height': None, 'abr': None}
    thread_results = {'audio_path': None, 'audio_ext': None, 'video_path': None}

    try:
        ffmpeg_loc = os.path.dirname(FFMPEG_BIN) if os.path.isabs(FFMPEG_BIN) else None
        ydl_common_opts = {
            'quiet': True, 
            'ffmpeg_location': ffmpeg_loc,
            'noplaylist': True,
            'no_warnings': True
        }

        # --- TASK 1: DOWNLOAD AUDIO ---
        jobs[job_id]['tasks']['audio_dl']['status'] = 'running'
        
        ydl_opts_audio = {
            **ydl_common_opts,
            'format': audio_quality, 
            'outtmpl': audio_base + '.%(ext)s',
            'progress_hooks': [make_progress_hook(job_id, 'audio_dl')]
        }
        
        with YoutubeDL(ydl_opts_audio) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
            except Exception as dl_err:
                raise Exception(f"Download failed. Please update yt-dlp. Error: {str(dl_err)}")

            if 'entries' in info: info = info['entries'][0]

            thread_results['audio_ext'] = info['ext']
            thread_results['audio_path'] = f"{audio_base}.{info['ext']}"
            
            meta_info['title'] = info.get('title', 'video')
            meta_info['channel'] = info.get('uploader', 'Unknown_Channel')
            meta_info['abr'] = int(info.get('abr', 0)) if info.get('abr') else 0

        jobs[job_id]['tasks']['audio_dl']['status'] = 'done'
        jobs[job_id]['tasks']['audio_dl']['progress'] = '100'

        # --- PARALLEL EXECUTION BLOCK ---
        def task_download_video():
            if video_quality != 'none':
                jobs[job_id]['tasks']['video_dl']['status'] = 'running'
                ydl_opts_video = {
                    **ydl_common_opts,
                    'format': video_quality,
                    'outtmpl': video_base + '.%(ext)s',
                    'progress_hooks': [make_progress_hook(job_id, 'video_dl')]
                }
                with YoutubeDL(ydl_opts_video) as ydl:
                    v_info = ydl.extract_info(url, download=True)
                    if 'entries' in v_info: v_info = v_info['entries'][0]
                    
                    meta_info['height'] = v_info.get('height')
                    jobs[job_id]['tasks']['video_dl']['status'] = 'done'
                    return f"{video_base}.{v_info['ext']}"
            else:
                jobs[job_id]['tasks']['video_dl']['status'] = 'skipped'
                return None

        def task_audio_pipeline():
            audio_for_transcription = None
            
            # Sub-Task A: Convert/Prepare Audio
            if gen_subtitles and groq_api_key:
                jobs[job_id]['tasks']['conversion']['status'] = 'running'
                raw_audio_path = thread_results["audio_path"]
                
                try:
                    file_size_bytes = os.path.getsize(raw_audio_path)
                    limit_bytes = 25 * 1024 * 1024 

                    if file_size_bytes > limit_bytes:
                        jobs[job_id]['tasks']['conversion']['detail'] = f'Compressing (>25MB) to Opus...'
                        cmd = f'"{FFMPEG_BIN}" -y -i "{raw_audio_path}" -map 0:a:0 -b:a {GROQ_BITRATE} -ac 1 -ar 16000 "{opus_path}" -v quiet'
                        run_ffmpeg(cmd)
                        audio_for_transcription = opus_path
                    else:
                        jobs[job_id]['tasks']['conversion']['detail'] = 'Using original audio (<25MB)'
                        audio_for_transcription = raw_audio_path
                    
                    jobs[job_id]['tasks']['conversion']['status'] = 'done'
                except Exception as e:
                    jobs[job_id]['tasks']['conversion']['status'] = 'error'
                    raise e
            else:
                jobs[job_id]['tasks']['conversion']['status'] = 'skipped'
                jobs[job_id]['tasks']['transcription']['status'] = 'skipped'
                return None

            # Sub-Task B: Transcribe
            srt_generated_path = None
            if audio_for_transcription and os.path.exists(audio_for_transcription):
                jobs[job_id]['tasks']['transcription']['status'] = 'running'
                try:
                    client = Groq(api_key=groq_api_key)
                    
                    with open(audio_for_transcription, "rb") as file:
                        filename_for_api = os.path.basename(audio_for_transcription)
                        if translate_subs:
                            jobs[job_id]['tasks']['transcription']['detail'] = 'Translating...'
                            resp = client.audio.translations.create(
                                file=(filename_for_api, file.read()), 
                                model="whisper-large-v3", 
                                response_format="verbose_json", 
                                temperature=0.0
                            )
                        else:
                            jobs[job_id]['tasks']['transcription']['detail'] = 'Transcribing...'
                            resp = client.audio.transcriptions.create(
                                file=(filename_for_api, file.read()), 
                                model="whisper-large-v3", 
                                response_format="verbose_json", 
                                temperature=0.0
                            )
                    
                    srt_content = generate_srt(resp.segments)
                    srt_generated_path = os.path.join(TEMP_FOLDER, f"{temp_id}.srt")
                    with open(srt_generated_path, "w", encoding="utf-8") as f: f.write(srt_content)
                    
                    jobs[job_id]['tasks']['transcription']['status'] = 'done'

                except Exception as e:
                    jobs[job_id]['tasks']['transcription']['status'] = 'error'
                    print(f"Transcription Error: {e}")
                
                if audio_for_transcription == opus_path and os.path.exists(opus_path):
                    os.remove(opus_path)
            
            return srt_generated_path

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CPU) as executor:
            future_video = executor.submit(task_download_video)
            future_subs = executor.submit(task_audio_pipeline)
            
            thread_results['video_path'] = future_video.result()
            srt_path_temp = future_subs.result()

        # --- FINALIZATION ---
        jobs[job_id]['tasks']['finalization']['status'] = 'running'
        jobs[job_id]['tasks']['finalization']['detail'] = 'Saving to disk...'

        safe_channel = sanitize_filename(meta_info['channel'])
        safe_title = sanitize_filename(meta_info['title'])
        
        # DETERMINE FOLDER TYPE: 'video' or 'audio'
        folder_type = 'video' if thread_results['video_path'] else 'audio'
        
        # Path: /youtube/{type}/{channel}
        channel_dir = os.path.join(DOWNLOAD_FOLDER, folder_type, safe_channel)
        os.makedirs(channel_dir, exist_ok=True)

        maps = []
        cmd_build = f'"{FFMPEG_BIN}" -y '
        
        if thread_results['video_path']:
            # VIDEO MODE
            final_ext = "mkv"
            quality_suffix = f"_{meta_info['height']}" if meta_info['height'] else "_video"
            final_filename = f"{safe_title}{quality_suffix}.{final_ext}"
            final_path = os.path.join(channel_dir, final_filename)
            
            cmd_build += f'-i "{thread_results["video_path"]}" -i "{thread_results["audio_path"]}" '
            maps.append('-map 0:v:0 -map 1:a:0')
            
            if srt_path_temp and os.path.exists(srt_path_temp):
                cmd_build += f'-i "{srt_path_temp}" '
                maps.append('-map 2:s:0')
                cmd_build += '-c:s srt '
            
            cmd_build += f'-c:v copy -c:a copy '
        else:
            # AUDIO MODE
            final_ext = thread_results['audio_ext']
            quality_suffix = f"_{meta_info['abr']}" if meta_info['abr'] else "_audio"
            final_filename = f"{safe_title}{quality_suffix}.{final_ext}"
            final_path = os.path.join(channel_dir, final_filename)
            
            cmd_build += f'-i "{thread_results["audio_path"]}" '
            maps.append('-map 0:a:0')
            cmd_build += '-vn -c:a copy '

        cmd_build += " ".join(maps) + f' "{final_path}" -v quiet'
        run_ffmpeg(cmd_build)

        # Handle standalone SRT file move
        final_srt_relative = None
        if srt_path_temp and os.path.exists(srt_path_temp):
            srt_filename = f"{safe_title}.srt"
            final_srt_path = os.path.join(channel_dir, srt_filename)
            shutil.move(srt_path_temp, final_srt_path)
            # Create relative path: type/channel/file.srt
            final_srt_relative = os.path.join(folder_type, safe_channel, srt_filename).replace("\\", "/")

        # Cleanup temp files
        if thread_results['video_path'] and os.path.exists(thread_results['video_path']): os.remove(thread_results['video_path'])
        if os.path.exists(thread_results['audio_path']): os.remove(thread_results['audio_path'])

        # Create relative path: type/channel/file.ext
        relative_filename = os.path.join(folder_type, safe_channel, final_filename).replace("\\", "/")
        
        jobs[job_id]['tasks']['finalization']['status'] = 'done'
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result'] = {
            'filename': relative_filename,
            'srt_filename': final_srt_relative,
            'title': meta_info['title'],
            'size': f"{os.path.getsize(final_path) / (1024*1024):.2f} MB"
        }

    except Exception as e:
        print(f"Job Error: {e}")
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def get_info():
    url = request.json.get('url')
    try:
        ffmpeg_loc = os.path.dirname(FFMPEG_BIN) if os.path.isabs(FFMPEG_BIN) else None
        ydl_opts = {'quiet': True, 'ffmpeg_location': ffmpeg_loc, 'noplaylist': True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        if 'entries' in info: info = info['entries'][0]

        formats = info.get('formats', [])
        video_formats = []
        audio_formats = []
        for f in formats:
            # Video only
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none':
                size_mb = f.get('filesize', 0) / (1024 * 1024) if f.get('filesize') else 0
                label = f"{f.get('resolution', 'N/A')} ({f.get('ext')})"
                if size_mb > 0: label += f" - ~{size_mb:.1f}MB"
                video_formats.append({'id': f['format_id'], 'label': label, 'height': f.get('height', 0)})
            
            # Audio only
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                 lang = f.get('language', 'default')
                 if not lang: lang = 'default'
                 
                 channels = f.get('audio_channels')
                 ch_label = "5.1" if channels and channels > 2 else "Stereo"
                 
                 label = f"[{lang}] {ch_label} - {f.get('abr', 'N/A')}kbps ({f.get('ext')})"
                 
                 audio_formats.append({'id': f['format_id'], 'label': label})
                 
        video_formats.sort(key=lambda x: x['height'], reverse=True)
        return jsonify({
            'title': info.get('title'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'video_formats': video_formats,
            'audio_formats': audio_formats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/convert', methods=['POST'])
def convert():
    data = request.json
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'queued',
        'tasks': {
            'audio_dl': {'status': 'pending', 'progress': '0', 'detail': 'Waiting...'},
            'video_dl': {'status': 'pending', 'progress': '0', 'detail': 'Waiting...'},
            'conversion': {'status': 'pending', 'detail': 'Waiting...'},
            'transcription': {'status': 'pending', 'detail': 'Waiting...'},
            'finalization': {'status': 'pending', 'detail': 'Waiting...'}
        }
    }
    thread = threading.Thread(target=process_conversion, args=(job_id, data))
    thread.start()
    return jsonify({'job_id': job_id})

@app.route('/api/status/<job_id>')
def status(job_id):
    def generate():
        while True:
            if job_id not in jobs: break
            job = jobs[job_id]
            yield f"data: {json.dumps(job)}\n\n"
            if job['status'] in ['completed', 'error']: break
            time.sleep(0.5) 
    return Response(generate(), mimetype='text/event-stream')

@app.route('/download/<path:filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    debug_mode = not getattr(sys, 'frozen', False)
    app.run(host='0.0.0.0', debug=debug_mode, port=5000)