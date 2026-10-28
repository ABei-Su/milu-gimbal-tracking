"""Board application orchestration. Main process exclusively owns actuators."""

import logging
from logging.handlers import RotatingFileHandler
import multiprocessing as mp
from pathlib import Path
import queue
import signal
import time

from milu.gimbal import Gimbal
from milu.light import LightGate
from milu.settings import load_settings
from milu.targeting import TargetStream, VisualServo, center
from milu.vision import worker


def light_eligible(cfg, target, aim, ambiguous, measured, previous_goal, now):
    if (
        target is None
        or target.confidence < cfg.confidence
        or ambiguous
        or aim.limited
        or not aim.centered
    ):
        return False
    if not 0 <= now - target.captured_at <= cfg.stale_after:
        return False
    cx, cy = center(target)
    x1, y1, x2, y2 = cfg.paper_roi
    if not (x1 <= cx <= x2 and y1 <= cy <= y2):
        return False
    return all(abs(m - g) <= cfg.reached_tolerance for m, g in zip(measured, previous_goal))


def configure_log(root):
    directory = root / "logs"
    directory.mkdir(exist_ok=True)
    logger = logging.getLogger("milu")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    file_handler = RotatingFileHandler(
        directory / "runtime.log", maxBytes=1000000, backupCount=2, encoding="utf-8"
    )
    for handler in (file_handler, logging.StreamHandler()):
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def run(config_path, mode="observe", seconds=0):
    if mode not in ("observe", "track", "paper"):
        raise ValueError("mode must be observe, track or paper")
    cfg = load_settings(config_path)
    root = Path(config_path).resolve().parent
    from milu.maixcam2 import LaserOutput, SerialTransport, check_board, verify_model

    check_board()
    log = configure_log(root)
    from maix import app

    model = verify_model(root / cfg.model)
    ctx = mp.get_context("spawn")
    messages, stop = ctx.Queue(maxsize=1), ctx.Event()
    process = ctx.Process(target=worker, args=(cfg, model, messages, stop), daemon=True)
    gimbal = laser = None
    requested_stop = False

    def request_stop(signum, frame):
        nonlocal requested_stop
        requested_stop = True

    previous_handlers = {
        sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    stream, servo, gate = (
        TargetStream(cfg),
        VisualServo(cfg),
        LightGate(cfg, mode == "paper"),
    )
    started = time.monotonic()
    last_frame = None
    last_capture = None
    frame_count = 0
    next_log = started
    previous_goal = (0.0, 0.0)
    try:
        # Also force output off in track mode. Observe never touches actuator pins.
        if mode != "observe":
            laser = LaserOutput(cfg)
        process.start()
        log.info("START mode=%s model=%s", mode, model)
        while not requested_stop and not app.need_exit():
            tick = time.monotonic()
            if seconds and tick - started >= seconds:
                break
            # Turn off before any potentially delayed I/O.
            if laser:
                laser.set(False)
            message = None
            try:
                message = messages.get_nowait()
            except queue.Empty:
                pass
            if message and message["kind"] == "error":
                raise RuntimeError(message["message"])
            if not process.is_alive():
                raise RuntimeError("VISION_WORKER_EXITED")
            if message:
                last_frame = message
                frame_count += 1
            if last_frame is None:
                if tick - started > 45:
                    raise TimeoutError("VISION_STARTUP_TIMEOUT")
                time.sleep(0.02)
                continue
            if mode != "observe" and gimbal is None:
                gimbal = Gimbal(SerialTransport(cfg), cfg)
                gimbal.start()
                # Discard detections captured before actuator startup.
                last_frame = None
                continue
            now = time.monotonic()
            target, ambiguous = stream.update(message, now)
            if message:
                last_capture = message["captured_at"]
            if gimbal:
                measured = gimbal.poll()
                now = time.monotonic()
                aim = servo.update(target, now, measured, stream.generation)
                eligible = light_eligible(cfg, target, aim, ambiguous, measured, previous_goal, now)
                gimbal.move(aim.yaw, aim.pitch)
                previous_goal = (aim.yaw, aim.pitch)
                light_now = time.monotonic()
                eligible = (
                    eligible
                    and target is not None
                    and light_now - target.captured_at <= cfg.stale_after
                )
                on = gate.update(light_now, eligible=eligible, generation=stream.generation)
                laser.set(on)
            if now >= next_log:
                log.info(
                    "mode=%s frames=%d frame_age=%.3f target=%s measured=%s goal=%s "
                    "v_ref=%s limited=%s rebase=%s light=%s",
                    mode,
                    frame_count,
                    now - last_capture if last_capture is not None else -1,
                    target is not None,
                    gimbal.measured if gimbal else None,
                    previous_goal if gimbal else None,
                    tuple(round(v, 3) for v in servo.velocity) if gimbal else None,
                    aim.limited if gimbal else False,
                    servo.rebase_reason,
                    gate.state.value,
                )
                next_log = now + 1
            # Sleep at most one period; vision process owns slow camera/NPU/display.
            time.sleep(max(0, 1 / cfg.loop_hz - (time.monotonic() - tick)))
    except BaseException:
        gate.fault()
        log.exception("FAULT")
        raise
    finally:
        # Attempt every cleanup independently so one failing device cannot skip others.
        if laser:
            try:
                laser.set(False)
            except Exception:
                log.exception("LASER_OFF_FAILED")
        if gimbal:
            try:
                gimbal.close()
            except Exception:
                log.exception("GIMBAL_CLOSE_FAILED")
            for error in gimbal.errors:
                log.error("gimbal: %s", error)
        stop.set()
        if process.pid is not None:
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        messages.close()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        log.info("STOP")
        for handler in list(log.handlers):
            handler.close()
            log.removeHandler(handler)
