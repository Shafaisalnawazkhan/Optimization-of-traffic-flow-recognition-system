from __future__ import annotations

import atexit
import csv
import io
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from traffic.database import TrafficDatabase
from traffic.processor import TrafficProcessor


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=500 * 1024 * 1024,
    UPLOAD_FOLDER=str(UPLOAD_DIR),
    SECRET_KEY=os.getenv("SECRET_KEY", "traffic-flow-local-dev"),
)

database = TrafficDatabase(BASE_DIR / "traffic.db")
processor = TrafficProcessor(database)


@app.get("/")
def index():
    return render_template("index.html", active_page="home")


@app.get("/monitor")
def monitor():
    return render_template("monitor.html", active_page="monitor")


@app.get("/workflow")
def workflow():
    return render_template("workflow.html", active_page="workflow")


@app.get("/reports")
def reports():
    return render_template("reports.html", active_page="reports")


@app.post("/api/start")
def start_analysis():
    source_type = request.form.get("source_type", "camera")
    source: int | str

    if source_type == "upload":
        video = request.files.get("video")
        if not video or not video.filename:
            return jsonify(error="Select a video file first."), 400
        extension = Path(video.filename).suffix.lower()
        if extension not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
            return jsonify(error="Unsupported video format."), 400
        filename = f"{int(time.time())}_{secure_filename(video.filename)}"
        destination = UPLOAD_DIR / filename
        video.save(destination)
        source = str(destination)
    else:
        try:
            source = int(request.form.get("camera_index", "0"))
        except ValueError:
            return jsonify(error="Camera index must be a number."), 400

    try:
        session_id = processor.start(source, source_type)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 409
    return jsonify(message="Analysis started", session_id=session_id)


@app.post("/api/stop")
def stop_analysis():
    processor.stop()
    return jsonify(message="Analysis stopped")


@app.get("/api/status")
def status():
    state = processor.status()
    state["summary"] = database.summary()
    state["history"] = database.recent(limit=30)
    return jsonify(state)


@app.get("/video_feed")
def video_feed():
    def frames():
        while True:
            frame = processor.jpeg_frame()
            if frame is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(0.025)

    return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/report.csv")
def csv_report():
    rows = database.all_results()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "In Frame", "Total Passed", "Cars", "Motorcycles", "Buses", "Trucks", "Density (%)", "Risk (%)", "Congestion", "Source"])
    for row in rows:
        writer.writerow([row["timestamp"], row["vehicle_count"], row["passed_count"], row["cars"], row["motorcycles"], row["buses"], row["trucks"], row["density"], row["risk_percentage"], row["congestion"], row["source_type"]])
    payload = io.BytesIO(output.getvalue().encode("utf-8"))
    return send_file(payload, mimetype="text/csv", as_attachment=True, download_name="traffic-analysis.csv")


@app.post("/api/report/reset")
def reset_report():
    if processor.status()["running"]:
        return jsonify(error="Stop the current analysis before clearing reports."), 409
    database.clear()
    return jsonify(message="Report history cleared")


@app.get("/health")
def health():
    return jsonify(status="ok", time=datetime.now(timezone.utc).isoformat())


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error="Video is larger than 500 MB."), 413


atexit.register(processor.stop)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True, threaded=True, use_reloader=False)
