from __future__ import annotations

import time
from typing import Any, Optional

from serial import SerialException

from conftest import wait_until
from DroneApi.app.button_config import ButtonConfig
from DroneApi.app.button_listener import ButtonListener

PROTOCOL_LINES = [
    b"READY\r\n",
    b"HB\r\n",
    b"BTN\r\n",
    b"\x00\xffnot a command\r\n",
    b"HB\r\n",
]


class FakeSerialPort:
    def __init__(self, lines: Optional[list[bytes]] = None, fail_after: Optional[int] = None) -> None:
        self._lines = list(lines or [])
        self._fail_after = fail_after
        self._reads = 0
        self.closed = False
        self.input_buffer_resets = 0

    def readline(self) -> bytes:
        self._reads += 1

        if self._fail_after is not None and self._reads > self._fail_after:
            raise SerialException("cable unplugged")

        if self._lines:
            return self._lines.pop(0)

        # Silence, the way a real port behaves once its read timeout expires.
        time.sleep(0.01)
        return b""

    def reset_input_buffer(self) -> None:
        self.input_buffer_resets += 1

    def close(self) -> None:
        self.closed = True


def fast_config(**overrides: Any) -> ButtonConfig:
    settings: dict[str, Any] = {
        "serial_port": "COM_TEST",
        "open_settle_seconds": 0.0,
        "heartbeat_timeout_seconds": 0.15,
        "reconnect_interval_seconds": 0.01,
        "read_timeout_seconds": 0.01,
    }
    settings.update(overrides)
    return ButtonConfig(**settings)


def test_reads_protocol_lines_and_reconnects_after_silence() -> None:
    presses: list[str] = []
    ports: list[FakeSerialPort] = []

    def serial_factory() -> FakeSerialPort:
        # Only the first connection replays the protocol; later ones stay silent.
        port = FakeSerialPort(PROTOCOL_LINES if not ports else [])
        ports.append(port)
        return port

    listener = ButtonListener(fast_config(), on_press=lambda: presses.append("BTN"), serial_factory=serial_factory)
    listener.start()
    try:
        assert wait_until(lambda: len(ports) >= 2)
    finally:
        listener.stop()

    assert presses == ["BTN"], "READY, HB and garbage must not trigger a press"
    assert ports[0].input_buffer_resets == 1, "input buffer is flushed after the boot settle"
    assert ports[0].closed, "heartbeat loss closes the port"


def test_serial_exception_while_reading_triggers_reconnect() -> None:
    ports: list[FakeSerialPort] = []

    def serial_factory() -> FakeSerialPort:
        port = FakeSerialPort([b"READY\r\n"], fail_after=1 if not ports else None)
        ports.append(port)
        return port

    listener = ButtonListener(fast_config(), on_press=lambda: None, serial_factory=serial_factory)
    listener.start()
    try:
        assert wait_until(lambda: len(ports) >= 2)
    finally:
        listener.stop()

    assert ports[0].closed


def test_missing_port_at_startup_is_retried_forever() -> None:
    attempts: list[int] = []
    presses: list[str] = []

    def serial_factory() -> FakeSerialPort:
        attempts.append(len(attempts))
        if len(attempts) < 3:
            raise SerialException("could not open port 'COM_TEST'")
        return FakeSerialPort([b"BTN\r\n"])

    listener = ButtonListener(fast_config(), on_press=lambda: presses.append("BTN"), serial_factory=serial_factory)
    listener.start()
    try:
        assert wait_until(lambda: presses)
    finally:
        listener.stop()

    assert len(attempts) >= 3, "the listener keeps retrying instead of dying"
    assert presses == ["BTN"]


def test_press_handler_errors_do_not_kill_the_reader() -> None:
    ports: list[FakeSerialPort] = []

    def serial_factory() -> FakeSerialPort:
        port = FakeSerialPort([b"BTN\r\n"] if not ports else [])
        ports.append(port)
        return port

    def explode() -> None:
        raise RuntimeError("spin failed")

    listener = ButtonListener(fast_config(), on_press=explode, serial_factory=serial_factory)
    listener.start()
    try:
        assert wait_until(lambda: len(ports) >= 2)
    finally:
        listener.stop()
