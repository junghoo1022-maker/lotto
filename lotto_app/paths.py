"""데이터 파일 위치. exe로 실행하면 exe 옆 폴더, 소스로 실행하면 저장소 루트."""
import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    d = base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


DB_PATH = None  # 테스트에서 덮어쓸 수 있도록 지연 계산


def db_path() -> Path:
    return Path(DB_PATH) if DB_PATH else data_dir() / "lotto_data.db"


def log_path() -> Path:
    return data_dir() / "fetch_log.txt"
