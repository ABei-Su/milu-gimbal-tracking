"""Thermal orchestration: actuator owner, vision UI, and supervised sensor."""

from dataclasses import asdict
import multiprocessing as mp
from pathlib import Path
import signal
import time
from milu.gimbal import Gimbal
from milu.maixcam2 import LaserOutput, SerialTransport, check_board
from milu.runtime import configure_log
from milu.settings import load_settings
from milu.targeting import VisualServo
from milu.vision import publish_latest
from thermo.config import load_config
from thermo.temperature import TemperatureGate, roi_covered
from thermo.ui import worker as vision_worker, get_latest
from thermo.sensor import worker as sensor_worker


def measurement_reason(
    base, cfg, target, aim, measured, previous_goal, speed, now, motion, sensor_ready
):
    if not motion:
        return "ENABLE_TRACK"
    if target is None:
        return "SELECT_OR_RESELECT_EYE"
    if not 0 <= now - target.captured_at <= base.stale_after:
        return "STALE_VISION"
    if not cfg.alignment_confirmed:
        return "ALIGN_RGB_IR_FIRST"
    if not roi_covered(target, base, cfg):
        return "EYE_TOO_SMALL_FOR_IR_ROI"
    if aim is None or aim.limited or not aim.centered:
        return "CENTER_AND_HOLD"
    if speed > cfg.measured_settle_rate or any(
        abs(m - g) > base.reached_tolerance for m, g in zip(measured, previous_goal)
    ):
        return "GIMBAL_MOVING"
    if not sensor_ready:
        return "SENSOR_NOT_READY"
    return ""


def stop_process(process, log):
    if process.pid is None:
        return
    process.join(timeout=1)
    if process.is_alive():
        process.terminate()
        process.join(timeout=1)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)
    if process.is_alive():
        log.error("WORKER_DID_NOT_EXIT pid=%s", process.pid)


def run(base_path, thermal_path, seconds=0):
    base = load_settings(base_path)
    cfg = load_config(thermal_path)
    cfg.check_pins(base)
    check_board()
    root = Path(base_path).resolve().parent
    log = configure_log(root)
    ctx = mp.get_context("spawn")
    frames, statuses, thermal = ctx.Queue(maxsize=1), ctx.Queue(maxsize=1), ctx.Queue(maxsize=1)
    stop = ctx.Event()
    vision = ctx.Process(
        target=vision_worker, args=(base, cfg, frames, statuses, stop), daemon=True
    )
    sensor = ctx.Process(target=sensor_worker, args=(cfg, thermal, stop), daemon=True)
    processes = (vision, sensor)
    gimbal = laser = None
    gate = TemperatureGate(cfg)
    servo = VisualServo(base)
    started = time.monotonic()
    last_visual = last_thermal = None
    previous_goal = (0.0, 0.0)
    previous_measurement = None
    sensor_error = (
        "VENDOR_PROTOCOL_REQUIRED" if cfg.sensor_backend == "pending_uart" else "WAIT_SENSOR"
    )
    sensor_started = False
    next_log = started
    handlers = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, lambda *_: stop.set())
        # Thermal eye measurements never enable the laser, even after UI interaction.
        laser = LaserOutput(base)
        vision.start()
        if cfg.sensor_confirmed and cfg.sensor_backend != "pending_uart":
            sensor.start()
            sensor_started = True
        while not stop.is_set():
            tick = time.monotonic()
            if seconds and tick - started >= seconds:
                break
            laser.set(False)
            message = get_latest(frames)
            if message:
                if message["kind"] == "error":
                    raise RuntimeError(message["message"])
                last_visual = message
            if not vision.is_alive():
                raise RuntimeError("THERMAL_VISION_EXITED")
            thermal_message = get_latest(thermal)
            if thermal_message:
                if thermal_message["kind"] == "sensor_error":
                    sensor_error = thermal_message["message"]
                    last_thermal = None
                else:
                    last_thermal = thermal_message
                    sensor_error = ""
            if sensor_started and not sensor.is_alive():
                last_thermal = None
                sensor_error = sensor_error or "SENSOR_WORKER_EXITED"
            now = time.monotonic()
            fresh = (
                last_visual is not None
                and 0 <= now - last_visual["captured_at"] <= base.stale_after
            )
            target = last_visual["target"] if fresh else None
            motion = bool(fresh and last_visual["motion"])
            session = last_visual["session"] if last_visual else 0
            if last_visual is None and now - started > 45:
                raise TimeoutError("THERMAL_VISION_STARTUP_TIMEOUT")
            if motion and target is not None and gimbal is None:
                gimbal = Gimbal(SerialTransport(base), base)
                gimbal.start()
                servo = VisualServo(base)
                previous_measurement = None
                last_visual = None
                continue
            aim = None
            speed = float("inf")
            measured = (0.0, 0.0)
            if gimbal:
                measured = gimbal.poll()
                now = time.monotonic()
                if previous_measurement:
                    old_time, old_position = previous_measurement
                    speed = max(abs(a - b) for a, b in zip(measured, old_position)) / (
                        now - old_time
                    )
                previous_measurement = (now, measured)
                aim = servo.update(target if motion else None, now, measured, session)
                reason = measurement_reason(
                    base,
                    cfg,
                    target,
                    aim,
                    measured,
                    previous_goal,
                    speed,
                    now,
                    motion,
                    not sensor_error,
                )
                gimbal.move(aim.yaw, aim.pitch)
                previous_goal = (aim.yaw, aim.pitch)
            else:
                reason = "ENABLE_TRACK" if not motion else "WAIT_EYE"
            after = time.monotonic()
            if target is not None and after - target.captured_at > base.stale_after:
                reason = "STALE_VISION"
            if (
                not last_thermal
                or not 0 <= after - last_thermal["captured_at"] <= cfg.sensor_timeout
            ):
                sensor_error = sensor_error or "SENSOR_TIMEOUT"
                if not reason:
                    reason = "SENSOR_TIMEOUT"
            # A new good sensor frame clears recoverable sensor_error above.
            reading = gate.update(
                after, session=session, eligible=not reason, reason=reason, frame=last_thermal
            )
            gimbal_status = (
                "OFF"
                if gimbal is None
                else ("HOLD" if not motion else ("LOCKED" if not reason else "TRACKING"))
            )
            publish_latest(
                statuses,
                {
                    "at": after,
                    "session": session,
                    "gimbal": gimbal_status,
                    "reading": asdict(reading),
                    "sensor_error": sensor_error,
                },
            )
            if after >= next_log:
                log.info(
                    "THERMAL session=%s state=%s reason=%s temp=%s sensor=%s",
                    session,
                    reading.state,
                    reading.reason,
                    reading.value,
                    sensor_error,
                )
                next_log = after + 1
            time.sleep(max(0, 1 / base.loop_hz - (time.monotonic() - tick)))
    except BaseException:
        log.exception("THERMAL_FAULT")
        raise
    finally:
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
                log.error(error)
        stop.set()
        for process in processes:
            try:
                stop_process(process, log)
            except Exception:
                log.exception("WORKER_CLEANUP_FAILED")
        for channel in (frames, statuses, thermal):
            try:
                channel.cancel_join_thread()
                channel.close()
            except Exception:
                log.exception("QUEUE_CLEANUP_FAILED")
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        for handler in list(log.handlers):
            handler.close()
            log.removeHandler(handler)
