# RoadPulse AI — Optimization of Traffic Flow Recognition System

A Flask and computer-vision application following the supplied workflow:

`Camera/video → frame extraction → vehicle detection → traffic density analysis → congestion classification → SQLite storage → dashboard and reports`

## Features

- Live webcam input and uploaded video analysis
- YOLOv8s vehicle recognition with track-wise class voting (car, motorcycle, bus, truck)
- Automatic OpenCV motion-detection fallback when YOLO is unavailable
- Low, Medium, and High congestion classification
- Annotated MJPEG live stream, metrics, history chart, and CSV export
- Persistent SQLite analysis database

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

Live camera inference defaults to an optimized 416px input and always processes the latest captured frame. Override it when needed with
`$env:YOLO_IMAGE_SIZE="640"` for higher detail or `"384"` for more speed.

On first use, Ultralytics may download the small `yolov8n.pt` model. To run fully offline with motion detection:

```powershell
$env:USE_YOLO="0"
python app.py
```

## Congestion logic

- **Low:** fewer than 7 vehicles and less than 10% occupied image area
- **Medium:** 7–14 vehicles or 10–21.9% occupied area
- **High:** 15+ vehicles or 22%+ occupied area

These thresholds are centralized in `TrafficProcessor.classify` and can be calibrated for a particular camera position.
