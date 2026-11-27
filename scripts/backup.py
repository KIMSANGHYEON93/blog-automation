"""n8n 워크플로·자격증명과 Google Sheets 탭을 로컬에 백업한다(원격 백업은 범위 밖).

- n8n: 컨테이너에서 `n8n export:workflow/credentials --all` + 암호화 키 파일(config)을 묶어
  `backups/n8n/n8n_YYYYMMDD_HHMMSS.tar.gz` 로 저장. 자격증명은 n8n이 암호화한 채로 내보낸다.
- Sheets: 모든 탭을 읽기 전용 범위로 읽어 `backups/sheets/YYYYMMDD_HHMMSS/<탭>.csv` 로 저장.
- 각각 최근 `--keep`(기본 7)개만 남긴다. 파일은 0600, 디렉터리는 0700. `backups/` 는 gitignore.

운영 데이터는 읽기만 한다(시트·n8n 변경 없음). `--dry-run` 은 아무 파일도 만들지 않는다.
종료 코드: 0 성공, 1 하나 이상 실패.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path

# run_pipeline_b.sh 와 같은 규약: BLOG_PROJECT_DIR 로 운영 저장소를 가리킬 수 있다
PROJECT_DIR = Path(os.getenv("BLOG_PROJECT_DIR") or Path(__file__).resolve().parents[1])
# 저장 위치는 BLOG_BACKUP_DIR 로 바꿀 수 있다(외장 디스크·iCloud 등을 쓰기로 정했을 때)
BACKUP_DIR = Path(os.getenv("BLOG_BACKUP_DIR") or PROJECT_DIR / "backups")
N8N_CONTAINER = "blog-automation-n8n-1"
CONTAINER_WORK_DIR = "/tmp/bk"
N8N_CONFIG_PATH = "/home/node/.n8n/config"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DEFAULT_KEEP = 7
SUBPROCESS_TIMEOUT = 300
CONTAINER_CHECK_TRIES = 3  # 메모리 스래싱 중 docker inspect 일시 실패 방지(2026-11-26)
CONTAINER_CHECK_DELAY = 10  # 재시도 사이 대기(초)

logger = logging.getLogger("backup")


# --- 순수 함수 (테스트 대상) ------------------------------------------------------------------

def safe_name(title: str) -> str:
    """탭 이름을 파일 이름으로 쓸 수 있게 바꾼다(경로 문자 제거, 한글은 유지)."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title).strip(" .")
    return cleaned or "_"


def prune(directory: Path, prefix: str, keep: int) -> list:
    """`prefix` 로 시작하는 항목을 이름순(= 시각순)으로 보고 최근 keep 개만 남긴다.

    지운 목록을 돌려준다.
    """
    if not directory.is_dir():
        return []
    items = sorted(p for p in directory.iterdir() if p.name.startswith(prefix))
    doomed = items[:-keep] if keep > 0 else items
    for path in doomed:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return doomed


def validate_workflows(text: str) -> int:
    """내보낸 워크플로 JSON이 비어 있지 않은 목록인지 확인하고 개수를 돌려준다."""
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        raise ValueError("워크플로 내보내기가 비어 있음")
    return len(data)


def write_csv(path: Path, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    path.chmod(0o600)


def write_sheet_snapshot(target: Path, tabs: dict) -> dict:
    """tabs: {탭 이름: 2차원 값 목록} → target/<탭>.csv + manifest.json. manifest 를 돌려준다."""
    target.mkdir(parents=True, mode=0o700)
    manifest = {}
    for title, rows in tabs.items():
        write_csv(target / f"{safe_name(title)}.csv", rows)
        manifest[title] = {"rows": len(rows), "cols": max((len(r) for r in rows), default=0)}
    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path.chmod(0o600)
    return manifest


# --- 외부 호출 --------------------------------------------------------------------------------

def _run(cmd: list) -> str:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT, check=True
    ).stdout


def container_running() -> bool:
    """컨테이너가 running 이면 True. 조회가 일시 실패하면 몇 번 더 시도한다."""
    for attempt in range(1, CONTAINER_CHECK_TRIES + 1):
        try:
            out = _run(["docker", "inspect", "-f", "{{.State.Status}}", N8N_CONTAINER])
            return out.strip() == "running"
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("docker inspect 실패 %d/%d: %s", attempt, CONTAINER_CHECK_TRIES,
                           type(e).__name__)
            if attempt < CONTAINER_CHECK_TRIES:
                time.sleep(CONTAINER_CHECK_DELAY)
    return False


def backup_n8n(stamp: str, keep: int, dry_run: bool) -> str:
    if not container_running():
        raise RuntimeError(f"n8n 컨테이너({N8N_CONTAINER})가 실행 중이 아님")
    if dry_run:
        return "n8n: 워크플로·자격증명 내보내기 + config → tar.gz (dry-run, 파일 안 만듦)"
    out_dir = BACKUP_DIR / "n8n"
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    work = CONTAINER_WORK_DIR
    script = (
        f"rm -rf {work} && mkdir -p {work} && "
        f"n8n export:workflow --all --output={work}/workflows.json && "
        f"n8n export:credentials --all --output={work}/credentials.json && "
        f"cp {N8N_CONFIG_PATH} {work}/config"
    )
    try:
        _run(["docker", "exec", N8N_CONTAINER, "sh", "-c", script])
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            _run(["docker", "cp", f"{N8N_CONTAINER}:{work}/.", tmp])
            count = validate_workflows((Path(tmp) / "workflows.json").read_text(encoding="utf-8"))
            archive = out_dir / f"n8n_{stamp}.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name in ("workflows.json", "credentials.json", "config"):
                    tar.add(Path(tmp) / name, arcname=name)
            archive.chmod(0o600)
    finally:
        subprocess.run(
            ["docker", "exec", N8N_CONTAINER, "rm", "-rf", work], capture_output=True, timeout=60
        )
    removed = prune(out_dir, "n8n_", keep)
    return f"n8n: {archive.name} (워크플로 {count}개, 오래된 {len(removed)}개 삭제)"


def _open_spreadsheet():
    import gspread
    from dotenv import load_dotenv
    from google.oauth2.service_account import Credentials

    load_dotenv(PROJECT_DIR / ".env")
    creds_path = os.getenv("GOOGLE_CREDS", "credentials.json")
    if not os.path.isabs(creds_path):
        creds_path = str(PROJECT_DIR / creds_path)
    client = gspread.authorize(
        Credentials.from_service_account_file(creds_path, scopes=SHEETS_SCOPES)
    )
    sheet_id = os.getenv("SHEET_ID", "")
    if sheet_id:
        return client.open_by_key(sheet_id)
    return client.open(os.getenv("SHEET_NAME", "keyword_calendar_v2"))


def backup_sheets(stamp: str, keep: int, dry_run: bool) -> str:
    worksheets = _open_spreadsheet().worksheets()
    if dry_run:
        names = ", ".join(ws.title for ws in worksheets)
        return f"sheets: 탭 {len(worksheets)}개 읽기 가능 [{names}] (dry-run, 파일 안 만듦)"
    out_dir = BACKUP_DIR / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    tabs = {ws.title: ws.get_all_values() for ws in worksheets}
    manifest = write_sheet_snapshot(out_dir / stamp, tabs)
    removed = prune(out_dir, "20", keep)
    total = sum(m["rows"] for m in manifest.values())
    return f"sheets: {stamp} (탭 {len(manifest)}개, {total}행, 오래된 {len(removed)}개 삭제)"


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="읽기 가능 여부만 확인, 파일 안 만듦"
    )
    parser.add_argument("--only", choices=("n8n", "sheets"), help="한쪽만 실행")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="보관 개수(기본 7)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    os.umask(0o077)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jobs = {"n8n": backup_n8n, "sheets": backup_sheets}
    failed = 0
    for name, job in jobs.items():
        if args.only and args.only != name:
            continue
        try:
            logger.info(job(stamp, args.keep, args.dry_run))
        except Exception as e:  # 한쪽이 실패해도 다른 쪽은 계속한다
            failed += 1
            logger.error(f"{name} 백업 실패: {type(e).__name__}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
