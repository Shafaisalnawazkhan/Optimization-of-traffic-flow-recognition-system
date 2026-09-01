from __future__ import annotations

import os
import cv2
from pathlib import Path


class VehicleDetector:
    """YOLO vehicle detector with an offline OpenCV motion fallback."""

    VEHICLE_CLASSES = {2, 3, 5, 7}  # car, motorcycle, bus, truck (COCO)

    def __init__(self):
        self.model = None
        self.backend = "OpenCV motion detection"
        self.background = cv2.createBackgroundSubtractorMOG2(history=400, varThreshold=45, detectShadows=True)
        self.image_size = int(os.getenv("YOLO_IMAGE_SIZE", "416"))
        if os.getenv("USE_YOLO", "1") != "0":
            try:
                from ultralytics import YOLO
                model_name = os.getenv("YOLO_MODEL", "yolov8n.pt")
                self.model = YOLO(model_name)
                self.backend = f"{Path(model_name).stem} Fast + ByteTrack"
            except Exception:
                self.model = None

    def detect(self, frame):
        if self.model is not None:
            return self._detect_yolo(frame)
        return self._detect_motion(frame)

    def _detect_yolo(self, frame):
        detections = []
        result = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=list(self.VEHICLE_CLASSES),
            conf=0.48,
            iou=0.55,
            imgsz=self.image_size,
            verbose=False,
        )[0]
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            track_id = int(box.id[0]) if box.id is not None else None
            detections.append((x1, y1, x2, y2, confidence, result.names[class_id], track_id))
        return detections

    def _detect_motion(self, frame):
        mask = self.background.apply(frame)
        mask = cv2.threshold(mask, 210, 255, cv2.THRESH_BINARY)[1]
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = frame.shape[0] * frame.shape[1]
        minimum = max(900, frame_area * 0.002)
        detections = []
        for contour in contours:
            if cv2.contourArea(contour) < minimum:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            if w / max(h, 1) > 5 or h / max(w, 1) > 5:
                continue
            detections.append((x, y, x + w, y + h, 1.0, "moving vehicle", None))
        return detections
