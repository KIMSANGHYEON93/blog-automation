"""Google Sheets 성과 대시보드 자동 업데이트 스크립트.

키워드 캘린더 운영 데이터를 읽어 성과 대시보드 탭의 상태 요약, 품질 지표,
주간 KPI를 자동으로 갱신한다. 사용 가이드의 구버전 컬럼 참조도 수정한다.

사용법:
    python scripts/update_dashboard.py              # 실행
    python scripts/update_dashboard.py --dry-run    # 미리보기만
    python scripts/update_dashboard.py --skip-sheet2  # 사용 가이드 수정 생략
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build as gapi_build

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# === 키워드 캘린더 컬럼 인덱스 (0-based, column_map.py COL 값 - 1) ===
IDX_NO = 0            # A: No.
IDX_KEYWORD = 1       # B: 키워드
IDX_CATEGORY = 2      # C: 카테고리
IDX_CONTENT_TYPE = 3  # D: 콘텐츠유형
IDX_SEARCH_VOL = 4    # E: 검색볼륨
IDX_STATUS = 9        # J: 상태
IDX_CONTENT = 15      # P: 본문마크다운
IDX_PUBLISHED_URL = 16  # Q: 발행URL
IDX_PUBLISHED_AT = 17  # R: 발행일시
IDX_INDEXED = 18      # S: 색인여부
IDX_ERROR = 19        # T: 에러메시지
IDX_SERP_DATA = 20    # U: SERP데이터
IDX_VERIFIED = 22     # W: Haiku검증
IDX_INTERNAL_LINKS = 23  # X: 내부링크키워드
IDX_CPC = 5           # F: 예상CPC
IDX_DIFFICULTY = 6    # G: 난이도
IDX_PRIORITY = 7      # H: 우선순위
IDX_SCHEDULED = 8     # I: 예정일
IDX_CWV_LCP = 29      # AD: CWV_LCP
IDX_CWV_CLS = 30      # AE: CWV_CLS

# === 상태값 ===
STATUS_WAITING = "대기"
STATUS_PENDING = "발행대기"
STATUS_PUBLISHING = "발행중"
STATUS_PUBLISHED = "발행완료"
STATUS_FAILED = "발행실패"
STATUS_REVISION_PENDING = "수정대기"
STATUS_GENERATING = "생성중"

# === 성과 대시보드 주간 KPI 테이블 컬럼 (1-based, gspread Cell용) ===
# A~B: 기본 | C~D: Pipeline A | E~G: Pipeline B | H~M: SEO성과 | N~O: 수동
DASH_COL_WEEK = 1           # A: 주차
DASH_COL_PERIOD = 2         # B: 기간
DASH_COL_PIPELINE_A = 3     # C: PL-A 성공률
DASH_COL_VERIFY_RATE = 4    # D: 검증통과율
DASH_COL_NEW = 5            # E: 신규발행
DASH_COL_CUMULATIVE = 6     # F: 누적발행
DASH_COL_PIPELINE_B = 7     # G: PL-B 성공률
DASH_COL_INDEXED = 8        # H: 색인수
DASH_COL_IMPRESSIONS = 9    # I: 총노출
DASH_COL_CLICKS = 10        # J: 총클릭
DASH_COL_CTR = 11           # K: 평균CTR
DASH_COL_DAILY_VISITS = 12  # L: 일평균유입
DASH_COL_AVG_POS = 13       # M: 평균순위
DASH_COL_ADSENSE = 14       # N: 애드센스수익
DASH_COL_NOTE = 15          # O: 비고

# KPI 데이터 행 시작 (1-based)
DASH_KPI_START_ROW = 4

# === 사용 가이드 컬럼 참조 매핑 (구버전 → v2) ===
SHEET2_COLUMN_FIXES = {
    "O (content)": "P (본문마크다운)",
    "O(content)": "P(본문마크다운)",
    "H (faq)": "N (FAQ스키마)",
    "H(faq)": "N(FAQ스키마)",
    "E (meta_desc)": "L (메타설명)",
    "E(meta_desc)": "L(메타설명)",
    "G (tags)": "M (태그)",
    "G(tags)": "M(태그)",
}

# === 서식 색상 (RGB 0~1 float) ===
COLOR_DARK_BLUE = {"red": 0.16, "green": 0.22, "blue": 0.35}
COLOR_PL_A = {"red": 0.85, "green": 0.92, "blue": 0.83}       # 연한 녹색
COLOR_PL_B = {"red": 0.80, "green": 0.88, "blue": 0.96}       # 연한 파랑
COLOR_SEO = {"red": 0.98, "green": 0.92, "blue": 0.80}        # 연한 노랑
COLOR_MANUAL = {"red": 0.93, "green": 0.93, "blue": 0.93}     # 연한 회색
COLOR_HEADER = {"red": 0.22, "green": 0.33, "blue": 0.53}     # 진한 파랑
COLOR_WHITE = {"red": 1, "green": 1, "blue": 1}
COLOR_GOAL_ROW = {"red": 1.0, "green": 0.95, "blue": 0.80}    # 연한 오렌지
COLOR_SUMMARY = {"red": 0.90, "green": 0.90, "blue": 0.95}    # 연한 보라
COLOR_TOP = {"red": 0.96, "green": 0.80, "blue": 0.80}        # 피라미드 Top
COLOR_MID = {"red": 0.98, "green": 0.93, "blue": 0.80}        # 피라미드 Mid
COLOR_BOTTOM = {"red": 0.85, "green": 0.92, "blue": 0.83}     # 피라미드 Bottom
COLOR_LOG_HEADER = {"red": 0.20, "green": 0.30, "blue": 0.45}
COLOR_SUCCESS = {"red": 0.85, "green": 0.95, "blue": 0.85}    # 성공행
COLOR_FAIL = {"red": 0.98, "green": 0.85, "blue": 0.85}       # 실패행
COLOR_GUIDE_SECTION = {"red": 0.22, "green": 0.33, "blue": 0.53}
COLOR_GUIDE_TABLE = {"red": 0.90, "green": 0.93, "blue": 0.98}

FMT_BOLD_WHITE = {
    "textFormat": {"bold": True, "foregroundColor": COLOR_WHITE, "fontSize": 10},
}
FMT_BOLD = {"textFormat": {"bold": True, "fontSize": 10}}
FMT_CENTER = {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"}
FMT_BORDER_ALL = {
    "borders": {
        side: {"style": "SOLID", "color": {"red": 0.7, "green": 0.7, "blue": 0.7}}
        for side in ("top", "bottom", "left", "right")
    },
}
FMT_BORDER_THICK_BOTTOM = {
    "borders": {
        "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0.4, "green": 0.4, "blue": 0.4}},
    },
}


def apply_formats(ws: gspread.Worksheet, formats: list[tuple[str, dict]]) -> None:
    """(range, format) 쌍 목록을 적용. 동일 포맷은 ranges 리스트로 묶어 배치 처리."""
    import hashlib
    # 동일 포맷끼리 그룹핑 (JSON 직렬화로 키 생성)
    grouped: dict[str, tuple[list[str], dict]] = {}
    for rng, fmt in formats:
        key = hashlib.md5(json.dumps(fmt, sort_keys=True).encode()).hexdigest()
        if key not in grouped:
            grouped[key] = ([], fmt)
        grouped[key][0].append(rng)

    for ranges, fmt in grouped.values():
        ws.format(ranges, fmt)


def col_letter(col_num: int) -> str:
    """1-based 컬럼 번호를 A1 표기 문자로 변환 (1=A, 26=Z, 27=AA)."""
    result = ""
    while col_num > 0:
        col_num, remainder = divmod(col_num - 1, 26)
        result = chr(65 + remainder) + result
    return result


def connect(creds_path: str, sheet_name: str) -> gspread.Spreadsheet:
    """Google Sheets 스프레드시트 객체 반환."""
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open(sheet_name)


def safe_get(row: list, idx: int) -> str:
    """리스트 범위 초과 시 빈 문자열 반환."""
    return row[idx] if idx < len(row) else ""


def parse_datetime(s: str) -> datetime | None:
    """발행일시 문자열 파싱. 실패 시 None."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Google Search Console 성과 데이터
# ---------------------------------------------------------------------------

def fetch_gsc_daily(
    creds_path: str, site_url: str, start_date: str, end_date: str,
) -> list[dict]:
    """GSC Search Analytics API에서 일별 성과 데이터 조회.

    Returns:
        [{"date": "2026-03-01", "clicks": 20, "impressions": 324,
          "ctr": 0.06, "position": 9.3}, ...]
    """
    creds = Credentials.from_service_account_file(creds_path, scopes=GSC_SCOPES)
    service = gapi_build("searchconsole", "v1", credentials=creds)

    response = service.searchanalytics().query(
        siteUrl=site_url,
        body={
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["date"],
            "rowLimit": 500,
        },
    ).execute()

    rows = response.get("rows", [])
    return [
        {
            "date": r["keys"][0],
            "clicks": r["clicks"],
            "impressions": r["impressions"],
            "ctr": r["ctr"],
            "position": r["position"],
        }
        for r in rows
    ]


def aggregate_gsc_by_week(
    gsc_data: list[dict], week_start: datetime, max_weeks: int,
) -> dict[int, dict]:
    """GSC 일별 데이터를 주차별로 집계.

    Returns:
        {1: {"impressions": 2000, "clicks": 100, "ctr": 0.05, "daily_visits": 14.3}, ...}
    """
    weekly: dict[int, dict] = {}

    for entry in gsc_data:
        dt = datetime.strptime(entry["date"], "%Y-%m-%d")
        week_num = (dt - week_start).days // 7 + 1
        if week_num < 1 or week_num > max_weeks:
            continue

        if week_num not in weekly:
            weekly[week_num] = {
                "impressions": 0, "clicks": 0, "days": 0,
                "position_sum": 0.0, "position_count": 0,
            }
        wk = weekly[week_num]
        wk["impressions"] += entry["impressions"]
        wk["clicks"] += entry["clicks"]
        wk["days"] += 1
        wk["position_sum"] += entry["position"]
        wk["position_count"] += 1

    # CTR, 일평균유입, 평균순위 계산
    for wk in weekly.values():
        if wk["impressions"] > 0:
            wk["ctr"] = wk["clicks"] / wk["impressions"]
        else:
            wk["ctr"] = 0.0
        if wk["days"] > 0:
            wk["daily_visits"] = wk["clicks"] / wk["days"]
        else:
            wk["daily_visits"] = 0.0
        if wk["position_count"] > 0:
            wk["avg_position"] = wk["position_sum"] / wk["position_count"]
        else:
            wk["avg_position"] = 0.0

    return weekly


def is_verified_pass(verified_raw: str) -> bool | None:
    """Haiku검증 JSON에서 통과 여부 판단. 데이터 없으면 None."""
    if not verified_raw:
        return None
    try:
        outer = json.loads(verified_raw)
        if not isinstance(outer, dict):
            return None
        # content[0].text 안에 실제 검증 결과 JSON이 있음
        content = outer.get("content", [])
        for c in content:
            text = c.get("text", "")
            if not text:
                continue
            inner = json.loads(text)
            if isinstance(inner, dict):
                acc = inner.get("is_accurate", False)
                log = inner.get("is_logical", False)
                return bool(acc and log)
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return None


# ---------------------------------------------------------------------------
# 키워드 캘린더 데이터 분석
# ---------------------------------------------------------------------------

def compute_status_counts(data: list[list]) -> dict[str, int]:
    """상태별 건수 집계."""
    statuses = [safe_get(row, IDX_STATUS) for row in data]
    counts = Counter(statuses)
    return {
        "총 키워드": len(data),
        STATUS_WAITING: counts.get(STATUS_WAITING, 0),
        STATUS_GENERATING: counts.get(STATUS_GENERATING, 0),
        STATUS_PENDING: counts.get(STATUS_PENDING, 0),
        STATUS_PUBLISHING: counts.get(STATUS_PUBLISHING, 0),
        STATUS_PUBLISHED: counts.get(STATUS_PUBLISHED, 0),
        STATUS_FAILED: counts.get(STATUS_FAILED, 0),
        STATUS_REVISION_PENDING: counts.get(STATUS_REVISION_PENDING, 0),
    }


def compute_quality_metrics(data: list[list]) -> dict[str, str]:
    """콘텐츠 품질 지표 산출 (본문이 있는 행 대상)."""
    lengths = []
    h2_counts = []
    table_count = 0
    code_block_count = 0
    total_with_content = 0

    for row in data:
        body = safe_get(row, IDX_CONTENT)
        if not body or len(body.strip()) < 10:
            continue
        total_with_content += 1
        lengths.append(len(body))
        h2_counts.append(len(re.findall(r"^##\s", body, re.MULTILINE)))
        if re.search(r"\|.*\|.*\|", body):
            table_count += 1
        if "```" in body:
            code_block_count += 1

    if total_with_content == 0:
        return {
            "평균 본문 길이": "0",
            "평균 H2 수": "0",
            "테이블 포함률": "0%",
            "코드블록 포함률": "0%",
            "분석 대상": "0건",
        }

    avg_len = sum(lengths) / total_with_content
    avg_h2 = sum(h2_counts) / total_with_content
    table_rate = table_count / total_with_content * 100
    code_rate = code_block_count / total_with_content * 100

    return {
        "평균 본문 길이": f"{avg_len:,.0f}자",
        "평균 H2 수": f"{avg_h2:.1f}개",
        "테이블 포함률": f"{table_rate:.0f}%",
        "코드블록 포함률": f"{code_rate:.0f}%",
        "분석 대상": f"{total_with_content}건",
    }


def compute_cwv_metrics(data: list[list]) -> dict[str, str]:
    """CWV 지표 산출."""
    lcps = []
    cls_scores = []
    lcp_pass = 0

    for row in data:
        lcp_str = safe_get(row, IDX_CWV_LCP)
        cls_str = safe_get(row, IDX_CWV_CLS)
        if not lcp_str or not cls_str:
            continue
        try:
            lcp = float(lcp_str)
            cls_val = float(cls_str)
        except ValueError:
            continue
        lcps.append(lcp)
        cls_scores.append(cls_val)
        if lcp <= 2.5 and cls_val <= 0.1:
            lcp_pass += 1

    if not lcps:
        return {
            "CWV 측정 건수": "0건",
            "CWV 통과율": "-",
            "평균 LCP": "-",
            "평균 CLS": "-",
        }

    total = len(lcps)
    return {
        "CWV 측정 건수": f"{total}건",
        "CWV 통과율": f"{lcp_pass / total * 100:.0f}%",
        "평균 LCP": f"{sum(lcps) / total:.2f}s",
        "평균 CLS": f"{sum(cls_scores) / total:.3f}",
    }


def compute_category_distribution(data: list[list]) -> dict[str, int]:
    """카테고리별 건수."""
    categories = [safe_get(row, IDX_CATEGORY) for row in data if safe_get(row, IDX_CATEGORY)]
    return dict(Counter(categories).most_common())


def compute_weekly_kpi(
    data: list[list],
    gsc_weekly: dict[int, dict] | None = None,
) -> list[dict[str, object]]:
    """주차별 상세 KPI 집계 (GSC 성과 데이터 포함).

    각 주차별로 반환:
    - week, period, new, cumulative, indexed
    - impressions, clicks, ctr, daily_visits (GSC)
    - verified_rate, content_rate, pipeline_b_rate
    """
    # 각 행의 주차 관련 정보 수집
    row_info: list[dict] = []
    for row in data:
        pub_str = safe_get(row, IDX_PUBLISHED_AT)
        if not pub_str:
            continue
        dt = parse_datetime(pub_str)
        if not dt:
            continue
        status = safe_get(row, IDX_STATUS)
        # 색인 판정: S열에 값이 있거나, 발행완료/수정대기 (발행 된 글)
        s_val = safe_get(row, IDX_INDEXED).strip().upper()
        indexed = (
            s_val in ("TRUE", "O", "Y", "예")
            or status in (STATUS_PUBLISHED, STATUS_REVISION_PENDING)
        )
        verified = is_verified_pass(safe_get(row, IDX_VERIFIED))
        has_content = bool(safe_get(row, IDX_CONTENT).strip())
        row_info.append({
            "dt": dt,
            "status": status,
            "indexed": indexed,
            "verified": verified,
            "has_content": has_content,
        })

    if not row_info:
        return []

    # 가장 이른 발행일의 월요일 기준 주차 시작
    min_date = min(r["dt"] for r in row_info)
    week_start = min_date - timedelta(days=min_date.weekday())

    # 주차별 그룹핑
    weekly_groups: dict[int, list[dict]] = {}
    for r in row_info:
        week_num = (r["dt"] - week_start).days // 7 + 1
        weekly_groups.setdefault(week_num, []).append(r)

    max_week = max(weekly_groups.keys())
    result = []
    cumulative = 0
    if gsc_weekly is None:
        gsc_weekly = {}

    for w in range(1, min(max_week + 1, 13)):
        rows_in_week = weekly_groups.get(w, [])
        new_pub = len(rows_in_week)
        cumulative += new_pub

        # 기간 계산
        ws = week_start + timedelta(weeks=w - 1)
        we = ws + timedelta(days=6)
        period = f"{ws.strftime('%m/%d')}~{we.strftime('%m/%d')}"

        # 색인수
        indexed_count = sum(1 for r in rows_in_week if r["indexed"])

        # 검증통과율
        verified_rows = [r for r in rows_in_week if r["verified"] is not None]
        if verified_rows:
            verified_pass = sum(1 for r in verified_rows if r["verified"])
            verified_rate = f"{verified_pass / len(verified_rows) * 100:.0f}%"
        else:
            verified_rate = "-"

        # Pipeline A 성공률 (본문 있는 비율)
        if rows_in_week:
            content_count = sum(1 for r in rows_in_week if r["has_content"])
            content_rate = f"{content_count / len(rows_in_week) * 100:.0f}%"
        else:
            content_rate = "-"

        # Pipeline B 성공률 (발행완료 + 수정대기 = 성공)
        published = sum(
            1 for r in rows_in_week
            if r["status"] in (STATUS_PUBLISHED, STATUS_REVISION_PENDING)
        )
        failed = sum(
            1 for r in rows_in_week if r["status"] == STATUS_FAILED
        )
        total_attempted = published + failed
        if total_attempted > 0:
            pipeline_b_rate = f"{published / total_attempted * 100:.0f}%"
        else:
            pipeline_b_rate = "-"

        # GSC 성과 데이터
        gsc = gsc_weekly.get(w, {})
        impressions = gsc.get("impressions", 0)
        clicks = gsc.get("clicks", 0)
        ctr = gsc.get("ctr", 0.0)
        daily_visits = gsc.get("daily_visits", 0.0)
        avg_position = gsc.get("avg_position", 0.0)

        result.append({
            "week": f"W{w}",
            "period": period,
            "new": new_pub,
            "cumulative": cumulative,
            "indexed": indexed_count,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": f"{ctr * 100:.1f}%" if impressions else "-",
            "daily_visits": f"{daily_visits:.1f}" if clicks else "-",
            "verified_rate": verified_rate,
            "content_rate": content_rate,
            "pipeline_b_rate": pipeline_b_rate,
            "avg_position": f"{avg_position:.1f}" if avg_position else "-",
        })

    return result


def get_week_start_from_data(data: list[list]) -> datetime | None:
    """키워드 캘린더 데이터에서 가장 이른 발행일의 월요일을 반환."""
    for row in data:
        pub_str = safe_get(row, IDX_PUBLISHED_AT)
        if pub_str:
            dt = parse_datetime(pub_str)
            if dt:
                dates = [dt]
                break
    else:
        return None

    for row in data:
        pub_str = safe_get(row, IDX_PUBLISHED_AT)
        if pub_str:
            dt = parse_datetime(pub_str)
            if dt:
                dates.append(dt)

    min_date = min(dates)
    return min_date - timedelta(days=min_date.weekday())


# ---------------------------------------------------------------------------
# 성과 대시보드 업데이트
# ---------------------------------------------------------------------------

def find_cell_by_label(
    all_values: list[list], label: str, *, exact: bool = False,
) -> tuple[int, int] | None:
    """대시보드에서 라벨 텍스트가 있는 셀 위치 반환 (row, col), 0-based."""
    for r, row in enumerate(all_values):
        for c, cell in enumerate(row):
            cell_str = str(cell).strip()
            if exact:
                if cell_str == label:
                    return (r, c)
            else:
                if label in cell_str:
                    return (r, c)
    return None


def update_dashboard_tab(
    spreadsheet: gspread.Spreadsheet,
    status_counts: dict[str, int],
    quality_metrics: dict[str, str],
    cwv_metrics: dict[str, str],
    category_dist: dict[str, int],
    weekly_kpi: list[dict[str, object]],
    *,
    dry_run: bool = False,
) -> None:
    """성과 대시보드 탭 업데이트."""
    try:
        dashboard = spreadsheet.worksheet("성과 대시보드")
    except gspread.exceptions.WorksheetNotFound:
        print("'성과 대시보드' 탭을 찾을 수 없습니다.")
        return

    all_values = dashboard.get_all_values()
    cells_to_update: list[gspread.Cell] = []

    # --- 현재 상태 요약 ---
    # 수정대기도 발행은 된 것이므로 발행완료에 합산
    published_total = (
        status_counts[STATUS_PUBLISHED] + status_counts[STATUS_REVISION_PENDING]
    )
    status_label_map = [
        ("총 키워드", status_counts["총 키워드"]),
        ("발행대기", status_counts[STATUS_PENDING]),
        ("발행완료", published_total),
        ("발행실패", status_counts[STATUS_FAILED]),
        ("수정대기", status_counts[STATUS_REVISION_PENDING]),
        ("생성중", status_counts[STATUS_GENERATING]),
        ("대기", status_counts[STATUS_WAITING]),
    ]

    matched_positions: set[tuple[int, int]] = set()
    for label, value in status_label_map:
        pos = find_cell_by_label(all_values, label, exact=True)
        if not pos:
            pos = find_cell_by_label(all_values, label)
        if pos and pos not in matched_positions:
            matched_positions.add(pos)
            r, c = pos
            cells_to_update.append(gspread.Cell(row=r + 1, col=c + 2, value=str(value)))

    # --- 콘텐츠 품질 지표 ---
    for label, value in quality_metrics.items():
        pos = find_cell_by_label(all_values, label)
        if pos:
            r, c = pos
            cells_to_update.append(gspread.Cell(row=r + 1, col=c + 2, value=value))

    # --- CWV 지표 ---
    for label, value in cwv_metrics.items():
        pos = find_cell_by_label(all_values, label)
        if pos:
            r, c = pos
            cells_to_update.append(gspread.Cell(row=r + 1, col=c + 2, value=value))

    # --- 주간 KPI 헤더 (Row 3) ---
    # 그룹: 기본 | Pipeline A | Pipeline B | SEO성과 | 수동
    kpi_headers = [
        (DASH_COL_WEEK, "주차"), (DASH_COL_PERIOD, "기간"),
        (DASH_COL_PIPELINE_A, "PL-A성공률"), (DASH_COL_VERIFY_RATE, "검증통과율"),
        (DASH_COL_NEW, "신규발행"), (DASH_COL_CUMULATIVE, "누적발행"),
        (DASH_COL_PIPELINE_B, "PL-B성공률"),
        (DASH_COL_INDEXED, "색인수"), (DASH_COL_IMPRESSIONS, "총노출"),
        (DASH_COL_CLICKS, "총클릭"), (DASH_COL_CTR, "평균CTR"),
        (DASH_COL_DAILY_VISITS, "일평균유입"), (DASH_COL_AVG_POS, "평균순위"),
        (DASH_COL_ADSENSE, "애드센스수익"), (DASH_COL_NOTE, "비고"),
    ]
    for col, header in kpi_headers:
        cells_to_update.append(gspread.Cell(row=3, col=col, value=header))

    # --- 주간 KPI 데이터 (고정 컬럼 위치 사용) ---
    for i, wk in enumerate(weekly_kpi):
        row_num = DASH_KPI_START_ROW + i
        cells_to_update.extend([
            gspread.Cell(row=row_num, col=DASH_COL_PERIOD, value=str(wk["period"])),
            gspread.Cell(row=row_num, col=DASH_COL_NEW, value=str(wk["new"])),
            gspread.Cell(row=row_num, col=DASH_COL_CUMULATIVE, value=str(wk["cumulative"])),
            gspread.Cell(row=row_num, col=DASH_COL_INDEXED, value=str(wk["indexed"])),
            gspread.Cell(row=row_num, col=DASH_COL_IMPRESSIONS, value=str(wk["impressions"])),
            gspread.Cell(row=row_num, col=DASH_COL_CLICKS, value=str(wk["clicks"])),
            gspread.Cell(row=row_num, col=DASH_COL_CTR, value=str(wk["ctr"])),
            gspread.Cell(row=row_num, col=DASH_COL_DAILY_VISITS, value=str(wk["daily_visits"])),
            gspread.Cell(row=row_num, col=DASH_COL_VERIFY_RATE, value=str(wk["verified_rate"])),
            gspread.Cell(row=row_num, col=DASH_COL_PIPELINE_A, value=str(wk["content_rate"])),
            gspread.Cell(row=row_num, col=DASH_COL_PIPELINE_B, value=str(wk["pipeline_b_rate"])),
            gspread.Cell(row=row_num, col=DASH_COL_AVG_POS, value=str(wk["avg_position"])),
        ])

    # --- 목표행 (Row 15): 기획 기준값 ---
    goal_row = 15
    goal_labels = [
        (DASH_COL_WEEK, "목표"),
        (DASH_COL_PIPELINE_A, "90%+"),
        (DASH_COL_PIPELINE_B, "95%+"),
        (DASH_COL_INDEXED, "10+"),
        (DASH_COL_IMPRESSIONS, "500+"),
        (DASH_COL_DAILY_VISITS, "20+"),
        (DASH_COL_CTR, "2%+"),
        (DASH_COL_AVG_POS, "30위 이내"),
    ]
    for col, val in goal_labels:
        cells_to_update.append(gspread.Cell(row=goal_row, col=col, value=val))

    # --- 요약 섹션 (Row 17~21) ---
    if weekly_kpi:
        total_published = weekly_kpi[-1]["cumulative"] if weekly_kpi else 0
        total_indexed = sum(int(wk.get("indexed", 0)) for wk in weekly_kpi)
        index_rate = (
            f"{total_indexed / total_published * 100:.0f}%"
            if total_published else "-"
        )
        total_impr = sum(int(wk.get("impressions", 0)) for wk in weekly_kpi)
        total_clicks = sum(int(wk.get("clicks", 0)) for wk in weekly_kpi)
        avg_ctr = (
            f"{total_clicks / total_impr * 100:.1f}%"
            if total_impr else "-"
        )
        # 최신 일평균유입
        latest_daily = "-"
        for wk in reversed(weekly_kpi):
            dv = wk.get("daily_visits", "-")
            if dv != "-" and dv != "0.0":
                latest_daily = dv
                break
        # 반려율 (수정대기 / 총 발행시도)
        revision_count = status_counts.get(STATUS_REVISION_PENDING, 0)
        total_attempted = (
            status_counts.get(STATUS_PUBLISHED, 0)
            + status_counts.get(STATUS_FAILED, 0)
            + revision_count
        )
        rejection_rate = (
            f"{revision_count / total_attempted * 100:.0f}%"
            if total_attempted else "-"
        )

        summary_data = [
            (17, "총 발행수", str(total_published)),
            (18, "누적 색인률", index_rate),
            (19, "전체 평균CTR", avg_ctr),
            (20, "최근 일평균유입", str(latest_daily)),
            (21, "반려율", rejection_rate),
        ]
        for row_num, label, value in summary_data:
            cells_to_update.append(gspread.Cell(row=row_num, col=1, value=label))
            cells_to_update.append(gspread.Cell(row=row_num, col=2, value=value))

    # --- 카테고리 분포 ---
    pos = find_cell_by_label(all_values, "카테고리별")
    if pos:
        r, c = pos
        for i, (cat, cnt) in enumerate(category_dist.items()):
            cells_to_update.append(gspread.Cell(row=r + 2 + i, col=c + 1, value=cat))
            cells_to_update.append(gspread.Cell(row=r + 2 + i, col=c + 2, value=str(cnt)))

    # --- 마지막 업데이트 시간 ---
    pos = find_cell_by_label(all_values, "마지막 업데이트")
    if not pos:
        pos = find_cell_by_label(all_values, "최종 업데이트")
    if pos:
        r, c = pos
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        cells_to_update.append(gspread.Cell(row=r + 1, col=c + 2, value=now_str))

    if dry_run:
        print(f"\n[성과 대시보드] {len(cells_to_update)}개 셀 업데이트 예정:")
        for cell in cells_to_update:
            print(f"  Row {cell.row}, Col {cell.col} = {cell.value}")
        return

    if cells_to_update:
        dashboard.update_cells(cells_to_update)
        print(f"[성과 대시보드] {len(cells_to_update)}개 셀 업데이트 완료")
    else:
        print("[성과 대시보드] 업데이트할 셀 없음")

    # --- 서식 적용 ---
    format_dashboard(dashboard, len(weekly_kpi))


def format_dashboard(ws: gspread.Worksheet, kpi_weeks: int) -> None:
    """성과 대시보드 탭 서식 적용."""
    last_col = col_letter(DASH_COL_NOTE)  # O
    kpi_last_row = DASH_KPI_START_ROW + kpi_weeks - 1 if kpi_weeks else DASH_KPI_START_ROW

    # Row 2: 그룹 헤더 (머지 + 색상)
    groups = [
        ("A2:B2", "기본", COLOR_DARK_BLUE),
        (f"{col_letter(DASH_COL_PIPELINE_A)}2:{col_letter(DASH_COL_VERIFY_RATE)}2",
         "Pipeline A", COLOR_PL_A),
        (f"{col_letter(DASH_COL_NEW)}2:{col_letter(DASH_COL_PIPELINE_B)}2",
         "Pipeline B", COLOR_PL_B),
        (f"{col_letter(DASH_COL_INDEXED)}2:{col_letter(DASH_COL_AVG_POS)}2",
         "SEO 성과", COLOR_SEO),
        (f"{col_letter(DASH_COL_ADSENSE)}2:{col_letter(DASH_COL_NOTE)}2",
         "수동입력", COLOR_MANUAL),
    ]
    for rng, label, _color in groups:
        ws.merge_cells(rng)
    # 그룹 헤더 값 기록
    ws.update(values=[["기본"]], range_name="A2")
    ws.update(values=[["Pipeline A"]], range_name=f"{col_letter(DASH_COL_PIPELINE_A)}2")
    ws.update(values=[["Pipeline B"]], range_name=f"{col_letter(DASH_COL_NEW)}2")
    ws.update(values=[["SEO 성과"]], range_name=f"{col_letter(DASH_COL_INDEXED)}2")
    ws.update(values=[["수동입력"]], range_name=f"{col_letter(DASH_COL_ADSENSE)}2")

    formats: list[tuple[str, dict]] = []

    # Row 2 그룹 헤더 서식
    for rng, _label, color in groups:
        fmt: dict = {
            "backgroundColor": color,
            "textFormat": {"bold": True, "fontSize": 10},
            **FMT_CENTER,
            **FMT_BORDER_ALL,
        }
        # 진한 색 배경이면 흰색 글자
        if color in (COLOR_DARK_BLUE, COLOR_HEADER):
            fmt["textFormat"]["foregroundColor"] = COLOR_WHITE
        formats.append((rng, fmt))

    # Row 3 컬럼 헤더: 진한 파랑 + 흰색 볼드
    formats.append((f"A3:{last_col}3", {
        "backgroundColor": COLOR_HEADER,
        **FMT_BOLD_WHITE,
        **FMT_CENTER,
        **FMT_BORDER_ALL,
    }))

    # KPI 데이터 영역: 테두리 + 가운데 정렬
    if kpi_weeks:
        formats.append((
            f"A{DASH_KPI_START_ROW}:{last_col}{kpi_last_row}",
            {**FMT_CENTER, **FMT_BORDER_ALL},
        ))

    # Row 15 목표행: 오렌지 배경 + 볼드
    formats.append((f"A15:{last_col}15", {
        "backgroundColor": COLOR_GOAL_ROW,
        **FMT_BOLD,
        **FMT_CENTER,
        **FMT_BORDER_ALL,
    }))

    # Row 17~21 요약 섹션: 보라 배경
    formats.append(("A17:B21", {
        "backgroundColor": COLOR_SUMMARY,
        **FMT_BOLD,
        **FMT_BORDER_ALL,
    }))

    apply_formats(ws, formats)

    # 헤더 행 고정
    ws.freeze(rows=3)
    # 열 너비 자동 조정
    ws.columns_auto_resize(0, DASH_COL_NOTE)
    print("[성과 대시보드] 서식 적용 완료")


# ---------------------------------------------------------------------------
# 사용 가이드 컬럼 참조 수정
# ---------------------------------------------------------------------------

def update_sheet2_references(
    spreadsheet: gspread.Spreadsheet,
    *,
    dry_run: bool = False,
) -> None:
    """사용 가이드의 구버전 컬럼 참조를 v2에 맞게 수정."""
    try:
        sheet2 = spreadsheet.worksheet("사용 가이드")
    except gspread.exceptions.WorksheetNotFound:
        print("[사용 가이드] '사용 가이드' 탭을 찾을 수 없습니다.")
        return

    all_values = sheet2.get_all_values()
    cells_to_update: list[gspread.Cell] = []
    changes: list[str] = []

    for r, row in enumerate(all_values):
        for c, cell_value in enumerate(row):
            if not cell_value:
                continue
            new_value = cell_value
            for old_ref, new_ref in SHEET2_COLUMN_FIXES.items():
                if old_ref in new_value:
                    new_value = new_value.replace(old_ref, new_ref)
            if new_value != cell_value:
                cells_to_update.append(
                    gspread.Cell(row=r + 1, col=c + 1, value=new_value),
                )
                changes.append(
                    f"  ({r + 1}, {c + 1}): '{cell_value}' → '{new_value}'",
                )

    if not changes:
        print("[사용 가이드] 수정할 구버전 컬럼 참조 없음")
        return

    print(f"\n[사용 가이드] {len(changes)}개 셀 수정 {'예정' if dry_run else ''}:")
    for ch in changes:
        print(ch)

    if not dry_run:
        sheet2.update_cells(cells_to_update)
        print(f"[사용 가이드] {len(cells_to_update)}개 셀 수정 완료")


# ---------------------------------------------------------------------------
# 키워드 캘린더 메타 컬럼 자동 채우기 (CPC / 난이도 / 우선순위 / 예정일)
# ---------------------------------------------------------------------------

import time
import urllib.request
import urllib.parse

# 대형 도메인 (경쟁 강도 판별용)
AUTHORITY_DOMAINS = {
    "wikipedia.org", "namu.wiki", "tistory.com", "velog.io",
    "microsoft.com", "aws.amazon.com", "cloud.google.com",
    "docs.oracle.com", "developer.mozilla.org", "github.com",
    "stackoverflow.com", "medium.com", "samsung.com",
    "redhat.com", "ibm.com", "cisco.com", "vmware.com",
    "digitalocean.com", "atlassian.com", "hashicorp.com",
}


def fetch_serp(api_key: str, keyword: str) -> dict:
    """SerpAPI로 구글 검색 결과 조회."""
    params = urllib.parse.urlencode({
        "q": keyword,
        "location": "South Korea",
        "hl": "ko",
        "gl": "kr",
        "num": "10",
        "api_key": api_key,
        "engine": "google",
    })
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def analyze_serp_difficulty(serp_data: dict) -> tuple[int, dict]:
    """SERP 결과 분석 → 난이도 점수(0~100) + 상세 정보.

    점수 산출:
    - 대형 도메인 비율 × 40
    - 광고 수 × 10 (최대 30)
    - 총 검색결과 수 기반 × 30
    """
    organic = serp_data.get("organic_results", [])
    ads = serp_data.get("ads", [])
    total_results = serp_data.get("search_information", {}).get(
        "total_results", 0,
    )

    # 1. 대형 도메인 비율 (0~40점)
    authority_count = 0
    domains = []
    for r in organic[:10]:
        link = r.get("link", "")
        domain = ""
        if "//" in link:
            domain = link.split("//")[1].split("/")[0].replace("www.", "")
        domains.append(domain)
        for auth in AUTHORITY_DOMAINS:
            if auth in domain:
                authority_count += 1
                break

    auth_ratio = authority_count / max(len(organic[:10]), 1)
    auth_score = auth_ratio * 40

    # 2. 광고 수 (0~30점)
    ad_score = min(len(ads) * 10, 30)

    # 3. 총 검색결과 수 (0~30점)
    if total_results >= 10_000_000:
        result_score = 30
    elif total_results >= 1_000_000:
        result_score = 20
    elif total_results >= 100_000:
        result_score = 10
    else:
        result_score = 0

    total_score = int(auth_score + ad_score + result_score)

    detail = {
        "authority_count": authority_count,
        "authority_ratio": f"{auth_ratio:.0%}",
        "ads": len(ads),
        "total_results": total_results,
        "top_domains": domains[:5],
        "score": total_score,
    }
    return total_score, detail


def score_to_difficulty(score: int) -> str:
    """난이도 점수 → 상/중/하."""
    if score >= 55:
        return "상"
    if score >= 25:
        return "중"
    return "하"


def calc_priority(vol: int, cpc: int, difficulty: str) -> str:
    """검색볼륨 × CPC / 난이도 → 우선순위."""
    diff_weight = {"하": 1.5, "중": 1.0, "상": 0.6}
    w = diff_weight.get(difficulty, 1.0)
    score = (vol * 0.5 + cpc * 0.3) * w
    if score >= 2000:
        return "S"
    if score >= 800:
        return "A"
    return "B"


def estimate_cpc(vol: int) -> int:
    """검색볼륨 기반 예상CPC 추정 (기존 데이터 패턴)."""
    if vol >= 2000:
        return 2400
    if vol >= 1000:
        return 2000
    if vol >= 500:
        return 2700
    return 5000


def fill_keyword_meta(
    spreadsheet: gspread.Spreadsheet,
    *,
    dry_run: bool = False,
    use_serp: bool = True,
) -> None:
    """키워드 캘린더의 빈 CPC/난이도/우선순위/예정일을 자동 채우기.

    use_serp=True면 SerpAPI로 난이도를 SERP 경쟁 분석 기반으로 산출.
    """
    serpapi_key = os.getenv("SERPAPI_KEY", "")
    if use_serp and not serpapi_key:
        print("[키워드 메타] SERPAPI_KEY 미설정 — 검색볼륨 기반 추정으로 대체")
        use_serp = False

    sheet = spreadsheet.sheet1
    all_rows = sheet.get_all_values()
    data = all_rows[1:]

    cells_to_update: list[gspread.Cell] = []
    serp_cells: list[gspread.Cell] = []  # U열 SERP 데이터 저장용
    filled_count = 0
    serp_calls = 0

    for i, row in enumerate(data):
        row_num = i + 2

        vol_str = safe_get(row, IDX_SEARCH_VOL).strip()
        vol = 0
        if vol_str:
            nums = re.findall(r"\d+", vol_str.replace(",", ""))
            vol = int(nums[0]) if nums else 0

        cpc_str = safe_get(row, IDX_CPC).strip()
        diff_str = safe_get(row, IDX_DIFFICULTY).strip()
        prio_str = safe_get(row, IDX_PRIORITY).strip()
        sched_str = safe_get(row, IDX_SCHEDULED).strip()
        pub_at_str = safe_get(row, IDX_PUBLISHED_AT).strip()
        keyword = safe_get(row, IDX_KEYWORD).strip()
        serp_stored = safe_get(row, IDX_SERP_DATA).strip()

        # 이미 숫자형 난이도(1~5)나 기획 입력값이면 건너뜀
        if diff_str and diff_str not in ("상", "중", "하"):
            continue

        needs_diff = diff_str in ("상", "중", "하") or not diff_str
        needs_prio = prio_str in ("S", "A", "B") or not prio_str
        if not needs_diff and not needs_prio:
            continue
        if vol == 0 and not keyword:
            continue

        changed = False

        # CPC 채우기
        cpc = 0
        if cpc_str:
            cpc_nums = re.findall(r"\d+", cpc_str.replace(",", ""))
            cpc = int(cpc_nums[0]) if cpc_nums else 0
        elif vol > 0:
            cpc = estimate_cpc(vol)
            cells_to_update.append(
                gspread.Cell(row=row_num, col=IDX_CPC + 1, value=str(cpc)),
            )
            changed = True

        # SERP 기반 난이도 산출
        difficulty = diff_str or "중"
        if use_serp and keyword and (needs_diff or needs_prio):
            try:
                serp_data = fetch_serp(serpapi_key, keyword)
                score, detail = analyze_serp_difficulty(serp_data)
                difficulty = score_to_difficulty(score)
                serp_calls += 1

                # SERP 요약 저장 (U열)
                if not serp_stored:
                    serp_summary = json.dumps(detail, ensure_ascii=False)
                    serp_cells.append(
                        gspread.Cell(
                            row=row_num, col=IDX_SERP_DATA + 1,
                            value=serp_summary,
                        ),
                    )

                if not dry_run and serp_calls % 10 == 0:
                    print(f"  SERP 분석 {serp_calls}건 완료...")

                time.sleep(0.5)  # rate limit

            except Exception as e:
                if not dry_run:
                    print(f"  SERP 조회 실패 ({keyword}): {e}")
                # fallback: 검색볼륨 기반
                if vol >= 2000:
                    difficulty = "상"
                elif vol >= 500:
                    difficulty = "중"
                else:
                    difficulty = "하"

        # 난이도 기록
        if needs_diff:
            cells_to_update.append(
                gspread.Cell(
                    row=row_num, col=IDX_DIFFICULTY + 1, value=difficulty,
                ),
            )
            changed = True

        # 우선순위 기록
        if needs_prio:
            priority = calc_priority(vol, cpc, difficulty)
            cells_to_update.append(
                gspread.Cell(
                    row=row_num, col=IDX_PRIORITY + 1, value=priority,
                ),
            )
            changed = True

        # 예정일 채우기
        if not sched_str and pub_at_str:
            dt = parse_datetime(pub_at_str)
            if dt:
                cells_to_update.append(
                    gspread.Cell(
                        row=row_num, col=IDX_SCHEDULED + 1,
                        value=dt.strftime("%Y-%m-%d"),
                    ),
                )
                changed = True

        if changed:
            filled_count += 1

    if dry_run:
        print(f"\n[키워드 메타] {filled_count}행 갱신 예정 (SERP 호출 {serp_calls}건):")
        shown = 0
        for cell in cells_to_update:
            col_names = {
                IDX_CPC + 1: "CPC", IDX_DIFFICULTY + 1: "난이도",
                IDX_PRIORITY + 1: "우선순위", IDX_SCHEDULED + 1: "예정일",
            }
            name = col_names.get(cell.col, f"Col{cell.col}")
            if shown < 10:
                print(f"  Row {cell.row}: {name}={cell.value}")
                shown += 1
        if len(cells_to_update) > 10:
            print(f"  ... 외 {len(cells_to_update) - 10}셀")
        return

    if cells_to_update:
        sheet.update_cells(cells_to_update)
        print(f"[키워드 메타] {filled_count}행 갱신 완료 (SERP {serp_calls}건 분석)")
    if serp_cells:
        sheet.update_cells(serp_cells)
        print(f"[키워드 메타] SERP 분석 데이터 {len(serp_cells)}셀 저장 완료")
    if not cells_to_update and not serp_cells:
        print("[키워드 메타] 갱신할 항목 없음")


# ---------------------------------------------------------------------------
# 키워드 피라미드 탭
# ---------------------------------------------------------------------------

PYRAMID_HEADERS = ["계층", "허브 키워드", "연결 하위 키워드", "내부 링크 수", "허브 검색량", "비고"]
PYRAMID_HUB_THRESHOLD = 2000
PYRAMID_MID_THRESHOLD = 500


def classify_tier(search_vol: int) -> str:
    """검색볼륨 기반 계층 분류."""
    if search_vol >= PYRAMID_HUB_THRESHOLD:
        return "Top (허브)"
    if search_vol >= PYRAMID_MID_THRESHOLD:
        return "Mid (중간)"
    return "Bottom (하위)"


def extract_internal_links(raw: str) -> list[str]:
    """내부링크키워드 JSON에서 키워드 리스트 추출."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(k) for k in parsed if k]
        if isinstance(parsed, dict):
            return [str(v) for v in parsed.values() if v]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def build_pyramid_data(data: list[list]) -> list[list[str]]:
    """키워드 캘린더 데이터로 피라미드 테이블 구성."""
    # 카테고리별 키워드 그룹핑
    cat_keywords: dict[str, list[dict]] = {}
    for row in data:
        keyword = safe_get(row, IDX_KEYWORD).strip()
        if not keyword:
            continue
        category = safe_get(row, IDX_CATEGORY).strip() or "미분류"
        vol_str = safe_get(row, IDX_SEARCH_VOL).strip()
        try:
            vol = int(vol_str.replace(",", "")) if vol_str else 0
        except ValueError:
            vol = 0
        links_raw = safe_get(row, IDX_INTERNAL_LINKS)
        links = extract_internal_links(links_raw)

        cat_keywords.setdefault(category, []).append({
            "keyword": keyword,
            "vol": vol,
            "links": links,
            "tier": classify_tier(vol),
        })

    # 계층별 정렬 후 피라미드 행 생성
    rows: list[list[str]] = []
    for tier_label in ["Top (허브)", "Mid (중간)", "Bottom (하위)"]:
        for cat, kws in sorted(cat_keywords.items()):
            for kw in sorted(kws, key=lambda x: x["vol"], reverse=True):
                if kw["tier"] != tier_label:
                    continue
                # 연결 하위 키워드: 내부링크 + 동일 카테고리의 하위 계층
                linked = list(kw["links"])
                if tier_label in ("Top (허브)", "Mid (중간)"):
                    same_cat_lower = [
                        k["keyword"] for k in kws
                        if k["keyword"] != kw["keyword"] and k["vol"] < kw["vol"]
                    ]
                    for lk in same_cat_lower:
                        if lk not in linked:
                            linked.append(lk)
                linked_str = ", ".join(linked[:10])  # 최대 10개
                rows.append([
                    tier_label,
                    kw["keyword"],
                    linked_str,
                    str(len(linked)),
                    str(kw["vol"]),
                    cat,
                ])

    return rows


def update_keyword_pyramid(
    spreadsheet: gspread.Spreadsheet,
    data: list[list],
    *,
    dry_run: bool = False,
) -> None:
    """키워드 피라미드 탭 생성/업데이트."""
    pyramid_rows = build_pyramid_data(data)

    if dry_run:
        print(f"\n[키워드 피라미드] {len(pyramid_rows)}행 기록 예정:")
        for r in pyramid_rows[:5]:
            print(f"  {r[0]:<12} {r[1]:<30} 링크:{r[3]} 볼륨:{r[4]}")
        if len(pyramid_rows) > 5:
            print(f"  ... 외 {len(pyramid_rows) - 5}행")
        return

    # 탭 가져오기 or 생성
    try:
        ws = spreadsheet.worksheet("키워드 피라미드")
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title="키워드 피라미드",
            rows=max(len(pyramid_rows) + 10, 50),
            cols=len(PYRAMID_HEADERS),
        )
        print("[키워드 피라미드] 탭 생성 완료")

    # 헤더 + 데이터 한번에 기록
    all_rows = [PYRAMID_HEADERS] + pyramid_rows
    ws.clear()
    ws.update(range_name="A1", values=all_rows)
    print(f"[키워드 피라미드] {len(pyramid_rows)}행 기록 완료")

    # 서식 적용
    format_keyword_pyramid(ws, pyramid_rows)


def format_keyword_pyramid(
    ws: gspread.Worksheet, pyramid_rows: list[list[str]],
) -> None:
    """키워드 피라미드 탭 서식 적용."""
    last_row = len(pyramid_rows) + 1
    last_col = col_letter(len(PYRAMID_HEADERS))

    formats: list[tuple[str, dict]] = []

    # 헤더: 진한 파랑 + 흰색 볼드
    formats.append((f"A1:{last_col}1", {
        "backgroundColor": COLOR_HEADER,
        **FMT_BOLD_WHITE,
        **FMT_CENTER,
        **FMT_BORDER_ALL,
    }))

    # 계층별 행 색상
    tier_colors = {
        "Top (허브)": COLOR_TOP,
        "Mid (중간)": COLOR_MID,
        "Bottom (하위)": COLOR_BOTTOM,
    }
    for i, row in enumerate(pyramid_rows):
        tier = row[0]
        color = tier_colors.get(tier)
        if color:
            r = i + 2  # 1-based, 헤더 다음
            formats.append((f"A{r}:{last_col}{r}", {
                "backgroundColor": color,
                **FMT_BORDER_ALL,
            }))

    # 전체 가운데 정렬 (B열 키워드 제외 - 왼쪽 정렬)
    formats.append((f"A2:A{last_row}", FMT_CENTER))
    formats.append((f"D2:{last_col}{last_row}", FMT_CENTER))

    apply_formats(ws, formats)

    ws.freeze(rows=1)
    ws.columns_auto_resize(0, len(PYRAMID_HEADERS))
    print("[키워드 피라미드] 서식 적용 완료")


# ---------------------------------------------------------------------------
# 파이프라인 로그 탭
# ---------------------------------------------------------------------------

LOG_HEADERS = [
    "실행ID", "실행시각", "키워드No", "키워드", "SERP", "생성",
    "URL검증", "코드검증", "논리검증", "검증통과", "이미지",
    "발행", "최종상태", "에러메시지",
]


def build_pipeline_log(data: list[list]) -> list[list[str]]:
    """키워드 캘린더 데이터에서 파이프라인 로그 복원."""
    logs: list[list[str]] = []

    for row in data:
        status = safe_get(row, IDX_STATUS).strip()
        # 상태가 있는(처리된) 행만 로그 대상
        if not status or status == STATUS_WAITING:
            continue

        no = safe_get(row, IDX_NO).strip()
        keyword = safe_get(row, IDX_KEYWORD).strip()
        pub_at = safe_get(row, IDX_PUBLISHED_AT).strip()
        error = safe_get(row, IDX_ERROR).strip()
        has_serp = "O" if safe_get(row, IDX_SERP_DATA).strip() else "X"
        has_content = "O" if safe_get(row, IDX_CONTENT).strip() else "X"
        has_url = "O" if safe_get(row, IDX_PUBLISHED_URL).strip() else "X"

        # Haiku 검증 결과 파싱
        verified = is_verified_pass(safe_get(row, IDX_VERIFIED))
        verified_str = "O" if verified else ("X" if verified is False else "-")

        # 상태 기반 추론 (수정대기도 발행은 완료된 것)
        is_published = status in (STATUS_PUBLISHED, STATUS_REVISION_PENDING)
        is_failed = status == STATUS_FAILED

        # 실행ID: 발행일 기반 또는 키워드번호 기반
        exec_id = f"PB-{no}" if no else f"PB-{keyword[:8]}"
        exec_time = pub_at or "-"

        logs.append([
            exec_id,
            exec_time,
            no,
            keyword,
            has_serp,           # SERP
            has_content,        # 생성
            has_url,            # URL검증
            verified_str,       # 코드검증 (Haiku검증으로 대체)
            verified_str,       # 논리검증 (동일)
            verified_str,       # 검증통과
            "O" if is_published else "-",  # 이미지
            "O" if is_published else "X",  # 발행
            status,             # 최종상태
            error or "-",       # 에러메시지
        ])

    # 실행시각 내림차순 정렬
    logs.sort(key=lambda x: x[1], reverse=True)
    return logs


def update_pipeline_log(
    spreadsheet: gspread.Spreadsheet,
    data: list[list],
    *,
    dry_run: bool = False,
) -> None:
    """파이프라인 로그 탭 생성/업데이트."""
    log_rows = build_pipeline_log(data)

    if dry_run:
        print(f"\n[파이프라인 로그] {len(log_rows)}행 기록 예정:")
        for r in log_rows[:5]:
            print(f"  {r[0]:<10} {r[1]:<20} {r[3]:<30} → {r[12]}")
        if len(log_rows) > 5:
            print(f"  ... 외 {len(log_rows) - 5}행")
        return

    try:
        ws = spreadsheet.worksheet("파이프라인 로그")
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title="파이프라인 로그",
            rows=max(len(log_rows) + 10, 50),
            cols=len(LOG_HEADERS),
        )
        print("[파이프라인 로그] 탭 생성 완료")

    all_rows = [LOG_HEADERS] + log_rows
    ws.clear()
    ws.update(range_name="A1", values=all_rows)
    print(f"[파이프라인 로그] {len(log_rows)}행 기록 완료")

    # 서식 적용
    format_pipeline_log(ws, log_rows)


def format_pipeline_log(
    ws: gspread.Worksheet, log_rows: list[list[str]],
) -> None:
    """파이프라인 로그 탭 서식 적용."""
    last_row = len(log_rows) + 1
    last_col = col_letter(len(LOG_HEADERS))

    formats: list[tuple[str, dict]] = []

    # 헤더: 진한 파랑 + 흰색 볼드
    formats.append((f"A1:{last_col}1", {
        "backgroundColor": COLOR_LOG_HEADER,
        **FMT_BOLD_WHITE,
        **FMT_CENTER,
        **FMT_BORDER_ALL,
    }))

    # 상태별 행 색상 (최종상태 = 13번째 컬럼, 0-based idx 12)
    for i, row in enumerate(log_rows):
        r = i + 2
        status = row[12] if len(row) > 12 else ""
        if status in (STATUS_PUBLISHED, STATUS_REVISION_PENDING):
            formats.append((f"A{r}:{last_col}{r}", {
                "backgroundColor": COLOR_SUCCESS,
                **FMT_BORDER_ALL,
            }))
        elif status == STATUS_FAILED:
            formats.append((f"A{r}:{last_col}{r}", {
                "backgroundColor": COLOR_FAIL,
                **FMT_BORDER_ALL,
            }))
        else:
            formats.append((f"A{r}:{last_col}{r}", FMT_BORDER_ALL))

    # 전체 가운데 정렬 (D열 키워드명 제외)
    formats.append((f"A2:C{last_row}", FMT_CENTER))
    formats.append((f"E2:{last_col}{last_row}", FMT_CENTER))

    apply_formats(ws, formats)

    ws.freeze(rows=1)
    ws.columns_auto_resize(0, len(LOG_HEADERS))
    print("[파이프라인 로그] 서식 적용 완료")


# ---------------------------------------------------------------------------
# 사용 가이드 보강
# ---------------------------------------------------------------------------

GUIDE_TAB_INFO = [
    ["탭 이름", "용도", "작성 주체", "업데이트 주기", "비고"],
    ["키워드 캘린더", "키워드 기획 + 콘텐츠 생성/발행 상태 관리", "n8n (자동) + 운영자", "매일", "메인 데이터 소스"],
    ["성과 대시보드", "주간 KPI, 상태 요약, 품질 지표", "스크립트 (자동)", "주 1회+", "update_dashboard.py"],
    ["키워드 피라미드", "허브-스포크 내부 링크 설계 맵", "스크립트 (자동)", "주 1회", "SEO 전략 참조"],
    ["파이프라인 로그", "n8n/Pipeline B 실행 이력 추적", "스크립트 (자동)", "매 실행 후", "장애 추적용"],
    ["사용 가이드", "탭 사용법, QA 기준, 주의사항", "운영자", "필요 시", "이 탭"],
]

GUIDE_N8N_NOTES = [
    "",
    "=== n8n 연동 주의사항 ===",
    "1. 키워드 캘린더 시트의 열 순서를 변경하지 마세요 — n8n 노드가 컬럼 인덱스를 참조합니다.",
    "2. 상태(J열) 값은 정해진 값만 사용하세요: 대기, 생성중, 발행대기, 발행중, 발행완료, 발행실패, 수정대기.",
    "3. 시트 이름(탭명)을 변경하면 n8n 워크플로우와 Python 스크립트 모두 수정이 필요합니다.",
    "4. 서비스 계정 권한: Google Sheets API + Search Console API가 모두 활성화되어야 합니다.",
    "5. n8n 크론 스케줄(01:00)과 Pipeline B(09:00)는 최소 6시간 간격을 유지하세요.",
]


def update_usage_guide(
    spreadsheet: gspread.Spreadsheet,
    *,
    dry_run: bool = False,
) -> None:
    """사용 가이드 탭에 탭 설명 + n8n 주의사항 추가."""
    try:
        ws = spreadsheet.worksheet("사용 가이드")
    except gspread.exceptions.WorksheetNotFound:
        print("[사용 가이드] 탭을 찾을 수 없습니다.")
        return

    existing = ws.get_all_values()

    # 이미 탭 설명이 있는지 확인
    has_tab_info = any("탭 이름" in str(cell) for row in existing for cell in row)
    has_n8n_notes = any("n8n 연동 주의사항" in str(cell) for row in existing for cell in row)

    if has_tab_info and has_n8n_notes:
        print("[사용 가이드] 탭 설명 + n8n 주의사항 이미 존재 — 건너뜀")
        return

    # 기존 내용 위에 삽입할 데이터 구성
    insert_rows: list[list[str]] = []
    if not has_tab_info:
        insert_rows.append(["=== 탭별 용도 안내 ===", "", "", "", ""])
        insert_rows.extend(GUIDE_TAB_INFO)
        insert_rows.append(["", "", "", "", ""])  # 빈 행

    if not has_n8n_notes:
        for note in GUIDE_N8N_NOTES:
            insert_rows.append([note, "", "", "", ""])
        insert_rows.append(["", "", "", "", ""])  # 빈 행

    if dry_run:
        print(f"\n[사용 가이드] {len(insert_rows)}행 삽입 예정 (기존 내용 위에):")
        for r in insert_rows:
            if r[0]:
                print(f"  {r[0]}")
        return

    # 기존 내용 위에 삽입: 기존 데이터를 아래로 밀기
    new_all = insert_rows + existing
    ws.clear()
    if new_all:
        ws.update(range_name="A1", values=new_all)
    print(f"[사용 가이드] {len(insert_rows)}행 추가 완료")

    # 서식 적용
    format_usage_guide(ws, insert_rows)


def format_usage_guide(ws: gspread.Worksheet, insert_rows: list[list[str]]) -> None:
    """사용 가이드 탭 서식 적용."""
    formats: list[tuple[str, dict]] = []

    for i, row in enumerate(insert_rows):
        r = i + 1  # 1-based
        text = row[0] if row else ""
        if text.startswith("==="):
            # 섹션 헤더: 진한 파랑 + 흰색 볼드
            formats.append((f"A{r}:E{r}", {
                "backgroundColor": COLOR_GUIDE_SECTION,
                **FMT_BOLD_WHITE,
            }))
        elif text == "탭 이름":
            # 테이블 헤더: 볼드 + 배경
            formats.append((f"A{r}:E{r}", {
                "backgroundColor": COLOR_GUIDE_TABLE,
                **FMT_BOLD,
                **FMT_CENTER,
                **FMT_BORDER_ALL,
            }))
        elif text in (t[0] for t in GUIDE_TAB_INFO[1:]):
            # 테이블 데이터 행
            formats.append((f"A{r}:E{r}", {
                "backgroundColor": COLOR_GUIDE_TABLE,
                **FMT_BORDER_ALL,
            }))
        elif text.startswith(("1.", "2.", "3.", "4.", "5.")):
            # 주의사항 번호 항목
            formats.append((f"A{r}:E{r}", {
                "backgroundColor": {"red": 1.0, "green": 0.97, "blue": 0.90},
                **FMT_BORDER_ALL,
            }))

    if formats:
        apply_formats(ws, formats)
    ws.columns_auto_resize(0, 5)
    print("[사용 가이드] 서식 적용 완료")


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def print_summary(
    status_counts: dict[str, int],
    quality_metrics: dict[str, str],
    cwv_metrics: dict[str, str],
    category_dist: dict[str, int],
    weekly_kpi: list[dict[str, object]],
) -> None:
    """계산 결과 콘솔 출력."""
    print("\n" + "=" * 80)
    print("  성과 대시보드 업데이트 요약")
    print("=" * 80)

    print("\n[현재 상태 요약]")
    for label, value in status_counts.items():
        print(f"  {label:<12}: {value}")

    print("\n[콘텐츠 품질 지표]")
    for label, value in quality_metrics.items():
        print(f"  {label:<14}: {value}")

    print("\n[CWV 지표]")
    for label, value in cwv_metrics.items():
        print(f"  {label:<14}: {value}")

    print("\n[카테고리 분포]")
    for cat, cnt in category_dist.items():
        print(f"  {cat:<20}: {cnt}")

    if weekly_kpi:
        print("\n[주간 KPI]")
        header = (
            f"  {'주차':<5} {'기간':<14} "
            f"{'PL-A':>5} {'검증률':>6} "
            f"{'신규':>4} {'누적':>4} {'PL-B':>5} "
            f"{'색인':>4} {'노출':>7} {'클릭':>5} {'CTR':>6} "
            f"{'일유입':>6} {'순위':>5}"
        )
        print(header)
        print("  " + "-" * (len(header) - 2))
        for wk in weekly_kpi:
            print(
                f"  {wk['week']:<5} {wk['period']:<14} "
                f"{wk['content_rate']:>5} {wk['verified_rate']:>6} "
                f"{wk['new']:>4} {wk['cumulative']:>4} "
                f"{wk['pipeline_b_rate']:>5} "
                f"{wk['indexed']:>4} {wk['impressions']:>7} "
                f"{wk['clicks']:>5} {wk['ctr']:>6} "
                f"{wk['daily_visits']:>6} {wk['avg_position']:>5}"
            )

    print("\n" + "=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="성과 대시보드 자동 업데이트 (키워드 캘린더 → 성과 대시보드)",
    )
    parser.add_argument("--dry-run", action="store_true", help="미리보기만 (시트 변경 없음)")
    parser.add_argument(
        "--skip-sheet2", action="store_true", help="사용 가이드 컬럼 참조 수정 생략",
    )
    parser.add_argument(
        "--creds", default=os.getenv("GOOGLE_CREDS", "credentials.json"),
        help="Google 서비스 계정 JSON 경로",
    )
    parser.add_argument(
        "--sheet", default=os.getenv("SHEET_NAME", "keyword_calendar_v2"),
        help="스프레드시트 이름",
    )
    args = parser.parse_args()

    if not os.path.exists(args.creds):
        print(f"인증 파일 없음: {args.creds}")
        sys.exit(1)

    print(f"스프레드시트: {args.sheet}")
    print(f"모드: {'DRY-RUN (변경 없음)' if args.dry_run else '실행'}")

    # 연결
    spreadsheet = connect(args.creds, args.sheet)
    sheet1 = spreadsheet.sheet1

    # 키워드 캘린더 데이터 읽기 (헤더 제외)
    print("\n키워드 캘린더 데이터 읽는 중...")
    all_rows = sheet1.get_all_values()
    data = all_rows[1:]  # 헤더 제외
    print(f"  → {len(data)}행 로드 완료")

    # GSC 성과 데이터 조회
    blog_name = os.getenv("TISTORY_BLOG", "")
    site_url = f"https://{blog_name}.tistory.com/" if blog_name else ""
    gsc_weekly: dict[int, dict] = {}

    if site_url:
        week_start = get_week_start_from_data(data)
        if week_start:
            start_date = week_start.strftime("%Y-%m-%d")
            end_date = datetime.now().strftime("%Y-%m-%d")
            print(f"\nGSC 성과 데이터 조회: {start_date} ~ {end_date}")
            try:
                gsc_daily = fetch_gsc_daily(args.creds, site_url, start_date, end_date)
                gsc_weekly = aggregate_gsc_by_week(gsc_daily, week_start, 12)
                print(f"  → {len(gsc_daily)}일치 데이터, {len(gsc_weekly)}주차 집계 완료")
            except Exception as e:
                print(f"  → GSC 조회 실패 (계속 진행): {e}")
    else:
        print("\nTISTORY_BLOG 미설정 — GSC 데이터 건너뜀")

    # 지표 계산
    status_counts = compute_status_counts(data)
    quality_metrics = compute_quality_metrics(data)
    cwv_metrics = compute_cwv_metrics(data)
    category_dist = compute_category_distribution(data)
    weekly_kpi = compute_weekly_kpi(data, gsc_weekly=gsc_weekly)

    # 결과 출력
    print_summary(status_counts, quality_metrics, cwv_metrics, category_dist, weekly_kpi)

    # 0. 키워드 캘린더 메타 자동 채우기
    print("\n[0/4] 키워드 캘린더 메타 채우기 (CPC/난이도/우선순위/예정일)...")
    fill_keyword_meta(spreadsheet, dry_run=args.dry_run)

    # 1. 성과 대시보드 업데이트
    print("\n[1/4] 성과 대시보드 업데이트 중...")
    update_dashboard_tab(
        spreadsheet, status_counts, quality_metrics, cwv_metrics,
        category_dist, weekly_kpi, dry_run=args.dry_run,
    )

    # 2. 키워드 피라미드
    print("\n[2/4] 키워드 피라미드 업데이트 중...")
    update_keyword_pyramid(spreadsheet, data, dry_run=args.dry_run)

    # 3. 파이프라인 로그
    print("\n[3/4] 파이프라인 로그 업데이트 중...")
    update_pipeline_log(spreadsheet, data, dry_run=args.dry_run)

    # 4. 사용 가이드
    if not args.skip_sheet2:
        print("\n[4/4] 사용 가이드 업데이트 중...")
        update_sheet2_references(spreadsheet, dry_run=args.dry_run)
        update_usage_guide(spreadsheet, dry_run=args.dry_run)
    else:
        print("\n[4/4] 사용 가이드 — 건너뜀 (--skip-sheet2)")

    print("\n완료!")


if __name__ == "__main__":
    main()
