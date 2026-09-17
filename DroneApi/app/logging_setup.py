from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

VIENNA_TIMEZONE = ZoneInfo("Europe/Vienna")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %Z"


class ViennaFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        moment = datetime.fromtimestamp(record.created, VIENNA_TIMEZONE)
        return moment.strftime(datefmt or LOG_DATE_FORMAT)


def configure_logging(level: int = logging.INFO) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if any(isinstance(handler.formatter, ViennaFormatter) for handler in root_logger.handlers):
        return

    handler = logging.StreamHandler()
    handler.setFormatter(ViennaFormatter(fmt=LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root_logger.addHandler(handler)
