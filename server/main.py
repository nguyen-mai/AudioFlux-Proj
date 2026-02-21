from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess
import uuid
import os
import threading
import re

app = FastAPI()

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

jobs = {}
lock = threading.Lock()


# =============================
# MODEL
# =============================

class ConvertRequest(BaseModel):
    url: str


# =============================
# UTIL
# =============================

def safe_filename(name: str):
    return re.sub(r'[\\/*?:"<>|]', "", name)


def get_video_title(url: str):
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0:
            return result.stdout.strip()

        print("TITLE ERROR:", result.stderr)
        return None

    except Exception as e:
        print("TITLE EXCEPTION:", str(e))
        return None


# =============================
# CONVERT THREAD
# =============================

def run_convert(job_id: str, url: str):
    try:
        print("Starting job:", job_id)

        # ====== 1️⃣ Lấy title (không fail nếu lỗi)
        title = get_video_title(url)
        if title:
            safe_title = safe_filename(title)
        else:
            print("Title not found, fallback to job_id")
            safe_title = job_id

        with lock:
            jobs[job_id]["status"] = "running"
            jobs[job_id]["progress"] = 10
            jobs[job_id]["title"] = safe_title

        # ====== 2️⃣ Convert mp3
        output_template = f"{OUTPUT_DIR}/{job_id}.%(ext)s"

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

        print("CONVERT RETURN CODE:", result.returncode)
        print("CONVERT STDERR:", result.stderr)

        if result.returncode != 0:
            with lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["progress"] = -1
            return

        # ====== 3️⃣ Kiểm tra file tồn tại
        final_path = f"{OUTPUT_DIR}/{job_id}.mp3"

        if not os.path.exists(final_path):
            print("MP3 file not found after convert")
            with lock:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["progress"] = -1
            return

        # ====== 4️⃣ DONE
        with lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["progress"] = 100

        print("Job done:", job_id)

    except Exception as e:
        print("THREAD ERROR:", str(e))
        with lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["progress"] = -1


# =============================
# API
# =============================

@app.post("/convert")
def convert(request: ConvertRequest):
    job_id = str(uuid.uuid4())

    with lock:
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
    with lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress", 0)
    }


@app.get("/download/{job_id}")
def download_mp3(job_id: str):
    with lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "done":
        raise HTTPException(status_code=400, detail="File not ready")

    file_path = f"{OUTPUT_DIR}/{job_id}.mp3"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    filename = job.get("title", job_id) + ".mp3"

    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=filename
    )
