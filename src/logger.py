import logging
import sys

try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:
    try:
        from pythonjsonlogger.jsonlogger import JsonFormatter
    except ImportError:
        from pythonjsonlogger import JsonFormatter


def get_logger(name: str = "executor-service") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(message)s %(name)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
