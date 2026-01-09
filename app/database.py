import aiosqlite
import json
from datetime import datetime
from typing import List, Optional
from app.config import settings
from app.models import Job, JobFile, JobStatus, JobType, AudioTrack


async def init_db():
    """Initialize the database with required tables."""
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL,
                files TEXT DEFAULT '[]',
                embed_subtitles INTEGER DEFAULT 1,
                language TEXT DEFAULT 'auto',
                model TEXT DEFAULT 'large-v3-int8',
                error TEXT,
                is_group INTEGER DEFAULT 0,
                group_name TEXT,
                selected_indices TEXT,
                download_speed TEXT,
                eta TEXT,
                is_paused INTEGER DEFAULT 0
            )
        """)
        # Add columns if they don't exist (migration)
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN selected_indices TEXT")
        except:
            pass
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN download_speed TEXT")
        except:
            pass
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN eta TEXT")
        except:
            pass
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN is_paused INTEGER DEFAULT 0")
        except:
            pass
        await db.commit()


async def create_job(job: Job) -> Job:
    """Create a new job in the database."""
    async with aiosqlite.connect(settings.db_path) as db:
        files_json = json.dumps([f.model_dump() for f in job.files], default=str)
        indices_json = json.dumps(job.selected_indices) if job.selected_indices else None
        await db.execute("""
            INSERT INTO jobs (id, type, status, progress, created_at, updated_at, 
                            source, files, embed_subtitles, language, model, error, 
                            is_group, group_name, selected_indices, download_speed, eta, is_paused)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.id, job.type.value, job.status.value, job.progress,
            job.created_at.isoformat(), job.updated_at.isoformat(),
            job.source, files_json, int(job.embed_subtitles),
            job.language, job.model, job.error, int(job.is_group), job.group_name,
            indices_json, job.download_speed, job.eta, int(job.is_paused)
        ))
        await db.commit()
    return job


async def get_job(job_id: str) -> Optional[Job]:
    """Get a job by ID."""
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return _row_to_job(dict(row))


async def get_all_jobs() -> List[Job]:
    """Get all jobs, ordered by creation date (newest first)."""
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jobs ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [_row_to_job(dict(row)) for row in rows]


async def update_job(job: Job) -> Job:
    """Update a job in the database."""
    async with aiosqlite.connect(settings.db_path) as db:
        files_json = json.dumps([f.model_dump() for f in job.files], default=str)
        indices_json = json.dumps(job.selected_indices) if job.selected_indices else None
        job.updated_at = datetime.utcnow()
        await db.execute("""
            UPDATE jobs SET 
                status = ?, progress = ?, updated_at = ?, files = ?,
                embed_subtitles = ?, language = ?, model = ?, error = ?,
                is_group = ?, group_name = ?, selected_indices = ?,
                download_speed = ?, eta = ?, is_paused = ?
            WHERE id = ?
        """, (
            job.status.value, job.progress, job.updated_at.isoformat(),
            files_json, int(job.embed_subtitles), job.language, job.model,
            job.error, int(job.is_group), job.group_name, indices_json,
            job.download_speed, job.eta, int(job.is_paused), job.id
        ))
        await db.commit()
    return job


async def delete_job(job_id: str) -> bool:
    """Delete a job by ID."""
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        await db.commit()
        return cursor.rowcount > 0


async def cleanup_old_jobs(days: int = 30):
    """Delete jobs older than the specified number of days."""
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            DELETE FROM jobs 
            WHERE status IN ('completed', 'failed') 
            AND created_at < ?
        """, (cutoff,))
        await db.commit()


def _row_to_job(row: dict) -> Job:
    """Convert a database row to a Job object."""
    files_data = json.loads(row['files']) if row['files'] else []
    files = []
    for f in files_data:
        audio_tracks = [AudioTrack(**t) for t in f.get('audio_tracks', [])]
        files.append(JobFile(
            id=f['id'],
            filename=f['filename'],
            status=JobStatus(f['status']),
            progress=f.get('progress', 0),
            audio_tracks=audio_tracks,
            selected_track=f.get('selected_track'),
            srt_path=f.get('srt_path'),
            output_path=f.get('output_path'),
            streaming_path=f.get('streaming_path'),
            error=f.get('error')
        ))
    
    # Parse selected_indices from JSON
    selected_indices = None
    if row.get('selected_indices'):
        try:
            selected_indices = json.loads(row['selected_indices'])
        except:
            pass
    
    return Job(
        id=row['id'],
        type=JobType(row['type']),
        status=JobStatus(row['status']),
        progress=row['progress'],
        created_at=datetime.fromisoformat(row['created_at']),
        updated_at=datetime.fromisoformat(row['updated_at']),
        source=row['source'],
        files=files,
        embed_subtitles=bool(row.get('embed_subtitles', 1)),  # Default True
        language=row['language'],
        model=row['model'],
        error=row['error'],
        is_group=bool(row.get('is_group', 0)),
        group_name=row.get('group_name'),
        selected_indices=selected_indices,
        download_speed=row.get('download_speed'),
        eta=row.get('eta'),
        is_paused=bool(row.get('is_paused', 0))
    )
