from __future__ import annotations

import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

import cv2

from .detector import VehicleDetector


class LatestFrameCapture:
    """Continuously drains a webcam and exposes only its newest frame."""

    def __init__(self, capture):
        self.capture = capture
        self.lock = threading.Lock()
        self.frame = None
        self.sequence = 0
        self.delivered_sequence = -1
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._read_frames, daemon=True)
        self.thread.start()

    def _read_frames(self):
        while not self.stopped.is_set():
            ok, frame = self.capture.read()
            if not ok:
                self.stopped.set()
                break
            with self.lock:
                self.frame = frame
                self.sequence += 1

    def read(self):
        while not self.stopped.is_set():
            with self.lock:
                if self.frame is not None and self.sequence != self.delivered_sequence:
                    self.delivered_sequence = self.sequence
                    return True, self.frame.copy()
            time.sleep(0.002)
        return False, None

    def isOpened(self):
        return self.capture.isOpened()

    def release(self):
        self.stopped.set()
        self.capture.release()
        if self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)


class TrafficProcessor:
    def __init__(self, database):
        self.database = database
        self.detector = VehicleDetector()
        self.lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()
        self.frame = None
        self.counted_track_ids = set()
        self.track_sides = {}
        self.track_positions = {}
        self.recent_crossings = []
        self.track_label_votes = {}
        self.passed_vehicle_types = Counter()
        self.state = self._initial_state()

    def _initial_state(self):
        return {
            "running": False, "session_id": None, "vehicle_count": 0,
            "density": 0.0, "congestion": "Waiting", "fps": 0.0, "vehicle_types": {},
            "passed_count": 0, "passed_vehicle_types": {}, "risk_percentage": 0.0,
            "backend": self.detector.backend if hasattr(self, "detector") else "Loading",
            "message": "Choose a source to begin analysis.",
        }

    def start(self, source, source_type):
        if self.thread and self.thread.is_alive():
            raise RuntimeError("An analysis is already running. Stop it before starting another.")
        capture = cv2.VideoCapture(source)
        if source_type == "camera":
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
            capture.set(cv2.CAP_PROP_FPS, 30)
            capture = LatestFrameCapture(capture)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError("Could not open the selected camera or video.")
        session_id = uuid.uuid4().hex[:12]
        self.counted_track_ids.clear()
        self.track_sides.clear()
        self.track_positions.clear()
        self.recent_crossings.clear()
        self.track_label_votes.clear()
        self.passed_vehicle_types.clear()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(capture, session_id, source_type), daemon=True)
        with self.lock:
            self.state.update(running=True, session_id=session_id, passed_count=0, passed_vehicle_types={}, message="Analyzing traffic…")
        self.thread.start()
        return session_id

    def stop(self):
        self.stop_event.set()
        thread = self.thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        with self.lock:
            self.state["running"] = False
            self.state["message"] = "Analysis stopped."

    @staticmethod
    def classify(vehicle_count, density):
        if vehicle_count >= 15 or density >= 22:
            return "High"
        if vehicle_count >= 7 or density >= 10:
            return "Medium"
        return "Low"

    @staticmethod
    def calculate_risk(vehicle_count, density):
        """Congestion-risk index normalized against the High thresholds."""
        count_risk = vehicle_count / 15 * 100
        density_risk = density / 22 * 100
        return round(min(100.0, max(count_risk, density_risk)), 1)

    def _run(self, capture, session_id, source_type):
        last_saved = 0.0
        last_tick = time.perf_counter()
        smoothed_fps = 0.0
        try:
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    break
                if frame.shape[1] > 960:
                    scale = 960 / frame.shape[1]
                    frame = cv2.resize(frame, None, fx=scale, fy=scale)
                detections = self.detector.detect(frame)
                stable_detections = []
                for x1, y1, x2, y2, confidence, label, track_id in detections:
                    if track_id is not None:
                        votes = self.track_label_votes.setdefault(track_id, Counter())
                        votes[label] += confidence
                        label = max(votes, key=votes.get)
                    stable_detections.append((x1, y1, x2, y2, confidence, label, track_id))
                detections = stable_detections
                vehicle_types = dict(Counter(label.title() for *_, label, _ in detections))
                occupied = sum(max(0, x2-x1) * max(0, y2-y1) for x1,y1,x2,y2,_,_,_ in detections)
                density = min(100.0, occupied / (frame.shape[0] * frame.shape[1]) * 100)
                count = len(detections)
                congestion = self.classify(count, density)
                risk_percentage = self.calculate_risk(count, density)
                color = {"Low": (45, 190, 105), "Medium": (0, 180, 255), "High": (55, 65, 240)}[congestion]
                line_y = int(frame.shape[0] * 0.62)
                crossing_margin = max(14, int(frame.shape[0] * 0.045))
                cv2.line(frame, (0, line_y), (frame.shape[1], line_y), (255, 205, 40), 3)
                cv2.putText(frame, "VEHICLE COUNTING LINE", (18, line_y - 11), cv2.FONT_HERSHEY_SIMPLEX, .58, (255, 205, 40), 2)
                for x1, y1, x2, y2, confidence, label, track_id in detections:
                    center_y = (y1 + y2) // 2
                    if track_id is not None:
                        center_x = (x1 + x2) // 2
                        positions = self.track_positions.setdefault(track_id, [])
                        positions.append((center_x, center_y))
                        if len(positions) > 12:
                            del positions[:-12]
                        stable_side = -1 if center_y < line_y - crossing_margin else (1 if center_y > line_y + crossing_margin else 0)
                        previous_side = self.track_sides.get(track_id)
                        moved_enough = len(positions) >= 3 and abs(positions[-1][1] - positions[0][1]) >= crossing_margin * 2
                        if stable_side and previous_side and stable_side != previous_side and moved_enough and track_id not in self.counted_track_ids:
                            crossing_time = time.monotonic()
                            self.recent_crossings = [item for item in self.recent_crossings if crossing_time - item[0] < 0.8]
                            duplicate = any(item[1] == label and abs(item[2] - center_x) < frame.shape[1] * 0.04 for item in self.recent_crossings)
                            self.counted_track_ids.add(track_id)
                            if not duplicate:
                                self.passed_vehicle_types[label.title()] += 1
                                self.recent_crossings.append((crossing_time, label, center_x))
                        if stable_side:
                            self.track_sides[track_id] = stable_side
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    identity = f" #{track_id}" if track_id is not None else ""
                    cv2.putText(frame, f"{label.upper()}{identity} {confidence:.0%}", (x1, max(22, y1-7)), cv2.FONT_HERSHEY_SIMPLEX, .52, color, 2)
                cv2.rectangle(frame, (0, 0), (frame.shape[1], 52), (10, 18, 32), -1)
                cv2.putText(frame, f"In frame: {count}   Passed: {sum(self.passed_vehicle_types.values())}   Risk: {risk_percentage:.1f}%", (18, 34), cv2.FONT_HERSHEY_SIMPLEX, .72, (245,245,245), 2)
                now_tick = time.perf_counter()
                instant_fps = 1 / max(now_tick - last_tick, .001)
                smoothed_fps = instant_fps if not smoothed_fps else .9 * smoothed_fps + .1 * instant_fps
                last_tick = now_tick
                encoded_ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                with self.lock:
                    if encoded_ok:
                        self.frame = encoded.tobytes()
                    passed_total = sum(self.passed_vehicle_types.values())
                    self.state.update(vehicle_count=count, vehicle_types=vehicle_types, passed_count=passed_total, passed_vehicle_types=dict(self.passed_vehicle_types), density=round(density, 1), congestion=congestion, risk_percentage=risk_percentage, fps=round(smoothed_fps, 1), backend=self.detector.backend)
                if time.time() - last_saved >= 2:
                    self.database.add(session_id, now, count, round(density, 1), congestion, source_type, sum(self.passed_vehicle_types.values()), dict(self.passed_vehicle_types), risk_percentage)
                    last_saved = time.time()
        except Exception as exc:
            with self.lock:
                self.state["message"] = f"Processing error: {exc}"
        finally:
            capture.release()
            with self.lock:
                self.state["running"] = False
                if self.state["message"] == "Analyzing traffic…":
                    self.state["message"] = "Video analysis completed."

    def status(self):
        with self.lock:
            return dict(self.state)

    def jpeg_frame(self):
        with self.lock:
            return self.frame
