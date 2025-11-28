import os
import sys
import json
import uuid
import time
import threading
import subprocess
import concurrent.futures
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
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'downloads')
TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'temp')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

jobs = {}

# ... (Keep format_timestamp and generate_srt functions as they were) ...
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
    # We will determine extensions dynamically during download
    audio_base = os.path.join(TEMP_FOLDER, f"{temp_id}_audio")
    video_base = os.path.join(TEMP_FOLDER, f"{temp_id}_video")
    opus_path = os.path.join(TEMP_FOLDER, f"{temp_id}_groq.opus")
    
    # Shared dictionary to store results from threads
    thread_results = {'audio_path': None, 'audio_ext': None, 'video_path': None}

    try:
        ffmpeg_loc = os.path.dirname(FFMPEG_BIN) if os.path.isabs(FFMPEG_BIN) else None
        ydl_common_opts = {'quiet': True, 'ffmpeg_location': ffmpeg_loc}

        # --- TASK 1: DOWNLOAD AUDIO ---
        jobs[job_id]['tasks']['audio_dl']['status'] = 'running'
        
        ydl_opts_audio = {
            **ydl_common_opts,
            'format': audio_quality,
            'outtmpl': audio_base + '.%(ext)s',
            'progress_hooks': [make_progress_hook(job_id, 'audio_dl')]
        }
        
        with YoutubeDL(ydl_opts_audio) as ydl:
            info = ydl.extract_info(url, download=True)
            thread_results['audio_ext'] = info['ext']
            thread_results['audio_path'] = f"{audio_base}.{info['ext']}"
            final_title = info.get('title', 'video')
        
        jobs[job_id]['tasks']['audio_dl']['status'] = 'done'
        jobs[job_id]['tasks']['audio_dl']['progress'] = '100'

        # --- PARALLEL TASKS ---
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
                    jobs[job_id]['tasks']['video_dl']['status'] = 'done'
                    return f"{video_base}.{v_info['ext']}"
            else:
                jobs[job_id]['tasks']['video_dl']['status'] = 'skipped'
                return None

        def task_prepare_groq_audio():
            if gen_subtitles and groq_api_key:
                jobs[job_id]['tasks']['conversion']['status'] = 'running'
                jobs[job_id]['tasks']['conversion']['detail'] = f'Encoding to Opus {GROQ_BITRATE}'
                # This conversion MUST happen for Groq API (needs 16k mono), but it is temporary
                cmd = f'"{FFMPEG_BIN}" -y -i "{thread_results["audio_path"]}" -map 0:a:0 -b:a {GROQ_BITRATE} -ac 1 -ar 16000 "{opus_path}" -v quiet'
                run_ffmpeg(cmd)
                jobs[job_id]['tasks']['conversion']['status'] = 'done'
                return opus_path
            else:
                jobs[job_id]['tasks']['conversion']['status'] = 'skipped'
                jobs[job_id]['tasks']['transcription']['status'] = 'skipped'
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CPU) as executor:
            future_video = executor.submit(task_download_video)
            future_audio_conv = executor.submit(task_prepare_groq_audio)
            
            thread_results['video_path'] = future_video.result()
            _ = future_audio_conv.result()

        # --- TRANSCRIPTION ---
        srt_path = None
        if gen_subtitles and os.path.exists(opus_path):
            jobs[job_id]['tasks']['transcription']['status'] = 'running'
            client = Groq(api_key=groq_api_key)
            with open(opus_path, "rb") as file:
                if translate_subs:
                    jobs[job_id]['tasks']['transcription']['detail'] = 'Translating...'
                    resp = client.audio.translations.create(
                        file=(opus_path, file.read()), model="whisper-large-v3", response_format="verbose_json", temperature=0.0
                    )
                else:
                    jobs[job_id]['tasks']['transcription']['detail'] = 'Transcribing...'
                    resp = client.audio.transcriptions.create(
                        file=(opus_path, file.read()), model="whisper-large-v3", response_format="verbose_json", temperature=0.0
                    )
            
            srt_content = generate_srt(resp.segments)
            srt_path = os.path.join(DOWNLOAD_FOLDER, f"{temp_id}.srt")
            with open(srt_path, "w", encoding="utf-8") as f: f.write(srt_content)
            os.remove(opus_path)
            jobs[job_id]['tasks']['transcription']['status'] = 'done'

        # --- FINALIZATION (SMART COPY) ---
        jobs[job_id]['tasks']['finalization']['status'] = 'running'
        jobs[job_id]['tasks']['finalization']['detail'] = 'Remuxing (Direct Stream Copy)...'

        maps = []
        cmd_build = f'"{FFMPEG_BIN}" -y '
        
        # Scenario 1: Video + Audio
        if thread_results['video_path']:
            final_ext = "mkv" # MKV is safest for direct stream copy of any codec mix
            final_path = os.path.join(DOWNLOAD_FOLDER, f"{temp_id}.{final_ext}")
            
            cmd_build += f'-i "{thread_results["video_path"]}" -i "{thread_results["audio_path"]}" '
            maps.append('-map 0:v:0 -map 1:a:0') # Map Video and Audio
            
            # Embed subtitles in video container
            if srt_path:
                cmd_build += f'-i "{srt_path}" '
                maps.append('-map 2:s:0')
                cmd_build += '-c:s srt ' # SRT is native to MKV

            # Copy codecs (0% CPU, 1:1 Quality/Size)
            cmd_build += f'-c:v copy -c:a copy '
        
        # Scenario 2: Audio Only
        else:
            final_ext = thread_results['audio_ext'] # Keep original extension (m4a, webm, etc)
            final_path = os.path.join(DOWNLOAD_FOLDER, f"{temp_id}.{final_ext}")
            
            cmd_build += f'-i "{thread_results["audio_path"]}" '
            maps.append('-map 0:a:0')
            
            # -vn removes any potential video streams (thumbnails) that confused players
            # -c:a copy preserves exact original data
            cmd_build += '-vn -c:a copy '

        # Execute
        cmd_build += " ".join(maps) + f' "{final_path}" -v quiet'
        run_ffmpeg(cmd_build)

        # Cleanup
        if thread_results['video_path'] and os.path.exists(thread_results['video_path']): os.remove(thread_results['video_path'])
        if os.path.exists(thread_results['audio_path']): os.remove(thread_results['audio_path'])

        jobs[job_id]['tasks']['finalization']['status'] = 'done'
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['result'] = {
            'filename': f"{temp_id}.{final_ext}",
            'srt_filename': f"{temp_id}.srt" if srt_path else None,
            'title': final_title,
            'size': f"{os.path.getsize(final_path) / (1024*1024):.2f} MB"
        }

    except Exception as e:
        print(f"Job Error: {e}")
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)

# ... (Routes remain the same) ...
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def get_info():
    # ... (Same as previous provided code) ...
    # Ensure you use the get_info from the previous full file I sent, 
    # ensuring it has the ffmpeg_location fix.
    url = request.json.get('url')
    try:
        ffmpeg_loc = os.path.dirname(FFMPEG_BIN) if os.path.isabs(FFMPEG_BIN) else None
        ydl_opts = {'quiet': True, 'ffmpeg_location': ffmpeg_loc}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        formats = info.get('formats', [])
        video_formats = []
        audio_formats = []
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none':
                size_mb = f.get('filesize', 0) / (1024 * 1024) if f.get('filesize') else 0
                label = f"{f.get('resolution', 'N/A')} ({f.get('ext')})"
                if size_mb > 0: label += f" - ~{size_mb:.1f}MB"
                video_formats.append({'id': f['format_id'], 'label': label, 'height': f.get('height', 0)})
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                 audio_formats.append({'id': f['format_id'], 'label': f"{f.get('abr', 'N/A')}kbps ({f.get('ext')})"})
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
