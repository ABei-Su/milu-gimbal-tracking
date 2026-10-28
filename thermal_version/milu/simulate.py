"""Deterministic ideal-plant demonstration. Never opens a device."""

from milu.f32c import position
from milu.tracking import Detection, State, Tracker


def run() -> tuple[float, float, State]:
    tracker = Tracker()
    yaw = pitch = 0.0
    target_yaw, target_pitch = 8.0, -4.0
    for i in range(301):
        now = i * 0.02
        # Synthetic camera: half-image covers 30 degrees on either axis.
        cx = 320 + (target_yaw - yaw) / 30 * 320
        cy = 240 + (target_pitch - pitch) / 30 * 240
        detection = Detection(cx - 10, cy - 10, cx + 10, cy + 10, 640, 480, 0.95, now)
        cmd = tracker.update(detection, now)
        yaw, pitch = cmd.yaw_deg, cmd.pitch_deg
        if i % 50 == 0:
            print(
                f"t={now:4.1f}s {cmd.state.value:8s} yaw={yaw:6.2f} pitch={pitch:6.2f} light={cmd.light_on}"
            )
    print("X position frame:", position(1, round(yaw * 10)).hex(" "))
    print("Y position frame:", position(2, round(pitch * 10)).hex(" "))
    lost = tracker.update(None, 6.6)
    print("After target timeout:", lost.state.value)
    return target_yaw - yaw, target_pitch - pitch, lost.state


if __name__ == "__main__":
    run()
