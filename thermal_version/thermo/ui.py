"""Local display, touch selection and MixFormerV2 in an isolated worker."""

from pathlib import Path
import queue
import time
from milu.vision import publish_latest
from thermo.selection import Selection, TrackState


def get_latest(channel):
    try:
        return channel.get_nowait()
    except queue.Empty:
        return None


def display_reading(status, selection, target, now, base, cfg):
    invalid = {
        "state": "INVALID",
        "reason": "WAITING_CONTROLLER",
        "value": None,
        "maximum": None,
        "average": None,
    }
    if not status or not 0 <= now - status["at"] <= cfg.status_timeout:
        return invalid
    if not selection.motion:
        return dict(invalid, reason="ENABLE_TRACK")
    if not target or not 0 <= now - target.captured_at <= base.stale_after:
        return dict(
            invalid,
            reason="SELECT_EYE" if selection.state != TrackState.TRACKING else "STALE_VISION",
        )
    if status["session"] != selection.session:
        return dict(invalid, reason="NEW_SELECTION")
    result = status["reading"]
    if result["value"] is not None and (
        result["acquired_at"] is None or not 0 <= now - result["acquired_at"] <= cfg.sensor_timeout
    ):
        return dict(invalid, reason="STALE_SENSOR")
    return result


def draw_panel(img, selection, target, status, base, cfg, now, image):
    reading = display_reading(status, selection, target, now, base, cfg)
    white = image.COLOR_WHITE
    black = image.COLOR_BLACK
    img.draw_rect(0, 0, img.width(), 96, color=black, thickness=-1)
    value = "--" if reading["value"] is None else f"{reading['value']:.2f}"
    maximum = "--" if reading["maximum"] is None else f"{reading['maximum']:.2f}"
    average = "--" if reading["average"] is None else f"{reading['average']:.2f}"
    img.draw_string(8, 4, "Milu eye IR SURFACE temperature", color=white)
    img.draw_string(8, 26, f"Temp {value} C   ROI max {maximum}   avg {average}", color=white)
    img.draw_string(8, 48, f"{reading['state']}: {reading['reason']}", color=white)
    gimbal = (
        "STALE"
        if not status or not 0 <= now - status["at"] <= cfg.status_timeout
        else status["gimbal"]
    )
    sensor_error = status.get("sensor_error", "") if status else ""
    detail = (
        sensor_error[:48] if sensor_error else f"Eye: {selection.state.value}   Gimbal: {gimbal}"
    )
    img.draw_string(8, 70, detail, color=white)
    if selection.box:
        x, y, w, h = selection.box
        img.draw_rect(int(x), int(y), int(w), int(h), color=image.COLOR_GREEN, thickness=2)
    cx, cy = int(base.aim_x * img.width()), int(base.aim_y * img.height())
    img.draw_line(cx - 8, cy, cx + 8, cy, color=image.COLOR_RED)
    img.draw_line(cx, cy - 8, cx, cy + 8, color=image.COLOR_RED)
    y = img.height() - 44
    img.draw_rect(0, y, img.width(), 44, color=black, thickness=-1)
    img.draw_string(8, y + 12, "SELECT EYE", color=white)
    img.draw_string(120, y + 12, "TRACK ON" if selection.motion else "TRACK OFF", color=white)
    img.draw_string(img.width() - 80, y + 12, "EXIT", color=white)


def worker(base, cfg, frames, statuses, stop):
    cam = None
    try:
        from maix import camera, display, touchscreen, nn, image, app
        from milu.maixcam2 import check_board

        check_board()
        if not Path(cfg.tracker_model).is_file():
            raise FileNotFoundError("MixFormerV2 system model missing: " + cfg.tracker_model)
        tracker = nn.MixFormerV2(cfg.tracker_model, update_interval=200, lost_find_interval=-1)
        screen = display.Display()
        touch = touchscreen.TouchScreen()
        width, height = screen.width(), screen.height()
        cam = camera.Camera(width, height, tracker.input_format())
        selection = Selection(width, height, cfg)
        status = None
        frozen = None
        frozen_at = None
        while not stop.is_set() and not app.need_exit():
            captured = time.monotonic()
            img = cam.read() if frozen is None else frozen.copy()
            x, y, pressed = touch.read()
            before = selection.state
            event = selection.touch(x, y, pressed)
            if selection.state == TrackState.DRAGGING and before != TrackState.DRAGGING:
                frozen = img.copy()
                frozen_at = captured
            target = None
            if event and event[0] == "exit":
                stop.set()
                break
            if event and event[0] == "init":
                tracker.init(img, *[int(v) for v in event[1]])
            elif selection.state == TrackState.TRACKING:
                result = tracker.track(img, threshold=cfg.tracker_threshold)
                target = selection.accept(result, captured)
            if selection.state != TrackState.DRAGGING:
                frozen = None
            # Do not report the frozen selection image as a fresh observation.
            effective_capture = frozen_at if frozen is not None else captured
            publish_latest(
                frames,
                {
                    "kind": "frame",
                    "captured_at": effective_capture,
                    "target": target,
                    "session": selection.session,
                    "motion": selection.motion,
                    "state": selection.state.value,
                },
            )
            message = get_latest(statuses)
            if message:
                status = message
            draw_panel(img, selection, target, status, base, cfg, time.monotonic(), image)
            if selection.state == TrackState.DRAGGING and selection.start:
                sx, sy = selection.start
                img.draw_rect(
                    min(sx, x),
                    min(sy, y),
                    abs(x - sx),
                    abs(y - sy),
                    color=image.COLOR_GREEN,
                    thickness=2,
                )
            screen.show(img)
    except Exception as exc:
        publish_latest(frames, {"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
        stop.wait(2)
    finally:
        if cam is not None:
            cam.close()
