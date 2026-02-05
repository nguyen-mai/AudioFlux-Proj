from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import uuid
import os
import threading

app = FastAPI(title="AudioFlux Backend - Simple Prod")

# Thư mục lưu mp3
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Lưu progress theo job_id
jobs = {}

# ---------
# MODEL
# ---------

class ConvertRequest(BaseModel):
    url: str


# ---------
# CORE LOGIC
# ---------

def run_convert(job_id: str, url: str):
    """
    Background job:
    - Download video
    - Convert to mp3
    """

    output_template = f"{OUTPUT_DIR}/{job_id}.%(ext)s"

    jobs[job_id] = {
        "status": "running",
        "progress": 10
    }

    # command: yt-dlp -x --audio-format mp3 -o outputs/xxx.mp3 URL
    command = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "-o", output_template,
        url
    ]

    try:
        result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

        if result.returncode == 0:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["progress"] = 100
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["progress"] = -1
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["progress"] = -1
        print(f"Error in job {job_id}: {e}")


# ---------
# API
# ---------

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

    return {
        "job_id": job_id
    }

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

    return FileResponse(
        path=file_path,
        media_type="audio/mpeg"
    )

@app.get("/")
def health():
    return {"status": "ok"}
