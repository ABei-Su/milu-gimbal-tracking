"""Fresh visual acquisition during bounded startup lift; no actuator ownership."""

import queue
import time
from milu.targeting import TargetStream


class StartupSearch:
    def __init__(self, cfg, channel, process, clock=time.monotonic):
        self.cfg, self.channel, self.process, self.clock = cfg, channel, process, clock
        self.stream = TargetStream(cfg)
        self.ready = False

    def acquired(self):
        if not self.process.is_alive():
            raise RuntimeError("VISION_WORKER_EXITED")
        try:
            message = self.channel.get_nowait()
        except queue.Empty:
            message = None
        if message and message["kind"] == "error":
            raise RuntimeError(message["message"])
        now = self.clock()
        if message and 0 <= now - message["captured_at"] <= self.cfg.stale_after:
            self.ready = True
        target, _ = self.stream.update(message, now)
        return target is not None and target.confidence >= self.cfg.confidence

    def wait_ready(self, cancelled, sleep=time.sleep):
        deadline = self.clock() + 45
        while not self.ready:
            if cancelled():
                raise InterruptedError("SEARCH_CANCELLED")
            if self.clock() >= deadline:
                raise TimeoutError("VISION_STARTUP_TIMEOUT")
            self.acquired()
            if not self.ready:
                sleep(0.02)
