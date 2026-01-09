import asyncio
import os
import uuid
import shutil
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager
import zipfile
import io

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Response, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.auth import (
    get_current_user, authenticate_user, create_access_token,
    change_password, get_app_settings, update_app_settings
)
from app.database import init_db, create_job, get_job, get_all_jobs, update_job, delete_job
from app.models import (
    Job, JobFile, JobStatus, JobType, AudioTrack,
    LoginRequest, LoginResponse, PasswordChangeRequest,
    SettingsUpdateRequest, JobCreateRequest, TrackSelectionRequest,
    TorrentFileInfo, FileSelectionRequest
)
from app.tasks.downloader import download_url, download_torrent, get_torrent_files
from app.tasks.extractor import get_audio_tracks, extract_audio, embed_subtitles
from app.tasks.transcriber import transcribe_with_progress


# Background task queue
processing_jobs = set()
job_processes = {}  # job_id -> subprocess for killing on cancel
cancelled_jobs = set()  # jobs that have been cancelled
download_processes = {}  # job_id -> subprocess.Popen for pause/resume
job_queue = asyncio.Queue()  # Queue for sequential job processing
queue_processor_running = False  # Flag to track if queue processor is active


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    await init_db()
    # Resume any interrupted jobs on startup
    asyncio.create_task(resume_pending_jobs())
    yield


app = FastAPI(
    title="Whisper Subtitle Generator",
    description="Generate subtitles from video files using AI",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ============================================================================
# Authentication Routes
# ============================================================================

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response):
    """Authenticate user and return JWT token."""
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": user["username"]})
    
    # Set cookie for browser access
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=86400,  # 24 hours
        samesite="strict"
    )
    
    return LoginResponse(access_token=token)


@app.post("/api/auth/logout")
async def logout(response: Response):
    """Logout user by clearing cookie."""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out"}


@app.get("/api/auth/me")
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """Get current authenticated user info."""
    return {"username": user["username"]}


# ============================================================================
# Settings Routes
# ============================================================================

@app.get("/api/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    """Get current application settings."""
    return get_app_settings()


@app.post("/api/settings")
async def update_settings(request: SettingsUpdateRequest, user: dict = Depends(get_current_user)):
    """Update application settings."""
    return update_app_settings(
        model=request.model,
        cpu_threads=request.cpu_threads,
        language=request.language
    )


@app.post("/api/settings/password")
async def change_user_password(request: PasswordChangeRequest, user: dict = Depends(get_current_user)):
    """Change user password."""
    if not change_password(request.current_password, request.new_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    return {"message": "Password changed successfully"}


# ============================================================================
# Job Routes
# ============================================================================

@app.get("/api/jobs")
async def list_jobs(user: dict = Depends(get_current_user)):
    """List all jobs."""
    jobs = await get_all_jobs()
    return {"jobs": [job.model_dump() for job in jobs]}


@app.get("/api/jobs/{job_id}")
async def get_job_details(job_id: str, user: dict = Depends(get_current_user)):
    """Get job details by ID."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()

import json

@app.post("/api/jobs")
async def create_new_job(
    background_tasks: BackgroundTasks,
    job_type: str = Form(...),
    source: Optional[str] = Form(None),
    embed_subtitles: bool = Form(True),  # Always embed subtitles by default
    language: str = Form("auto"),
    selected_indices: Optional[str] = Form(None),  # JSON array of file indices
    file: Optional[UploadFile] = File(None),
    torrent_file: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user)
):
    """Create a new transcription job."""
    current_settings = get_app_settings()
    
    # Parse selected file indices if provided
    parsed_indices = None
    if selected_indices:
        try:
            parsed_indices = json.loads(selected_indices)
        except:
            pass
    
    job_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    job = Job(
        id=job_id,
        type=JobType(job_type),
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
        source="",
        embed_subtitles=True,  # Always embed subtitles - ignore form value
        language=language,
        model=current_settings["model"],
        selected_indices=parsed_indices
    )
    
    # Handle different job types
    if job_type == "upload" and file:
        # Save uploaded file
        job.source = file.filename
        upload_path = os.path.join(settings.uploads_dir, job_id)
        os.makedirs(upload_path, exist_ok=True)
        file_path = os.path.join(upload_path, file.filename)
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        job.files = [JobFile(id=str(uuid.uuid4()), filename=file.filename)]
    
    elif job_type == "url" and source:
        job.source = source
    
    elif job_type == "magnet" and source:
        job.source = source
    
    elif job_type == "torrent" and torrent_file:
        # Save torrent file
        job.source = torrent_file.filename
        torrent_path = os.path.join(settings.uploads_dir, job_id, torrent_file.filename)
        os.makedirs(os.path.dirname(torrent_path), exist_ok=True)
        
        with open(torrent_path, "wb") as f:
            content = await torrent_file.read()
            f.write(content)
        
        job.source = torrent_path
    
    else:
        raise HTTPException(status_code=400, detail="Invalid job configuration")
    
    await create_job(job)
    
    # Start processing through queue (one job at a time)
    await queue_job(job.id)
    
    return job.model_dump()


@app.post("/api/torrent-files")
async def get_torrent_file_list(
    source: Optional[str] = Form(None),
    torrent_file: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user)
):
    """Get list of files in a torrent for selection before download."""
    try:
        if torrent_file:
            # Save torrent file temporarily
            temp_path = os.path.join(settings.temp_dir, f"temp_{uuid.uuid4()}.torrent")
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)
            
            with open(temp_path, "wb") as f:
                content = await torrent_file.read()
                f.write(content)
            
            files = await get_torrent_files(temp_path)
            
            # Clean up temp file
            os.remove(temp_path)
        elif source:  # Magnet link
            files = await get_torrent_files(source)
        else:
            raise HTTPException(status_code=400, detail="No torrent source provided")
        
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/select-track")
async def select_audio_track(
    job_id: str,
    request: TrackSelectionRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Select audio track for transcription."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.AWAITING_TRACK:
        raise HTTPException(status_code=400, detail="Job is not waiting for track selection")
    
    # Apply selection to files
    if request.apply_to_all:
        # Apply to all files awaiting track selection
        for file in job.files:
            if file.status == JobStatus.AWAITING_TRACK:
                file.selected_track = request.track_index
                file.status = JobStatus.PENDING
    else:
        # Apply to first file awaiting track selection only
        for file in job.files:
            if file.status == JobStatus.AWAITING_TRACK:
                file.selected_track = request.track_index
                file.status = JobStatus.PENDING
                break  # Only apply to first awaiting file
    
    await update_job(job)
    
    # Check if any files still awaiting track selection
    still_awaiting = any(f.status == JobStatus.AWAITING_TRACK for f in job.files)
    
    if still_awaiting:
        # Don't start processing yet, stay in AWAITING_TRACK
        return job.model_dump()
    
    # All files have tracks selected - start processing
    job.status = JobStatus.EXTRACTING
    await update_job(job)
    
    # Continue processing
    background_tasks.add_task(process_job, job_id)
    
    return job.model_dump()


@app.delete("/api/jobs/{job_id}")
async def delete_job_route(job_id: str, user: dict = Depends(get_current_user)):
    """Delete a job and its associated files, kill any running processes."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Mark job as cancelled to stop transcription
    cancelled_jobs.add(job_id)
    processing_jobs.discard(job_id)
    
    # Kill transcription subprocess if running
    if job_id in job_processes:
        try:
            process = job_processes[job_id]
            print(f"[DELETE] Terminating transcription subprocess PID {process.pid}")
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
                print(f"[DELETE] Subprocess terminated gracefully")
            except asyncio.TimeoutError:
                print(f"[DELETE] Subprocess didn't terminate, killing...")
                process.kill()
                await process.wait()
                print(f"[DELETE] Subprocess killed")
        except Exception as e:
            print(f"[DELETE] Error killing transcription: {e}")
        finally:
            job_processes.pop(job_id, None)
    
    # Kill any aria2c process for this job
    try:
        import subprocess
        subprocess.run(['pkill', '-f', f'--dir.*/downloads/{job_id}'], capture_output=True)
        subprocess.run(['pkill', '-f', f'--dir.*/temp/{job_id}'], capture_output=True)
        # Kill any ffmpeg process for this job (conversion/streaming)
        subprocess.run(['pkill', '-f', f'{job_id}'], capture_output=True)
        print(f"[DELETE] Killed all processes for job {job_id}")
    except Exception as e:
        print(f"[DELETE] Error killing processes for job {job_id}: {e}")
    
    # Clean up files
    for dir_path in [settings.uploads_dir, settings.downloads_dir, settings.temp_dir, settings.output_dir]:
        job_dir = os.path.join(dir_path, job_id)
        if os.path.exists(job_dir):
            try:
                shutil.rmtree(job_dir)
            except Exception as e:
                print(f"[DELETE] Error removing {job_dir}: {e}")
    
    await delete_job(job_id)
    cancelled_jobs.discard(job_id)
    return {"message": "Job deleted"}


@app.post("/api/jobs/{job_id}/pause")
async def toggle_pause_job(job_id: str, user: dict = Depends(get_current_user)):
    """Toggle pause state for a downloading job."""
    import signal
    
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.DOWNLOADING:
        raise HTTPException(status_code=400, detail="Job is not downloading")
    
    # Toggle pause state
    job.is_paused = not job.is_paused
    await update_job(job)
    
    # Send signal to aria2c process using PID
    if job_id in download_processes:
        try:
            pid = download_processes[job_id]
            if job.is_paused:
                os.kill(pid, signal.SIGSTOP)
                print(f"[PAUSE] Paused download for job {job_id} (PID: {pid})")
            else:
                os.kill(pid, signal.SIGCONT)
                print(f"[PAUSE] Resumed download for job {job_id} (PID: {pid})")
        except ProcessLookupError:
            print(f"[PAUSE] Process {pid} not found, removing from registry")
            download_processes.pop(job_id, None)
        except Exception as e:
            print(f"[PAUSE] Error sending signal: {e}")
    
    return {"is_paused": job.is_paused}


# ============================================================================
# Download Routes
# ============================================================================

@app.get("/api/jobs/{job_id}/download/srt")
async def download_srt(job_id: str, file_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Download SRT subtitle file."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.COMPLETED, JobStatus.CONVERTING, JobStatus.EMBEDDING]:
        raise HTTPException(status_code=400, detail="Job not completed")
    
    # Single file or specific file
    if file_id:
        for f in job.files:
            if f.id == file_id and f.srt_path and os.path.exists(f.srt_path):
                return FileResponse(
                    f.srt_path,
                    media_type="application/x-subrip",
                    filename=os.path.basename(f.srt_path)
                )
        raise HTTPException(status_code=404, detail="SRT file not found")
    
    # Multiple files - return ZIP
    if len(job.files) > 1:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for f in job.files:
                if f.srt_path and os.path.exists(f.srt_path):
                    zip_file.write(f.srt_path, os.path.basename(f.srt_path))
        
        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=subtitles_{job_id}.zip"}
        )
    
    # Single file job
    if job.files and job.files[0].srt_path and os.path.exists(job.files[0].srt_path):
        return FileResponse(
            job.files[0].srt_path,
            media_type="application/x-subrip",
            filename=os.path.basename(job.files[0].srt_path)
        )
    
    raise HTTPException(status_code=404, detail="SRT file not found")


@app.get("/api/jobs/{job_id}/download/video")
async def download_video_with_subtitles(job_id: str, file_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Download video with embedded subtitles."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status not in [JobStatus.COMPLETED, JobStatus.CONVERTING, JobStatus.EMBEDDING]:
        raise HTTPException(status_code=400, detail="Job not completed")
    
    # Find the output file
    target_file = None
    if file_id:
        for f in job.files:
            if f.id == file_id:
                target_file = f
                break
    else:
        target_file = job.files[0] if job.files else None
    
    if not target_file or not target_file.output_path or not os.path.exists(target_file.output_path):
        print(f"[DEBUG DOWNLOAD] target_file={target_file}, output_path={target_file.output_path if target_file else None}")
        raise HTTPException(status_code=404, detail="Video file not found")
    
    print(f"[DEBUG DOWNLOAD] Sending file: {target_file.output_path}")
    return FileResponse(
        target_file.output_path,
        media_type="video/x-matroska",
        filename=os.path.basename(target_file.output_path)
    )


# ============================================================================
# Streaming Routes (Online viewing with burned-in subtitles)
# ============================================================================

# Streaming version is now created automatically during transcription
# The /stream endpoint simply serves the pre-created file


@app.get("/api/jobs/{job_id}/stream")
async def stream_video(
    job_id: str, 
    file_id: Optional[str] = None, 
    token: Optional[str] = None,  # Support token in query for video player
    user: dict = Depends(get_current_user)
):
    """Stream video (remuxed MP4 for browser compatibility)."""
    # If token provided in query, verify it (for video player which can't set headers)
    if token and not user:
        from app.auth import verify_token
        payload = verify_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")
    
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    target_file = None
    if file_id:
        for f in job.files:
            if f.id == file_id:
                target_file = f
                break
    else:
        target_file = job.files[0] if job.files else None
    
    if not target_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not target_file.streaming_path or not os.path.exists(target_file.streaming_path):
        raise HTTPException(status_code=404, detail="Video for online viewing not found")
    
    return FileResponse(
        target_file.streaming_path,
        media_type="video/mp4"
    )


@app.get("/api/jobs/{job_id}/subtitles.vtt")
async def get_subtitles_vtt(
    job_id: str,
    file_id: Optional[str] = None,
    token: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Get WebVTT subtitles for HTML5 video track element."""
    # If token provided in query, verify it
    if token and not user:
        from app.auth import verify_token
        payload = verify_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")
    
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    target_file = None
    if file_id:
        for f in job.files:
            if f.id == file_id:
                target_file = f
                break
    else:
        target_file = job.files[0] if job.files else None
    
    if not target_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not target_file.srt_path:
        raise HTTPException(status_code=404, detail="Subtitles not found")
    
    # WebVTT file is next to SRT file with .vtt extension
    vtt_path = target_file.srt_path.rsplit('.', 1)[0] + '.vtt'
    
    if not os.path.exists(vtt_path):
        raise HTTPException(status_code=404, detail="WebVTT subtitles not found")
    
    return FileResponse(
        vtt_path,
        media_type="text/vtt",
        headers={"Content-Disposition": "inline"}
    )


# ============================================================================
# Static File Serving
# ============================================================================

@app.get("/")
async def serve_index():
    """Serve the main application page."""
    return FileResponse("app/static/index.html")


# ============================================================================
# Subprocess-based Transcription (for cancellation support)
# ============================================================================

async def run_transcription_subprocess(
    job_id: str,
    audio_path: str,
    output_srt_path: str,
    model_name: str,
    language: str,
    progress_callback = None
) -> str:
    """
    Run transcription as a subprocess that can be killed.
    Returns path to generated SRT file.
    """
    import sys
    
    # Build command to run the worker
    cmd = [
        sys.executable, "-m", "app.tasks.transcribe_worker",
        audio_path,
        output_srt_path,
        model_name,
        language
    ]
    
    print(f"[TRANSCRIBE] Starting subprocess: {' '.join(cmd)}")
    
    # Start subprocess
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    
    # Store process for cancellation
    job_processes[job_id] = process
    print(f"[TRANSCRIBE] Subprocess started with PID {process.pid}")
    
    # Drain stderr concurrently to prevent buffer overflow
    stderr_lines = []
    async def drain_stderr():
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            stderr_lines.append(line.decode())
    
    stderr_task = asyncio.create_task(drain_stderr())
    
    try:
        # Read progress updates from stdout
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            
            try:
                data = json.loads(line.decode().strip())
                status = data.get("status", "")
                progress = data.get("progress", 0)
                
                print(f"[TRANSCRIBE] {status}: {progress}%")
                
                if progress_callback and progress > 0:
                    await progress_callback(progress)
                
                if status == "completed":
                    break
                elif status == "error":
                    error = data.get("error", "Unknown error")
                    traceback_info = data.get("traceback", "")
                    if traceback_info:
                        print(f"[TRANSCRIBE] Error traceback:\n{traceback_info}")
                    raise Exception(f"Transcription failed: {error}")
                elif status == "cancelled":
                    raise Exception("Transcription cancelled")
                    
            except json.JSONDecodeError:
                # Non-JSON output, just log it
                print(f"[TRANSCRIBE] {line.decode().strip()}")
        
        # Wait for stderr drain to complete
        await stderr_task
        
        # Wait for process to complete
        await process.wait()
        
        if process.returncode != 0:
            # Use collected stderr lines
            error_msg = "".join(stderr_lines).strip() if stderr_lines else "Unknown error (process crashed)"
            print(f"[TRANSCRIBE] Subprocess failed with stderr:\n{error_msg}")
            raise Exception(f"Transcription subprocess failed: {error_msg}")
        
        return output_srt_path
        
    finally:
        # Cancel stderr drain task if still running
        if not stderr_task.done():
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
        
        # Clean up process reference
        job_processes.pop(job_id, None)
        
        # Ensure process is terminated
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                process.kill()


# ============================================================================
# Background Job Processing
# ============================================================================

async def resume_pending_jobs():
    """Resume processing of interrupted jobs on startup."""
    await asyncio.sleep(2)  # Wait for app to fully start
    jobs = await get_all_jobs()
    
    for job in jobs:
        if job.status in [JobStatus.PENDING, JobStatus.DOWNLOADING, JobStatus.EXTRACTING, JobStatus.TRANSCRIBING, JobStatus.CONVERTING]:
            if job.id not in processing_jobs:
                await queue_job(job.id)


async def queue_job(job_id: str):
    """Add job to processing queue."""
    global queue_processor_running
    
    # Add to queue
    await job_queue.put(job_id)
    print(f"[QUEUE] Job {job_id} added to queue. Queue size: {job_queue.qsize()}")
    
    # Start queue processor if not running
    if not queue_processor_running:
        queue_processor_running = True
        asyncio.create_task(process_job_queue())


async def process_job_queue():
    """Process jobs from queue one at a time."""
    global queue_processor_running
    
    print("[QUEUE] Queue processor started")
    
    while True:
        try:
            # Wait for next job in queue
            job_id = await asyncio.wait_for(job_queue.get(), timeout=5.0)
            
            # Skip if job was cancelled while waiting in queue
            if job_id in cancelled_jobs:
                print(f"[QUEUE] Skipping cancelled job {job_id}")
                job_queue.task_done()
                continue
            
            print(f"[QUEUE] Processing job {job_id}. Remaining in queue: {job_queue.qsize()}")
            
            # Process the job (wait for completion)
            await process_job(job_id)
            
            job_queue.task_done()
            
        except asyncio.TimeoutError:
            # No jobs in queue, check if we should stop
            if job_queue.empty():
                print("[QUEUE] Queue empty, stopping processor")
                queue_processor_running = False
                break


async def process_job(job_id: str):
    """Main job processing function."""
    if job_id in processing_jobs:
        return
    
    processing_jobs.add(job_id)
    
    try:
        job = await get_job(job_id)
        if not job:
            return
        
        current_settings = get_app_settings()
        
        # Step 1: Download (if URL, magnet, or torrent)
        if job.type in [JobType.URL, JobType.MAGNET, JobType.TORRENT] and not job.files:
            job.status = JobStatus.DOWNLOADING
            await update_job(job)
            
            download_dir = os.path.join(settings.downloads_dir, job_id)
            os.makedirs(download_dir, exist_ok=True)
            
            try:
                async def update_download_progress(progress, speed=None, eta=None):
                    job.progress = progress  # Show download progress as 0-100%
                    job.download_speed = speed
                    job.eta = eta
                    await update_job(job)
                
                if job.type == JobType.URL:
                    file_path = await download_url(job.source, download_dir, update_download_progress)
                    job.files = [JobFile(id=str(uuid.uuid4()), filename=os.path.basename(file_path))]
                else:
                    is_magnet = job.type == JobType.MAGNET
                    
                    # Register process for pause/resume
                    def register_download_process(jid, pid):
                        download_processes[jid] = pid
                    
                    file_paths = await download_torrent(
                        job.source, 
                        download_dir, 
                        is_magnet, 
                        update_download_progress,
                        selected_indices=job.selected_indices,
                        job_id=job_id,
                        register_process=register_download_process
                    )
                    
                    job.files = [
                        JobFile(id=str(uuid.uuid4()), filename=os.path.basename(fp))
                        for fp in file_paths
                    ]
                    
                    if len(job.files) > 1:
                        job.is_group = True
                        job.group_name = os.path.basename(job.source)
                
                await update_job(job)
                
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error = str(e)
                await update_job(job)
                return
        
        # Step 2: Extract audio tracks info
        if job.status != JobStatus.AWAITING_TRACK:
            job.status = JobStatus.EXTRACTING
            await update_job(job)
            
            for file in job.files:
                if file.status == JobStatus.PENDING:
                    # Find the actual video file
                    video_path = find_video_file(job, file)
                    if not video_path:
                        file.status = JobStatus.FAILED
                        file.error = "Video file not found"
                        continue
                    
                    try:
                        tracks = await get_audio_tracks(video_path)
                        file.audio_tracks = tracks
                        
                        # If multiple tracks, wait for selection
                        if len(tracks) > 1 and file.selected_track is None:
                            file.status = JobStatus.AWAITING_TRACK
                        elif len(tracks) == 1:
                            file.selected_track = 0
                        elif len(tracks) == 0:
                            file.status = JobStatus.FAILED
                            file.error = "No audio tracks found"
                    except Exception as e:
                        file.status = JobStatus.FAILED
                        file.error = str(e)
            
            await update_job(job)
            
            # Check if any file needs track selection
            awaiting = any(f.status == JobStatus.AWAITING_TRACK for f in job.files)
            if awaiting:
                job.status = JobStatus.AWAITING_TRACK
                await update_job(job)
                return
        
        # Step 3: Process each file
        job.status = JobStatus.TRANSCRIBING
        await update_job(job)
        
        for file in job.files:
            # Check if job was cancelled
            if job_id in cancelled_jobs:
                print(f"[CANCEL] Job {job_id} was cancelled, stopping processing")
                return
            
            # Skip already completed or failed files
            if file.status in [JobStatus.FAILED, JobStatus.COMPLETED]:
                continue
            
            # Skip files without selected track or still awaiting selection
            if file.selected_track is None or file.status == JobStatus.AWAITING_TRACK:
                continue
            
            try:
                video_path = find_video_file(job, file)
                if not video_path:
                    file.status = JobStatus.FAILED
                    file.error = "Video file not found"
                    continue
                
                # Extract audio
                temp_dir = os.path.join(settings.temp_dir, job_id)
                os.makedirs(temp_dir, exist_ok=True)
                audio_path = os.path.join(temp_dir, f"{file.id}.wav")
                
                await extract_audio(video_path, audio_path, file.selected_track)
                
                # Transcribe
                output_dir = os.path.join(settings.output_dir, job_id)
                os.makedirs(output_dir, exist_ok=True)
                
                base_name = os.path.splitext(file.filename)[0]
                srt_path = os.path.join(output_dir, f"{base_name}.srt")
                
                async def update_transcribe_progress(progress):
                    file.progress = progress
                    await update_job(job)
                
                # Run transcription as subprocess (can be killed on cancel)
                await run_transcription_subprocess(
                    job_id,
                    audio_path,
                    srt_path,
                    model_name=current_settings["model"],
                    language=current_settings["language"],
                    progress_callback=update_transcribe_progress
                )
                
                file.srt_path = srt_path
                
                # Embed subtitles (always enabled now)
                print(f"[DEBUG] job.embed_subtitles = {job.embed_subtitles}, video_path = {video_path}, srt_path = {srt_path}")
                if job.embed_subtitles:
                    # Validate SRT file exists and has content
                    if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
                        raise Exception(f"Transcription failed: SRT file is empty or missing ({srt_path})")
                    
                    output_video = os.path.join(output_dir, f"{base_name}_subtitled.mkv")
                    print(f"[EMBED] Starting embed_subtitles: {video_path} + {srt_path} -> {output_video}")
                    await embed_subtitles(video_path, srt_path, output_video)
                    print(f"[EMBED] Completed: {output_video}, exists={os.path.exists(output_video)}")
                    file.output_path = output_video
                    
                    # CRITICAL: Save output_path to DB immediately so it's available for download
                    job.status = JobStatus.EMBEDDING
                    file.status = JobStatus.EMBEDDING
                    await update_job(job)
                    print(f"[EMBED] Saved output_path to DB: {file.output_path}")
                    
                    # Create streaming version with burned-in subtitles for online viewing
                    job.status = JobStatus.CONVERTING
                    file.status = JobStatus.CONVERTING
                    file.progress = 0  # Reset progress for conversion phase
                    await update_job(job)
                    
                    from app.tasks.extractor import create_streaming_version
                    streaming_video = os.path.join(output_dir, f"{base_name}_streaming.mp4")
                    
                    async def update_conversion_progress(progress):
                        # Conversion progress 0-100%
                        file.progress = progress
                        await update_job(job)
                    
                    try:
                        await create_streaming_version(
                            output_video,
                            srt_path,
                            streaming_video,
                            max_height=1080,
                            progress_callback=update_conversion_progress,
                            is_cancelled=lambda: job_id in cancelled_jobs
                        )
                        file.streaming_path = streaming_video
                        print(f"[STREAMING] Created: {streaming_video}")
                    except Exception as e:
                        print(f"[STREAMING] Failed to create streaming version: {e}")
                        import traceback
                        traceback.print_exc()
                        # Continue without streaming version - not critical
                
                file.status = JobStatus.COMPLETED
                file.progress = 100
                
                # Clean up temp audio
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                
            except Exception as e:
                # Check if this was a cancellation
                if job_id in cancelled_jobs or "cancelled" in str(e).lower():
                    print(f"[CANCEL] Job {job_id} was cancelled during processing")
                    return  # Exit cleanly, job already deleted
                
                print(f"[ERROR] Transcription failed for {file.filename}: {e}")
                import traceback
                traceback.print_exc()
                file.status = JobStatus.FAILED
                file.error = str(e)
            
            # Safe update - job may have been deleted
            try:
                await update_job(job)
            except Exception:
                if job_id in cancelled_jobs:
                    return  # Job was deleted, exit
        
        # Final status
        all_completed = all(f.status == JobStatus.COMPLETED for f in job.files)
        any_failed = any(f.status == JobStatus.FAILED for f in job.files)
        
        if all_completed:
            job.status = JobStatus.COMPLETED
            job.progress = 100
        elif any_failed:
            failed_count = sum(1 for f in job.files if f.status == JobStatus.FAILED)
            if failed_count == len(job.files):
                job.status = JobStatus.FAILED
                job.error = "All files failed to process"
            else:
                job.status = JobStatus.COMPLETED
                job.error = f"{failed_count} file(s) failed"
        
        await update_job(job)
        
    except Exception as e:
        print(f"[ERROR] Job {job_id} failed: {e}")
        import traceback
        traceback.print_exc()
        job = await get_job(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error = str(e)
            await update_job(job)
    finally:
        processing_jobs.discard(job_id)


def find_video_file(job: Job, file: JobFile) -> Optional[str]:
    """Find the actual video file path."""
    # Check uploads directory
    upload_path = os.path.join(settings.uploads_dir, job.id, file.filename)
    if os.path.exists(upload_path):
        return upload_path
    
    # Check downloads directory
    download_dir = os.path.join(settings.downloads_dir, job.id)
    if os.path.exists(download_dir):
        for root, dirs, files in os.walk(download_dir):
            for f in files:
                if f == file.filename:
                    return os.path.join(root, f)
    
    return None
