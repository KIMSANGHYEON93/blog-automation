"""
Google Sheets 컬럼 매핑 (A~T열 = 1~20)
masterplan_v2.2 스키마 섹션 7 기준
"""
COL = {
    "keyword": 1,        # A: 키워드
    "category": 2,       # B: 콘텐츠 유형
    "status": 3,         # C: 상태
    "title": 4,          # D: 제목
    "meta_desc": 5,      # E: 메타 설명
    "url_slug": 6,       # F: URL 슬러그
    "tags": 7,           # G: 태그
    "faq": 8,            # H: FAQ 스키마 JSON
    "references": 9,     # I: 참고 자료
    "created_at": 10,    # J: 생성 일시
    "published_at": 11,  # K: 발행 일시
    "published_url": 12, # L: 발행 URL
    "error_msg": 13,     # M: 에러 메시지
    "search_vol": 14,    # N: 검색량 (SerpAPI)
    "content": 15,       # O: 본문 마크다운 (핵심)
    "serp_data": 16,     # P: SERP 스니펫 JSON
    "prompt_type": 17,   # Q: 프롬프트 유형 (A/B/C)
    "verified": 18,      # R: Haiku 검증 결과
    "internal_links": 19,  # S: 내부 링크 키워드
    "thumbnail_url": 20,   # T: 썸네일 URL (OG 이미지)
}

STATUS_WAITING = "대기"
STATUS_PENDING = "발행대기"
STATUS_PUBLISHING = "발행중"
STATUS_PUBLISHED = "발행완료"
STATUS_FAILED = "발행실패"
