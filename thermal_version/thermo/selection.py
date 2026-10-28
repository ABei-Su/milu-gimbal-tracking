"""Pure touch and selected-patch state machine; no automatic reacquisition."""

from enum import Enum
import math
from milu.tracking import Detection


class TrackState(str, Enum):
    SELECTING = "SELECTING"
    DRAGGING = "DRAGGING"
    TRACKING = "TRACKING"
    LOST = "LOST"


class Selection:
    def __init__(self, width, height, cfg):
        if width < 320 or height < 240:
            raise ValueError("display too small")
        self.width, self.height, self.cfg = width, height, cfg
        self._state = TrackState.SELECTING
        self.session = 0
        self.motion = False
        self.pressed = False
        self.start = None
        self.button = None
        self.box = None

    @property
    def state(self):
        return self._state

    def _button(self, x, y):
        if y < self.height - 44:
            return None
        if x < 110:
            return "SELECT"
        if x < 240:
            return "MOTION"
        if x > self.width - 100:
            return "EXIT"
        return None

    def touch(self, x, y, pressed):
        x = max(0, min(self.width - 1, int(x)))
        y = max(0, min(self.height - 1, int(y)))
        pressed = bool(pressed)
        event = None
        if pressed and not self.pressed:
            self.button = self._button(x, y)
            if (
                self.button is None
                and y >= 96
                and self.state in (TrackState.SELECTING, TrackState.LOST)
            ):
                self.start = (x, y)
                self._state = TrackState.DRAGGING
                self.box = None
        if not pressed and self.pressed:
            if self.button is not None:
                if self._button(x, y) == self.button:
                    if self.button == "SELECT":
                        self._state = TrackState.SELECTING
                        self.box = None
                        self.session += 1
                        event = ("clear", None)
                    elif self.button == "MOTION":
                        self.motion = not self.motion
                        event = ("motion", self.motion)
                    else:
                        event = ("exit", None)
            elif self.state == TrackState.DRAGGING:
                sx, sy = self.start
                y = max(96, min(y, self.height - 45))
                x1, y1 = min(x, sx), min(y, sy)
                w, h = abs(x - sx), abs(y - sy)
                if w >= 16 and h >= 16:
                    self.box = (x1, y1, w, h)
                    self.session += 1
                    self._state = TrackState.TRACKING
                    event = ("init", self.box)
                else:
                    self._state = TrackState.SELECTING
            self.start = None
            self.button = None
        self.pressed = pressed
        return event

    def lost(self):
        self._state = TrackState.LOST
        self.box = None

    def accept(self, result, captured):
        if self.state != TrackState.TRACKING:
            return None
        fields = (result.x, result.y, result.w, result.h, result.score)
        if any(not math.isfinite(v) for v in fields) or result.score < self.cfg.tracker_threshold:
            self.lost()
            return None
        x, y, w, h, score = fields
        if w < 4 or h < 4 or x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            self.lost()
            return None
        if self.box:
            ox, oy, ow, oh = self.box
            jump = math.hypot(
                (x + w / 2 - ox - ow / 2) / self.width, (y + h / 2 - oy - oh / 2) / self.height
            )
            if jump > self.cfg.max_box_jump or not 0.4 <= w * h / (ow * oh) <= 2.5:
                self.lost()
                return None
        self.box = (x, y, w, h)
        d = Detection(x, y, x + w, y + h, self.width, self.height, score, captured)
        d.validate()
        return d
