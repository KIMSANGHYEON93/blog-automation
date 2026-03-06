"""Logging setup — stdout + optional file handler."""
import logging
import sys
from pathlib import Path


def setup_logging(log_file: str = "logs/blog-publisher.log") -> None:
    log_path = Path(log_file)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except PermissionError:
        pass  # 로그 파일 쓰기 권한 없으면 stdout만

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )
