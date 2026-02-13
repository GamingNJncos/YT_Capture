# YT_Capture

A command-line tool for archiving YT Video content. This does not output videos, it isolates screenshots of the video based on frameskip settings and then the audio channel from that timestamp seperately.  It features smart frame deduplication (ignoring static screens) and high-fidelity audio stream copying.

This was designed with a focus on an odd usecase - vintage software preservation and recreation based on old footage. To recreate interfaces videos are very helpful as they actually show animations and on-click behaviors.  Static Images from old magazines etc aren't going to have comprehensive menu click throughs. Need a random frame from e3 1999 to show a special debug menu? Know there is that one thing in that movie when that particular scene happens?

Help isolate and extract frame by frame menu interactions, software settings, grandpas old bug or in game secret. Go forth and troll Speed Runners frame by frame.  Output format should be named in a way that it's easy to import the images into a LLM and create spiritual successors or "identicial" interfaces, graphics etc (assuming recording FPS is high enough). 


## Setup

1. Install Python 3.10+

2. Setup Environment:

    python -m venv venv
    source venv/bin/activate  # OR venv\Scripts\activate on Windows
    pip install -r requirements.txt

3. Install FFmpeg:
   - See INSTALL_FFMPEG.txt for instructions. This is required for audio extraction.

## Usage

Basic Syntax:
python yt_capture.py [URL] [OPTIONS]

### Valid Command Combinations

| Goal | Mode | Timing Argument |
| :--- | :--- | :--- |
| Extract Frames Only | --mode frame (Default) | --range 0:00-0:10 OR --full |
| Extract Audio Only | --mode audio | --range 0:00-0:10 OR --full |
| Extract Both | --mode both | --start-at 1:00 --extract-for 5s |

### Key Flags

- --range
  Specific timestamp range (e.g., 0:03-0:05 or 1:30-2:00).

- --full
  Process the entire video duration.

- --extract-for
  Extract X seconds starting from --start-at.

- --frameskip
  How many frames to skip between checks.
  * 0 = Check every frame (Slow, high precision).
  * 10 = Check every 10th frame (Default, good balance).
  * 60 = Check once per second (Fast scanning).

- --audio-format
  * native: (Default) Saves original stream (Opus/AAC). Best quality/size.
  * mp3: Transcodes to MP3 192k.

## Output Structure

The tool creates a unique folder for every video to prevent file collisions.

Folder Name: [Channel_Name].[Video_Title]
Example: LGR.Windows_95_First_Run

File Contents:
1. Source Manifest (source_url.txt)
   - Contains: URL, Date, Channel, Title.

2. Frame Images
   - Format: frame_Minute-Second-Millisecond.png
   - Example: frame_0-00-01_500.png

3. Audio Clips
   - Format: audio_StartSec-EndSec.ext
   - Example: audio_0.0-15.0.webm

## Notes

- If you interrupt the process and restart it with the same settings, it will skip existing files rather than overwriting them.
- To refresh a capture completely, delete the output folder or specific files.
