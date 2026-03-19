"""Google Sheets에 키워드 일괄 추가 스크립트."""
import json
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

# site_profile.json 기반 카테고리 자동 분류
CATEGORY_RULES = [
    # (패턴, 카테고리)
    (r"vs |비교|차이", "비교"),
    (r"에러|오류|해결|안될때|트러블슈팅|장애|진단", "트러블슈팅"),
    (r"방법$|설정|설치|가이드|구축|준비|체크리스트|활용|실전|총정리|모음", "가이드"),
    (r"란$|이란$|뜻$|의미$", "용어"),
    (r"트렌드|전망", "트렌드"),
]


def classify_category(keyword: str) -> str:
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, keyword):
            return category
    return "가이드"  # 기본값


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


def main():
    creds_path = os.getenv("GOOGLE_CREDS", "credentials.json")
    sheet_name = os.getenv("SHEET_NAME", "keyword_calendar_v2")

    if not os.path.exists(creds_path):
        print(f"❌ 인증 파일 없음: {creds_path}")
        sys.exit(1)

    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).sheet1

    # 기존 키워드 중복 체크
    existing = sheet.col_values(1)  # A열 전체
    existing_set = set(existing)

    rows_to_add = []
    skipped = []
    for kw in KEYWORDS:
        if kw in existing_set:
            skipped.append(kw)
            continue
        category = classify_category(kw)
        # A: keyword, B: category, C: status(대기)
        rows_to_add.append([kw, category, "대기"])

    if skipped:
        print(f"⏭️  중복 스킵 ({len(skipped)}건):")
        for s in skipped:
            print(f"   - {s}")

    if not rows_to_add:
        print("추가할 키워드가 없습니다.")
        return

    # 미리보기
    print(f"\n📋 추가 예정 ({len(rows_to_add)}건):")
    print(f"{'키워드':<45} {'카테고리':<10}")
    print("-" * 55)
    for row in rows_to_add:
        print(f"{row[0]:<45} {row[1]:<10}")

    print(f"\n✅ {len(rows_to_add)}건 추가 중...")
    sheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
    print(f"✅ 완료! {len(rows_to_add)}건 추가됨.")


if __name__ == "__main__":
    main()
