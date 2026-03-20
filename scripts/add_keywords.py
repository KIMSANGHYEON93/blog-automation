"""Google Sheets에 키워드 일괄 추가 스크립트 (시트 구조 v2 대응).

사용법:
    python scripts/add_keywords.py              # 추가 실행
    python scripts/add_keywords.py --dry-run    # 미리보기만
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# column_map.py 기준 v2 컬럼 위치
COL_NO = 1           # A: No.
COL_KEYWORD = 2      # B: 키워드
COL_CATEGORY = 3     # C: 카테고리
COL_CONTENT_TYPE = 4  # D: 콘텐츠유형
COL_STATUS = 10      # J: 상태

# site_profile.json 기반 카테고리 자동 분류
CATEGORY_RULES: list[tuple[str, str]] = [
    (r"vs |비교|차이", "비교"),
    (r"에러|오류|해결|안될때|트러블슈팅|장애|진단|모음집", "트러블슈팅"),
    (r"방법$|설정|설치|가이드|구축|준비|체크리스트|활용|실전|총정리|모음", "가이드"),
    (r"란$|이란$|뜻$|의미$|무엇", "용어"),
    (r"트렌드|전망", "트렌드"),
]

# 콘텐츠유형 자동 분류
CONTENT_TYPE_RULES: list[tuple[str, str]] = [
    (r"vs |비교|차이", "비교분석"),
    (r"에러|오류|해결|안될때|트러블슈팅|장애|진단", "트러블슈팅"),
    (r"가이드|구축|설정|설치|방법|준비|실전", "실전가이드"),
    (r"란$|이란$|뜻$|의미$|무엇", "용어해설"),
    (r"총정리|모음|체크리스트", "리스트"),
]


def classify(keyword: str, rules: list[tuple[str, str]], default: str) -> str:
    for pattern, value in rules:
        if re.search(pattern, keyword):
            return value
    return default


KEYWORDS = [
    "AWS 비용 최적화 방법",
    "AWS vs Azure 비용 비교 2026",
    "클라우드 마이그레이션 체크리스트",
    "AWS Lambda vs Azure Functions 비교",
    "S3 vs Azure Blob vs GCS 스토리지 비교",
    "Terraform 실전 프로젝트 구축",
    "Docker Compose 멀티컨테이너 실전",
    "GitHub Actions CI/CD 실전 구축",
    "GitOps ArgoCD 실전 배포 가이드",
    "Prometheus Grafana 모니터링 실전 구축",
    "ELK Stack 로그 분석 시스템 구축",
    "서버 장애 대응 프레임워크",
    "쿠버네티스 트러블슈팅 종합 가이드",
    "GitHub Copilot vs Cursor 비교",
    "Claude Code 설치부터 실전 활용까지",
    "AI 코딩 도구 비교 총정리 2026",
    "n8n 자동화 워크플로우 실전 구축",
    "ChatGPT vs Claude vs Gemini 비교",
    "MCP 서버 구축 가이드",
    "Redis vs Memcached 비교",
    "이벤트 드리븐 아키텍처 설계 가이드",
    "Apache Airflow 데이터 파이프라인 구축",
    "AWS SAA 자격증 준비 가이드 2026",
    "정보처리기사 실기 준비 가이드",
    "Azure AZ-900 자격증 준비 가이드",
    "쿠버네티스 CKA 자격증 준비 가이드",
    "기업용 VPN 비교 2026",
    "기업 보안 솔루션 스택 가이드",
    "Docker 에러 모음집 총정리",
    "Linux 서버 성능 진단 명령어 가이드",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Sheets 키워드 일괄 추가 (v2)")
    parser.add_argument("--dry-run", action="store_true", help="미리보기만 (시트 변경 없음)")
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

    creds = Credentials.from_service_account_file(args.creds, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open(args.sheet).sheet1

    # 기존 키워드 중복 체크 (B열 = 키워드)
    existing_keywords = set(sheet.col_values(COL_KEYWORD))

    # 마지막 No. 찾기
    no_values = sheet.col_values(COL_NO)
    last_no = 0
    for v in reversed(no_values):
        if v.isdigit():
            last_no = int(v)
            break

    rows_to_add = []
    skipped = []
    for kw in KEYWORDS:
        if kw in existing_keywords:
            skipped.append(kw)
            continue

        last_no += 1
        category = classify(kw, CATEGORY_RULES, "가이드")
        content_type = classify(kw, CONTENT_TYPE_RULES, "실전가이드")

        # v2 시트: A=No, B=키워드, C=카테고리, D=콘텐츠유형, E~I=빈칸, J=상태(대기)
        row = [""] * COL_STATUS
        row[COL_NO - 1] = str(last_no)
        row[COL_KEYWORD - 1] = kw
        row[COL_CATEGORY - 1] = category
        row[COL_CONTENT_TYPE - 1] = content_type
        row[COL_STATUS - 1] = "대기"
        rows_to_add.append(row)

    if skipped:
        print(f"중복 스킵 ({len(skipped)}건):")
        for s in skipped:
            print(f"  - {s}")

    if not rows_to_add:
        print("추가할 키워드가 없습니다.")
        return

    print(f"\n추가 예정 ({len(rows_to_add)}건):")
    print(f"{'No.':<5} {'키워드':<45} {'카테고리':<12} {'콘텐츠유형':<12}")
    print("-" * 74)
    for row in rows_to_add:
        print(
            f"{row[0]:<5} {row[1]:<45} {row[2]:<12} {row[3]:<12}"
        )

    if args.dry_run:
        print(f"\n--dry-run 모드. 시트 변경 없음.")
        return

    print(f"\n{len(rows_to_add)}건 추가 중...")
    sheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
    print(f"완료! {len(rows_to_add)}건 추가됨.")


if __name__ == "__main__":
    main()
