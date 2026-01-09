import asyncio
import json
import os
import subprocess
from typing import List, Optional

from app.models import AudioTrack


async def _drain_stderr(stream, container: list):
    """Read stderr in background to prevent buffer overflow."""
    while True:
        line = await stream.readline()
        if not line:
            break
        container.append(line.decode('utf-8', errors='ignore'))


async def get_audio_tracks(video_path: str) -> List[AudioTrack]:
    """Get all audio tracks from a video file using ffprobe."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        '-select_streams', 'a',
        video_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        raise Exception(f"ffprobe failed: {stderr.decode()}")
    
    data = json.loads(stdout.decode())
    tracks = []
    
    for i, stream in enumerate(data.get('streams', [])):
        # IMPORTANT: Use enumeration index 'i' for audio stream mapping
        # stream.get('index') is the GLOBAL stream index (video=0, audio1=1, audio2=2...)
        # But ffmpeg -map 0:a:N expects the RELATIVE audio stream index (0, 1, 2...)
        track = AudioTrack(
            index=i,  # Use relative audio index for ffmpeg -map 0:a:N
            codec=stream.get('codec_name', 'unknown'),
            language=stream.get('tags', {}).get('language'),
            title=stream.get('tags', {}).get('title'),
            channels=stream.get('channels', 2),
            default=stream.get('disposition', {}).get('default', 0) == 1
        )
        tracks.append(track)
    
    return tracks


async def extract_audio(
    video_path: str, 
    output_path: str, 
    track_index: int = 0,
    progress_callback=None
) -> str:
    """Extract audio track from video file to WAV format (16kHz mono for Whisper)."""
    cmd = [
        'ffmpeg',
        '-y',  # Overwrite output
        '-i', video_path,
        '-map', f'0:a:{track_index}',  # Select specific audio track
        '-vn',  # No video
        '-acodec', 'pcm_s16le',  # 16-bit PCM
        '-ar', '16000',  # 16kHz sample rate (Whisper requirement)
        '-ac', '1',  # Mono
        '-progress', 'pipe:1',  # Progress to stdout
        output_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Get video duration first for progress tracking
    duration = await get_video_duration(video_path)
    
    # Start draining stderr in background to prevent buffer overflow
    stderr_lines = []
    stderr_task = asyncio.create_task(_drain_stderr(process.stderr, stderr_lines))
    
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        
        line_str = line.decode('utf-8', errors='ignore').strip()
        
        # Parse progress from ffmpeg output
        # Format: out_time_ms=123456789
        if line_str.startswith('out_time_ms='):
            try:
                current_ms = int(line_str.split('=')[1])
                current_sec = current_ms / 1000000
                if duration > 0 and progress_callback:
                    progress = min(100, (current_sec / duration) * 100)
                    await progress_callback(progress)
            except:
                pass
    
    await stderr_task  # Wait for stderr to be fully consumed
    await process.wait()
    
    if process.returncode != 0:
        raise Exception(f"ffmpeg failed: {''.join(stderr_lines)}")
    
    return output_path


async def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await process.communicate()
    
    try:
        return float(stdout.decode().strip())
    except:
        return 0.0


async def embed_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    progress_callback=None
) -> str:
    """Embed SRT subtitles into video file (soft subtitles, no re-encoding).
    
    IMPORTANT: Removes all original subtitle tracks and only keeps the new generated ones.
    """
    cmd = [
        'ffmpeg',
        '-y',
        '-i', video_path,
        '-i', srt_path,
        '-map', '0:v',         # Take only video from source
        '-map', '0:a',         # Take only audio from source (all audio tracks)
        '-map', '1:0',         # Take subtitles from SRT file (second input)
        '-c:v', 'copy',        # Copy video without re-encoding
        '-c:a', 'copy',        # Copy audio without re-encoding
        '-c:s', 'srt',         # Subtitle codec
        '-metadata:s:s:0', 'language=rus',  # Set subtitle language
        '-metadata:s:s:0', 'title=AI Generated',  # Mark as AI generated
        '-disposition:s:0', 'default',  # Set as default subtitle track
        '-progress', 'pipe:1',
        output_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    duration = await get_video_duration(video_path)
    
    # Start draining stderr in background to prevent buffer overflow
    stderr_lines = []
    stderr_task = asyncio.create_task(_drain_stderr(process.stderr, stderr_lines))
    
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        
        line_str = line.decode('utf-8', errors='ignore').strip()
        
        if line_str.startswith('out_time_ms='):
            try:
                current_ms = int(line_str.split('=')[1])
                current_sec = current_ms / 1000000
                if duration > 0 and progress_callback:
                    progress = min(100, (current_sec / duration) * 100)
                    await progress_callback(progress)
            except:
                pass
    
    await stderr_task  # Wait for stderr to be fully consumed
    await process.wait()
    
    if process.returncode != 0:
        raise Exception(f"ffmpeg failed: {''.join(stderr_lines)}")
    
    return output_path


async def get_video_resolution(video_path: str) -> tuple[int, int]:
    """Get video resolution (width, height)."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        video_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, _ = await process.communicate()
    
    try:
        data = json.loads(stdout.decode())
        stream = data.get('streams', [{}])[0]
        return (stream.get('width', 1920), stream.get('height', 1080))
    except:
        return (1920, 1080)


async def create_streaming_version(
    video_path: str,
    srt_path: str,
    output_path: str,
    max_height: int = 1080,
    progress_callback=None,
    is_cancelled=None  # Callback to check if job was cancelled
) -> str:
    """
    Create a streaming-ready MP4 version by remuxing (not re-encoding).
    
    This is MUCH faster than burning subtitles:
    - Video: copy without re-encoding (instant)
    - Audio: convert to AAC for browser compatibility
    - Subtitles: separate WebVTT file for HTML5 <track> element
    """
    duration = await get_video_duration(video_path)
    
    # Fast remux: copy video, convert audio to AAC stereo
    # -ac 2 ensures proper downmix from 5.1 to stereo
    cmd = [
        'ffmpeg',
        '-y',
        '-i', video_path,
        '-c:v', 'copy',        # Copy video without re-encoding (FAST!)
        '-c:a', 'aac',         # Convert audio to AAC for browser compatibility
        '-ac', '2',            # Downmix to stereo (proper 5.1 -> 2.0 conversion)
        '-b:a', '192k',        # Good quality audio
        '-movflags', '+faststart',  # Web optimization - metadata at start
        '-map', '0:v:0',       # First video stream
        '-map', '0:a:0',       # First audio stream
        '-progress', 'pipe:1',
        output_path
    ]
    
    print(f"[STREAMING] Starting fast remux: {video_path} -> {output_path}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Start draining stderr in background to prevent buffer overflow
    stderr_lines = []
    stderr_task = asyncio.create_task(_drain_stderr(process.stderr, stderr_lines))
    
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        
        # Check if job was cancelled
        if is_cancelled and is_cancelled():
            stderr_task.cancel()
            process.kill()
            await process.wait()
            print(f"[STREAMING] Cancelled: {output_path}")
            raise Exception("Job cancelled")
        
        line_str = line.decode('utf-8', errors='ignore').strip()
        
        if line_str.startswith('out_time_ms='):
            try:
                current_ms = int(line_str.split('=')[1])
                current_sec = current_ms / 1000000
                if duration > 0 and progress_callback:
                    progress = min(100, (current_sec / duration) * 100)
                    await progress_callback(progress)
            except:
                pass
    
    await stderr_task  # Wait for stderr to be fully consumed
    await process.wait()
    
    if process.returncode != 0:
        error_msg = ''.join(stderr_lines)
        print(f"[STREAMING] FFmpeg failed: {error_msg}")
        raise Exception(f"ffmpeg remux failed: {error_msg}")
    
    # Also create WebVTT file for HTML5 subtitles
    vtt_path = srt_path.rsplit('.', 1)[0] + '.vtt'
    await convert_srt_to_vtt(srt_path, vtt_path)
    
    print(f"[STREAMING] Fast remux complete: {output_path}")
    return output_path


async def convert_srt_to_vtt(srt_path: str, vtt_path: str) -> str:
    """
    Convert SRT subtitle file to WebVTT format for HTML5 <track> element.
    
    SRT format:
    1
    00:00:01,234 --> 00:00:04,567
    Text here
    
    WebVTT format:
    WEBVTT
    
    00:00:01.234 --> 00:00:04.567
    Text here
    """
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        # Start with WebVTT header
        vtt_lines = ['WEBVTT', '']
        
        # Process SRT content
        blocks = srt_content.strip().split('\n\n')
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 2:
                # Skip sequence number (first line if it's a number)
                start_idx = 0
                if lines[0].strip().isdigit():
                    start_idx = 1
                
                if start_idx < len(lines):
                    # Convert timestamp: 00:00:01,234 --> 00:00:04,567
                    # to WebVTT:         00:00:01.234 --> 00:00:04.567
                    timestamp_line = lines[start_idx].replace(',', '.')
                    vtt_lines.append(timestamp_line)
                    
                    # Add text lines
                    for text_line in lines[start_idx + 1:]:
                        vtt_lines.append(text_line)
                    
                    vtt_lines.append('')  # Empty line between cues
        
        with open(vtt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(vtt_lines))
        
        print(f"[STREAMING] Created WebVTT: {vtt_path}")
        return vtt_path
        
    except Exception as e:
        print(f"[STREAMING] Failed to convert SRT to VTT: {e}")
        raise


