import logging
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOGGING_LEVEL = logging.DEBUG
LOGGER = logging.getLogger("m2r")

LOGGER.setLevel(LOGGING_LEVEL)

handler = logging.StreamHandler()
handler.setLevel(LOGGING_LEVEL)
LOGGER.addHandler(handler)


__all__ = [
    "PROJECT_DIR",
    "LOGGING_LEVEL",
    "LOGGER",
]
