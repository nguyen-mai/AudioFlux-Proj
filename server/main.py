from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import uuid
import os
import threading
import re

app = FastAPI(title="AudioFlux Backend - Stable Version")

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

jobs = {}

# -------------------------
# MODEL
# -------------------------

class ConvertRequest(BaseModel):
    url: str


# -------------------------
# UTILS
# -------------------------

def safe_filename(name: str):
    return re.sub(r'[\\/*?:"<>|]', "", name)


def get_video_title(url: str):
    command = ["yt-dlp", "--get-title", url]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode == 0:
        return result.stdout.strip()

    print("TITLE ERROR:", result.stderr)
    return None


# -------------------------
# CONVERT LOGIC
# -------------------------

def run_convert(job_id: str, url: str):

    try:
        print("Starting job:", job_id)

        title = get_video_title(url)

        if not title:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["progress"] = -1
            return

        safe_title = safe_filename(title)

        output_template = f"{OUTPUT_DIR}/{job_id}.%(ext)s"

        jobs[job_id] = {
            "status": "running",
            "progress": 10,
            "title": safe_title
        }

        command = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "-o", output_template,
            url
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        print("RETURN CODE:", result.returncode)
        print("STDERR:", result.stderr)

        if result.returncode == 0:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["progress"] = 100
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["progress"] = -1

    except Exception as e:
        print("🔥 THREAD ERROR:", str(e))
        jobs[job_id]["status"] = "error"
        jobs[job_id]["progress"] = -1


# -------------------------
# API
# -------------------------

@app.post("/convert")
def convert(request: ConvertRequest):
    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "pending",
        "progress": 0
    }

    thread = threading.Thread(
        target=run_convert,
        args=(job_id, request.url),
        daemon=True
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/progress/{job_id}")
def get_progress(job_id: str):
    job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"]
    }


@app.get("/download/{job_id}")
def download_mp3(job_id: str):
    job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="File not ready")

    file_path = f"{OUTPUT_DIR}/{job_id}.mp3"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    safe_title = job.get("title", job_id)

    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=f"{safe_title}.mp3"
    )
