"""Board application orchestration. Main process exclusively owns actuators."""

import logging
from logging.handlers import RotatingFileHandler
import multiprocessing as mp
from pathlib import Path
import queue
import signal
import time

from milu.gimbal import Gimbal
from milu.settings import load_settings
from milu.targeting import TargetStream, VisualServo
from milu.vision import worker


def light_eligible(*args, **kwargs):
    """Compatibility for offline checks: person test never permits laser."""
    return False


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


def run(config_path, mode="track", seconds=0):
    if mode not in ("observe", "track"):
        raise ValueError("mode must be observe or track")
    cfg = load_settings(config_path)
    root = Path(config_path).resolve().parent
    from milu.maixcam2 import LaserOutput, SerialTransport, check_board, verify_model

    check_board()
    from milu.maixcam2 import release_default_listener

    release_default_listener()
    log = configure_log(root)
    from maix import app

    if cfg.target_kind == "face":
        from milu.head_model import resolve_face_model

        model, _ = resolve_face_model(cfg.model if cfg.model == "auto:face" else root / cfg.model)
    else:
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
    stream, servo = TargetStream(cfg), VisualServo(cfg)
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
        log.info("START mode=%s model=%s", mode, model)
        searching = mode != "observe" and cfg.search_during_lift
        search = None
        if searching:
            from milu.startup_search import StartupSearch

            process.start()
            search = StartupSearch(cfg, messages, process, clock=time.monotonic)
            search.wait_ready(lambda: requested_stop or app.need_exit(), sleep=time.sleep)
        if mode != "observe":
            gimbal = Gimbal(SerialTransport(cfg), cfg)
            gimbal.start(
                cancelled=lambda: requested_stop or app.need_exit(),
                acquired=search.acquired if search else lambda: False,
            )
        if requested_stop or app.need_exit():
            return
        # Vision has its own startup budget after bounded homing completes.
        started = time.monotonic()
        if not searching:
            process.start()
        metrics_started = started
        metric_ticks = metric_frames = 0
        vision_latency = poll_ms = 0.0
        while not requested_stop and not app.need_exit():
            tick = time.monotonic()
            metric_ticks += 1
            if seconds and tick - started >= seconds:
                break
            # Turn off before any potentially delayed I/O.
            if laser:
                laser.set(False)
            # Poll first: consume any newer image arriving during bounded UART I/O.
            if gimbal:
                poll_started = time.monotonic()
                measured = gimbal.poll()
                poll_ms = (time.monotonic() - poll_started) * 1000
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
                metric_frames += 1
                vision_latency = message.get("latency", 0.0)
            if last_frame is None:
                if tick - started > 45:
                    raise TimeoutError("VISION_STARTUP_TIMEOUT")
                time.sleep(0.02)
                continue
            now = time.monotonic()
            target, ambiguous = stream.update(message, now)
            if message:
                last_capture = message["captured_at"]
            if gimbal:
                now = time.monotonic()
                aim = servo.update(target, now, measured, stream.generation)
                gimbal.move(aim.yaw, aim.pitch)
                previous_goal = (aim.yaw, aim.pitch)
            if now >= next_log:
                log.info(
                    "mode=%s frames=%d frame_age=%.3f target=%s measured=%s goal=%s "
                    "v_ref=%s lead_deg=%s limited=%s rebase=%s light=%s "
                    "control_hz=%.1f vision_fps=%.1f vision_ms=%.1f poll_ms=%.1f",
                    mode,
                    frame_count,
                    now - last_capture if last_capture is not None else -1,
                    target is not None,
                    gimbal.measured if gimbal else None,
                    previous_goal if gimbal else None,
                    tuple(round(v, 3) for v in servo.velocity) if gimbal else None,
                    tuple(round(g - m, 3) for g, m in zip(previous_goal, measured))
                    if gimbal
                    else None,
                    aim.limited if gimbal else False,
                    servo.rebase_reason,
                    "DISABLED",
                    metric_ticks / max(now - metrics_started, 0.001),
                    metric_frames / max(now - metrics_started, 0.001),
                    vision_latency * 1000,
                    poll_ms,
                )
                metrics_started = now
                metric_ticks = metric_frames = 0
                next_log = now + 1
            # Sleep at most one period; vision process owns slow camera/NPU/display.
            time.sleep(max(0, 1 / cfg.loop_hz - (time.monotonic() - tick)))
    except BaseException:
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
