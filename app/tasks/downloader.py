import asyncio
import os
import re
import subprocess
from typing import Optional, Callable
import httpx

from app.config import settings


async def download_url(url: str, dest_dir: str, progress_callback: Optional[Callable] = None) -> str:
    """Download a file from URL and return the local path."""
    # Extract filename from URL or Content-Disposition header
    filename = None
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # First, get headers to determine filename
        response = await client.head(url)
        
        # Try Content-Disposition header
        content_disposition = response.headers.get('content-disposition', '')
        if 'filename=' in content_disposition:
            match = re.search(r'filename[*]?=["\']?([^"\';\s]+)', content_disposition)
            if match:
                filename = match.group(1)
        
        # Fallback to URL path
        if not filename:
            filename = url.split('/')[-1].split('?')[0]
            if not filename:
                filename = 'video.mp4'
        
        dest_path = os.path.join(dest_dir, filename)
        
        # Download with streaming
        async with client.stream('GET', url) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(dest_path, 'wb') as f:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        await progress_callback(downloaded / total_size * 100)
    
    return dest_path


async def download_torrent(
    source: str, 
    dest_dir: str, 
    is_magnet: bool = True,
    progress_callback: Optional[Callable] = None,
    selected_indices: Optional[list[int]] = None,
    job_id: Optional[str] = None,
    register_process: Optional[Callable] = None
) -> list[str]:
    """
    Download files using aria2c (supports magnet links and torrent files).
    Returns list of downloaded video file paths.
    
    Args:
        source: Magnet link or path to .torrent file
        dest_dir: Directory to download files to
        is_magnet: True if source is a magnet link
        progress_callback: Async callback for progress updates
        selected_indices: If provided, only download files at these indices (1-based)
        job_id: Job ID for process management
        register_process: Callback to register process for pause/resume
    """
    # Video extensions to include
    VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    
    # Build aria2c command
    cmd = [
        'aria2c',
        '--dir', dest_dir,
        '--seed-time=0',  # Don't seed after download
        '--bt-stop-timeout=300',  # Stop if no activity for 5 minutes
        '--bt-remove-unselected-file=true',  # Delete unselected files (no placeholders)
        '--summary-interval=5',
        '--console-log-level=notice',
        '--show-console-readout=false',
    ]
    
    # Add file selection if specified
    if selected_indices:
        indices_str = ','.join(str(i) for i in selected_indices)
        cmd.extend(['--select-file', indices_str])
        print(f"[TORRENT] Downloading selected files: {indices_str}")
    else:
        print(f"[TORRENT] No file selection - downloading all files")
    
    cmd.append(source)
    print(f"[TORRENT] aria2c command: {' '.join(cmd)}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Register process for pause/resume
    if register_process and job_id:
        register_process(job_id, process.pid)
        print(f"[TORRENT] Registered process PID {process.pid} for job {job_id}")
    
    # Parse output for progress and speed
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        
        line_str = line.decode('utf-8', errors='ignore').strip()
        
        # Parse progress from aria2c output
        # Format: [#hash SIZE/TOTAL(PERCENT) CN:N DL:SPEED ETA:TIME]
        progress_match = re.search(r'\((\d+)%\)', line_str)
        if progress_match and progress_callback:
            progress = float(progress_match.group(1))
            
            # Try to extract speed and ETA
            speed_match = re.search(r'DL:(\d+(?:\.\d+)?[KMGT]?i?B)', line_str)
            eta_match = re.search(r'ETA:(\S+)', line_str)
            
            speed = speed_match.group(1) if speed_match else None
            eta = eta_match.group(1) if eta_match else None
            
            await progress_callback(progress, speed, eta)
    
    await process.wait()
    
    if process.returncode != 0:
        raise Exception(f"aria2c failed with return code {process.returncode}")
    
    # Scan for video files and clean up placeholders
    downloaded_files = []
    for root, dirs, files in os.walk(dest_dir):
        for file in files:
            if any(file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)
                
                # Delete placeholder files (0 bytes or very small)
                if file_size < 1000:
                    print(f"[TORRENT] Removing placeholder file: {file_path} ({file_size} bytes)")
                    os.remove(file_path)
                else:
                    print(f"[TORRENT] Found video file: {file_path} ({file_size} bytes)")
                    downloaded_files.append(file_path)
    
    if not downloaded_files:
        raise Exception("No video files found in downloaded content")
    
    print(f"[TORRENT] Total video files: {len(downloaded_files)}")
    return sorted(downloaded_files)


async def get_torrent_files(source: str) -> list[dict]:
    """
    Get list of files in a torrent without downloading.
    Uses aria2c --show-files option.
    
    Returns list of dicts with: index, path
    """
    cmd = ['aria2c', '--show-files', '--bt-metadata-only=true', source]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
    output = stdout.decode('utf-8', errors='ignore')
    
    files = []
    current_file = None
    
    for line in output.split('\n'):
        line = line.rstrip()
        
        if not line or '===+' in line or line.strip().startswith('idx|'):
            continue
        
        # Check if this is an index line (starts with number|)
        index_match = re.match(r'^\s*(\d+)\|(.+)$', line)
        if index_match:
            if current_file:
                files.append(current_file)
            current_file = {
                'index': int(index_match.group(1)),
                'path': index_match.group(2).strip(),
            }
    
    if current_file:
        files.append(current_file)
    
    # Filter to video files only
    VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    video_files = [
        f for f in files 
        if any(f['path'].lower().endswith(ext) for ext in VIDEO_EXTENSIONS)
    ]
    
    return video_files


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
