"""Bounded position queries only: never enable, move or save motor parameters."""

import json
import time
from milu import f32c
from milu.settings import load_settings


def probe(port, motor, clock=time.monotonic, sleep=time.sleep):
    request = f32c.query(motor, 1)
    port.clear_input()
    port.send(request)
    parser = f32c.FeedbackParser()
    received = bytearray()
    count = 0
    deadline = clock() + 0.5
    result = {"motor": motor, "tx_hex": request.hex(" "), "status": "NO_BYTES"}
    while clock() < deadline:
        data = port.read()
        count += len(data)
        received.extend(data[: max(0, 128 - len(received))])
        for feedback in parser.feed(data):
            if feedback.motor == motor and feedback.kind == 1:
                result.update(status="VALID", position_deg=feedback.value)
                break
        if result["status"] == "VALID":
            break
        sleep(0.002)
    if count and result["status"] != "VALID":
        result["status"] = "UNMATCHED_BYTES"
    result.update(rx_bytes=count, rx_hex=received.hex(" "))
    return result


def run(config_path):
    from milu.maixcam2 import check_board, release_default_listener, SerialTransport

    cfg = load_settings(config_path)
    check_board()
    release_default_listener()
    print("[DIAG] QUERY ONLY: no motor enable/move/ID change; no camera", flush=True)
    print(f"[DIAG] {cfg.uart_device} 115200 8N1 TX={cfg.tx_pin} RX={cfg.rx_pin}", flush=True)
    port = SerialTransport(cfg)
    try:
        time.sleep(cfg.boot_wait)
        for attempt in range(1, 4):
            for motor in (1, 2):
                result = probe(port, motor)
                print("[DIAG] " + json.dumps({"attempt": attempt, **result}), flush=True)
        print("[DIAG] DONE. Send all six result lines for analysis.", flush=True)
    finally:
        port.close()
