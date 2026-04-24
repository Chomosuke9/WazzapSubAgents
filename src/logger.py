import logging
import sys
from pythonjsonlogger import jsonlogger


def get_logger(name: str = "executor-service") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(message)s %(name)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
