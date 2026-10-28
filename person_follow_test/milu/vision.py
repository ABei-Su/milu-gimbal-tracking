"""Isolated MaixPy capture/inference worker. No motor or GPIO imports."""

import queue
import time
from milu.tracking import Detection


def publish_latest(channel, message):
    try:
        channel.put_nowait(message)
    except queue.Full:
        try:
            channel.get_nowait()
        except queue.Empty:
            return
        try:
            channel.put_nowait(message)
        except queue.Full:
            return


def worker(cfg, model_path, channel, stop):
    cam = None
    try:
        from maix import camera, display, image, nn, app
        from milu.maixcam2 import check_board, verify_model

        check_board()
        from milu.maixcam2 import release_default_listener

        release_default_listener()
        if cfg.target_kind == "face":
            from milu.head_model import make_face_detector

            detector, class_id = make_face_detector(nn, model_path)
        else:
            detector = nn.YOLO11(model=verify_model(model_path), dual_buff=False)
            if "person" not in detector.labels:
                raise ValueError("SDK labels do not contain person")
            class_id = list(detector.labels).index("person")
        cam = camera.Camera(
            detector.input_width(), detector.input_height(), detector.input_format()
        )
        disp = display.Display() if cfg.show_display else None
        while not stop.is_set() and not app.need_exit():
            captured = time.monotonic()  # conservative includes camera read + inference
            img = cam.read()
            objects = detector.detect(
                img, conf_th=min(cfg.confidence, cfg.track_confidence), iou_th=cfg.nms_iou
            )
            detections = []
            width, height = img.width(), img.height()
            for obj in objects:
                if class_id is not None and obj.class_id != class_id:
                    continue
                x1, y1 = max(0, obj.x), max(0, obj.y)
                x2, y2 = min(width, obj.x + obj.w), min(height, obj.y + obj.h)
                if x2 <= x1 or y2 <= y1:
                    continue
                d = Detection(
                    float(x1),
                    float(y1),
                    float(x2),
                    float(y2),
                    width,
                    height,
                    float(obj.score),
                    captured,
                )
                d.validate()
                detections.append(d)
            publish_latest(
                channel,
                {
                    "kind": "frame",
                    "captured_at": captured,
                    "detections": detections,
                    "latency": time.monotonic() - captured,
                },
            )
            if disp is not None:
                for d in detections:
                    img.draw_rect(
                        int(d.x1),
                        int(d.y1),
                        int(d.x2 - d.x1),
                        int(d.y2 - d.y1),
                        color=image.COLOR_GREEN,
                    )
                ax, ay = int(width * cfg.aim_x), int(height * cfg.aim_y)
                img.draw_line(ax - 8, ay, ax + 8, ay, color=image.COLOR_RED)
                img.draw_line(ax, ay - 8, ax, ay + 8, color=image.COLOR_RED)
                img.draw_string(
                    2,
                    2,
                    f"{cfg.target_kind} strong: {sum(d.confidence >= cfg.confidence for d in detections)} / candidates: {len(detections)}",
                    color=image.COLOR_WHITE,
                )
                disp.show(img)
    except Exception as exc:
        publish_latest(channel, {"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        if cam is not None:
            cam.close()
