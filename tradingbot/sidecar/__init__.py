"""Local broker sidecar — a thin loopback HTTP wrapper around the existing
``build_broker(config, mode="local")`` stack, spawned by the Electron desktop
shell so the renderer can drive a TWS / IB Gateway running on the same machine.

See docs/superpowers/specs/2026-05-30-electron-desktop-local-broker-design.md
"""
