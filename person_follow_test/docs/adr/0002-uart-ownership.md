# ADR 0002 UART ownership
Accepted 2026-10-12. User board logs show Maix Comm Protocol listening on UART4 in both parent and spawned vision process while raw Linux SerialTransport also uses /dev/ttyS4. Raw os.open bypasses SDK UART takeover callbacks, allowing competing readers.
Call maix.comm.rm_default_comm_listener() in each process after SDK import and board validation, before model initialization or actuator startup. Require True and propagate errors; no persistent system setting changes or automatic retries. The first frame is only published after worker removal, so the parent cannot start the motor session before the child releases its reader.
Official source inspected: https://raw.githubusercontent.com/sipeed/MaixCDK/main/components/comm/src/maix_comm_protocol.cpp
API: https://wiki.sipeed.com/maixpy/api/maix/comm.html
The official implementation joins its listener thread and deletes its protocol instance; an already absent listener returns True. SDK shutdown internally has no timeout parameter; a driver hang requires stopping the application. This call occurs before motor enable. Existing vision startup timeout remains.
Maix protocol UART remote control is unavailable within this app; use MaixVision network connection. No F32C command, timing, pins, limits or laser behavior changed. Board recovery is not yet verified. Power, wiring and motor ID remain possible additional causes of NO_FEEDBACK.
Tests cover API invocation, missing API, false result, exception propagation, and invocation in both runtime and vision worker. Full suite: 94 passing offline tests.
