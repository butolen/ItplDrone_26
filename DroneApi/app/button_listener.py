from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional, Protocol

from serial import Serial, SerialException

from DroneApi.app.button_config import ButtonConfig

logger = logging.getLogger(__name__)

READY_LINE = "READY"
HEARTBEAT_LINE = "HB"
BUTTON_LINE = "BTN"


class SerialPort(Protocol):
    def readline(self) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


class ButtonListener:
    def __init__(
        self,
        config: ButtonConfig,
        on_press: Callable[[], None],
        serial_factory: Optional[Callable[[], SerialPort]] = None,
    ) -> None:
        self._config = config
        self._on_press = on_press
        self._serial_factory = serial_factory or self._open_serial_port
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return

        self._thread = threading.Thread(target=self._run, name="button-listener", daemon=True)
        self._thread.start()
        logger.info(
            "[BUTTON] listener started on %s @ %d baud",
            self._config.serial_port,
            self._config.baud_rate
        )

    def stop(self) -> None:
        self._stop_event.set()

        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._config.read_timeout_seconds + 1.0)

        self._thread = None
        logger.info("[BUTTON] listener stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._read_until_disconnect()

            if self._stop_event.wait(self._config.reconnect_interval_seconds):
                return

    def _read_until_disconnect(self) -> None:
        port: Optional[SerialPort] = None

        try:
            port = self._serial_factory()
        except (SerialException, OSError) as exception:
            logger.warning(
                "[BUTTON] cannot open %s (%s), retrying in %.0f s",
                self._config.serial_port,
                exception,
                self._config.reconnect_interval_seconds
            )
            return

        logger.info("[BUTTON] serial port %s open", self._config.serial_port)

        try:
            self._settle_after_open(port)
            self._read_lines(port)
        except (SerialException, OSError) as exception:
            logger.warning(
                "[BUTTON] serial error on %s (%s), reconnecting in %.0f s",
                self._config.serial_port,
                exception,
                self._config.reconnect_interval_seconds
            )
        finally:
            self._close(port)

    def _settle_after_open(self, port: SerialPort) -> None:
        # Opening the port toggles DTR and reboots the Uno, so everything sent
        # while it boots (and any press queued before) is discarded.
        self._stop_event.wait(self._config.open_settle_seconds)
        port.reset_input_buffer()

    def _read_lines(self, port: SerialPort) -> None:
        last_line_time = time.monotonic()

        while not self._stop_event.is_set():
            raw_line = port.readline()

            if raw_line:
                last_line_time = time.monotonic()
                self._handle_line(raw_line)
                continue

            if time.monotonic() - last_line_time >= self._config.heartbeat_timeout_seconds:
                logger.warning(
                    "[BUTTON] no line from %s for %.1f s, closing port",
                    self._config.serial_port,
                    self._config.heartbeat_timeout_seconds
                )
                return

    def _handle_line(self, raw_line: bytes) -> None:
        line = raw_line.decode("ascii", errors="ignore").strip()

        if line == BUTTON_LINE:
            logger.info("[BUTTON] press received")
            self._notify_press()
        elif line == READY_LINE:
            logger.info("[BUTTON] board reported READY")
        elif line == HEARTBEAT_LINE:
            logger.debug("[BUTTON] heartbeat")
        elif line:
            logger.debug("[BUTTON] ignoring unexpected line: %r", line)

    def _notify_press(self) -> None:
        try:
            self._on_press()
        except Exception:
            logger.exception("[BUTTON] press handler failed")

    def _open_serial_port(self) -> SerialPort:
        return Serial(
            port=self._config.serial_port,
            baudrate=self._config.baud_rate,
            timeout=self._config.read_timeout_seconds,
        )

    @staticmethod
    def _close(port: Optional[SerialPort]) -> None:
        if port is None:
            return

        try:
            port.close()
        except (SerialException, OSError):
            logger.debug("[BUTTON] closing the serial port failed", exc_info=True)
        else:
            logger.info("[BUTTON] serial port closed")
