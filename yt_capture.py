import cv2
import os
import yt_dlp
import argparse
import sys
import re
import numpy as np
from datetime import timedelta

# --- 1. Branding & Help ---
def Banner():
    print(r'''
    
    [ PASTE YOUR ASCII ART HERE ]

    ''')

def print_usage():
    print(r'''
    Usage: python archiver.py [URL] [OPTIONS]

    CHEAT SHEET EXAMPLES:
    ---------------------
    1. Extract Frames (Default):
       python archiver.py "https://youtu.be/..." --range 0:03-0:05

    2. Extract Audio Only (High Quality Native):
       python archiver.py "https://youtu.be/..." --range 0:00-1:30 --mode audio

    3. Archive Everything (Audio + Frames) for a specific clip:
       python archiver.py "https://youtu.be/..." --start-at 5:20 --extract-for 10s --mode both

    4. High Precision Re-Run (Keep existing, add new frames):
       python archiver.py "https://youtu.be/..." --full --frameskip 2

    OPTIONS:
    --------
    --mode [frame|audio|both]   : What to extract (Default: frame)
    --range [start-end]         : Time range (e.g. 0:03-0:05)
    --full                      : Process entire video
    --start-at [time]           : Start point for fixed duration
    --extract-for [duration]    : Duration (e.g. 10s)
    --frameskip [int]           : 0=Every Frame, 10=Every 10th (Default: 10)
    --audio-format [type]       : native (best), mp3, wav
    ''')

# --- 2. Setup & Metadata ---
def sanitize_filename(name):
    # Remove invalid characters for directory names
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")

def setup_environment(url, args):
    print("--- Fetching Metadata ---")
    ydl_opts = {'quiet': True}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            channel = info.get('uploader', 'Unknown_Channel')
            title = info.get('title', 'Unknown_Video')
            
            # Smart Folder Naming: "Channel.Video_Title"
            safe_channel = sanitize_filename(channel)
            safe_title = sanitize_filename(title)
            # Limit length to avoid OS errors
            folder_name = f"{safe_channel}.{safe_title}"[:200]
            
            # Create Directory
            full_path = os.path.join(os.getcwd(), folder_name)
            os.makedirs(full_path, exist_ok=True)
            
            # Create Source Manifest
            manifest_path = os.path.join(full_path, "source_url.txt")
            if not os.path.exists(manifest_path):
                with open(manifest_path, "w") as f:
                    f.write(f"Source: {url}\nDate: {info.get('upload_date')}\nChannel: {channel}\nTitle: {title}")
            
            return full_path, info
            
    except Exception as e:
        print(f"Error fetching metadata: {e}")
        sys.exit(1)

# --- 3. Engines ---
def dhash(image, hashSize=8):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hashSize + 1, hashSize))
    diff = resized[:, 1:] > resized[:, :-1]
    return sum([2**i for (i, v) in enumerate(diff.flatten()) if v])

def time_str_to_seconds(ts):
    if not ts: return 0
    parts = list(map(int, ts.split(':')))
    if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2: return parts[0]*60 + parts[1]
    return parts[0]

def extract_audio(url, start, end, out_dir, fmt_mode):
    print(f"--- Audio Extraction ({fmt_mode}) ---")
    
    # Naming pattern: audio_Start-End.ext (Avoids overwriting different clips)
    # We use a temp template because we need to handle duplicates manually if needed
    filename_tmpl = f'{out_dir}/audio_%(section_start)s-%(section_end)s.%(ext)s'
    
    dl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'outtmpl': filename_tmpl,
    }

    if fmt_mode == 'mp3':
        dl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]
    elif fmt_mode == 'wav':
        dl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'wav'}]
    
    if start > 0 or end is not None:
        dl_opts['download_ranges'] = lambda info, ydl: [
            {'start_time': start, 'end_time': end if end else float('inf')}
        ]
        dl_opts['force_keyframes_at_cuts'] = False

    try:
        # Check if file might already exist is hard with yt-dlp dynamic extensions
        # but yt-dlp defaults to NOT overwriting if file exists (-nc) usually.
        # We explicitly set no-overwrites to be safe.
        dl_opts['nooverwrites'] = True
        
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])
        print(f"Audio saved to: {out_dir}")
    except Exception as e:
        print(f"Audio Error: {e}")

def process_video(url, start_sec, end_sec, out_dir, args):
    print(f"--- Frame Extraction ---")
    
    ydl_opts = {'format': 'bestvideo', 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info['url']
    except Exception as e:
        print(f"Stream Error: {e}")
        return

    cap = cv2.VideoCapture(video_url)
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)
    
    prev_frame_data = None
    last_saved_hash = None
    frame_idx = 0
    saved_count = 0
    skipped_existing = 0
    
    print(f"Scanning {out_dir}...")
    
    while True:
        ret, frame = cap.read()
        if not ret: break
        
        curr_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
        if end_sec and (curr_msec / 1000) > end_sec: break

        if frame_idx % (args.frameskip + 1) == 0:
            
            # Stage 1: Fast Pixel Check
            is_static = False
            if prev_frame_data is not None:
                diff = cv2.absdiff(frame, prev_frame_data)
                if (np.mean(diff) < args.scene_threshold):
                    is_static = True
            prev_frame_data = frame

            # Stage 2: Smart Dedup & Save
            if not is_static:
                curr_hash = dhash(frame)
                
                if last_saved_hash is None or bin(curr_hash ^ last_saved_hash).count('1') > args.sensitivity:
                    
                    # Generate Filename (Time based)
                    ts_str = str(timedelta(milliseconds=curr_msec))[:-3].replace(":", "-").replace(".", "_")
                    filename = f"frame_{ts_str}.png"
                    filepath = os.path.join(out_dir, filename)
                    
                    # COLLISION CHECK: Don't overwrite if we already archived this moment
                    if not os.path.exists(filepath):
                        cv2.imwrite(filepath, frame)
                        saved_count += 1
                        sys.stdout.write(f"\rCaptured: {saved_count} | Skipped(Exist): {skipped_existing} | {ts_str}")
                    else:
                        skipped_existing += 1
                        
                    last_saved_hash = curr_hash
                    sys.stdout.flush()
        
        frame_idx += 1
    
    cap.release()
    print(f"\nComplete. Saved {saved_count} new frames.")

# --- 4. Main Entry ---
def main():
    Banner()
    
    # Custom Help Trigger
    if len(sys.argv) == 1:
        print_usage()
        sys.exit(0)

    # Argument Definition
    parser = argparse.ArgumentParser(description="Media Extraction Utility", usage=argparse.SUPPRESS)
    parser.add_argument("url", help="YouTube Video URL")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--full", action="store_true", help="Process entire video")
    group.add_argument("--range", help="Time range (e.g., '0:03-0:05')")
    group.add_argument("--extract-for", type=str, help="Duration (e.g., '5s')")

    parser.add_argument("--mode", choices=['frame', 'audio', 'both'], default='frame')
    parser.add_argument("--start-at", help="Start time for --extract-for")
    parser.add_argument("--audio-format", choices=['native', 'mp3', 'wav'], default='native')
    
    parser.add_argument("--frameskip", type=int, default=10)
    parser.add_argument("--sensitivity", type=int, default=2)
    parser.add_argument("--scene-threshold", type=float, default=5.0)
    
    args = parser.parse_args()

    # 1. Setup Folder & Manifest
    out_dir, info = setup_environment(args.url, args)
    
    # 2. Parse Time
    start_sec = 0.0
    end_sec = None

    if args.range:
        s, e = args.range.split('-')
        start_sec = float(time_str_to_seconds(s))
        end_sec = float(time_str_to_seconds(e))
    elif args.extract_for:
        if not args.start_at:
            print("Error: --extract-for requires --start-at")
            sys.exit(1)
        start_sec = float(time_str_to_seconds(args.start_at))
        duration = float(args.extract_for.replace('s',''))
        end_sec = start_sec + duration
    
    # 3. Execute
    if args.mode in ['audio', 'both']:
        extract_audio(args.url, start_sec, end_sec, out_dir, args.audio_format)
        
    if args.mode in ['frame', 'both']:
        process_video(args.url, start_sec, end_sec, out_dir, args)

if __name__ == "__main__":
    main()