from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import re
import json
from datetime import datetime

# Flask app initialization
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit

# Download folder
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Global progress variable
download_progress = {'percent': 0, 'status': 'idle', 'speed': 'N/A', 'eta': 'N/A'}

def get_video_info(url):
    """Fetch video metadata without downloading"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            formats = []
            seen_resolutions = set()
            # Get video+audio formats
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    height = f.get('height', 0)
                    if height and height not in seen_resolutions:
                        seen_resolutions.add(height)
                        formats.append({
                            'quality': f'{height}p',
                            'format_id': f['format_id'],
                            'ext': f['ext'],
                            'filesize': f.get('filesize', 0)
                        })
            # Sort by quality (highest first)
            formats.sort(key=lambda x: int(x['quality'].replace('p', '') or 0), reverse=True)

            # Audio-only formats
            audio_formats = []
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    audio_formats.append({
                        'quality': f"{f.get('abr', 128)} kbps",
                        'format_id': f['format_id'],
                        'ext': f['ext'],
                        'filesize': f.get('filesize', 0)
                    })

            return {
                'title': info.get('title', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'views': info.get('view_count', 0),
                'formats': formats[:10],
                'audio_formats': audio_formats[:5]
            }
    except Exception as e:
        print(f"Error fetching info: {e}")
        return None

def progress_hook(d):
    """Progress hook for yt-dlp"""
    if d['status'] == 'downloading':
        download_progress['percent'] = d.get('_percent_str', '0%').replace('%', '').strip()
        download_progress['speed'] = d.get('_speed_str', 'N/A')
        download_progress['eta'] = d.get('_eta_str', 'N/A')
        download_progress['status'] = 'downloading'
    elif d['status'] == 'finished':
        download_progress['status'] = 'processing'
        download_progress['percent'] = '100'

def download_video(url, format_id, quality_type='video'):
    """Download video/audio with given format"""
    ydl_opts = {
        'format': format_id,
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'ignoreerrors': True,
        'progress_hooks': [progress_hook],
    }
    if quality_type == 'audio':
        ydl_opts.update({
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'format': 'bestaudio/best',
        })
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if quality_type == 'audio':
                filename = filename.rsplit('.', 1)[0] + '.mp3'
            download_progress['status'] = 'completed'
            return filename
    except Exception as e:
        download_progress['status'] = 'error'
        download_progress['error'] = str(e)
        return None

# ----- Routes -----

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_info', methods=['POST'])
def get_info():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    info = get_video_info(url)
    if not info:
        return jsonify({'error': 'Could not fetch video info. Check URL.'}), 400
    return jsonify(info)

@app.route('/download', methods=['POST'])
def download():
    url = request.json.get('url', '').strip()
    format_id = request.json.get('format_id', 'best')
    quality_type = request.json.get('quality_type', 'video')
    if not url:
        return jsonify({'error': 'No URL'}), 400
    filename = download_video(url, format_id, quality_type)
    if not filename:
        return jsonify({'error': 'Download failed'}), 400
    return jsonify({'success': True, 'filename': os.path.basename(filename)})

@app.route('/download_file/<filename>')
def download_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404

@app.route('/progress')
def progress():
    return jsonify(download_progress)

# ----- Run -----
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
