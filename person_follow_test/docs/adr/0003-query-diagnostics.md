# ADR 0003 Read-only motor diagnostic
Accepted 2026-10-12. Persistent NO_FEEDBACK after listener release and both wiring orientations needs raw UART evidence.
Add diagnose CLI mode; temporarily select it as RUN_MODE for this hardware session. No camera, laser access, motor enable, position command, reset, ID change or Flash write. Query only known IDs 1 and 2 three times each, 500ms receive window, at most 128 bytes retained per result. Existing UART read bounded at 256 bytes. Close transport in finally. Diagnose does not stop motors already enabled by other software; begin from stopped experiment.
NO_BYTES means no received bytes in this window; UNMATCHED_BYTES means bytes without matching valid ID/type/checksum; VALID means matching position reply, not complete hardware acceptance. No scan outside documented project IDs and no automatic switch into tracking.
Restore RUN_MODE track after communication is verified. Original deer projects unchanged.
