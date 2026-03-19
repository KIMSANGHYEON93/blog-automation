"""
Google Sheets 컬럼 매핑 (A~AH열)
시트 구조 v2 — 기획 메타 + 생성 데이터 + 운영 데이터 통합
"""
COL = {
    # === 기획 메타데이터 (A-I) ===
    "no": 1,              # A: No.
    "keyword": 2,         # B: 키워드
    "category": 3,        # C: 카테고리
    "content_type": 4,    # D: 콘텐츠유형
    "search_vol": 5,      # E: 검색볼륨
    "cpc": 6,             # F: 예상CPC
    "difficulty": 7,      # G: 난이도
    "priority": 8,        # H: 우선순위
    "scheduled_date": 9,  # I: 예정일
    # === 상태 (J) ===
    "status": 10,         # J: 상태
    # === 생성 데이터 (K-P) ===
    "title": 11,          # K: 제목
    "meta_desc": 12,      # L: 메타설명
    "tags": 13,           # M: 태그
    "faq": 14,            # N: FAQ스키마
    "references": 15,     # O: 참고자료
    "content": 16,        # P: 본문마크다운
    # === 발행/운영 데이터 (Q-Y) ===
    "published_url": 17,  # Q: 발행URL
    "published_at": 18,   # R: 발행일시
    "indexed": 19,        # S: 색인여부
    "error_msg": 20,      # T: 에러메시지
    "serp_data": 21,      # U: SERP데이터
    "prompt_type": 22,    # V: 프롬프트유형
    "verified": 23,       # W: Haiku검증
    "internal_links": 24, # X: 내부링크키워드
    "note": 25,           # Y: 비고
    # === 확장 운영 컬럼 (Z-AH) ===
    "created_at": 26,     # Z: 생성일시
    "thumbnail_url": 27,  # AA: 썸네일URL
    "entry_id": 28,       # AB: 엔트리ID
    "revision_count": 29, # AC: 수정횟수
    "cwv_lcp": 30,        # AD: CWV_LCP
    "cwv_cls": 31,        # AE: CWV_CLS
    "cwv_checked_at": 32, # AF: CWV점검일시
    "revised_at": 33,     # AG: 최종수정일시
    "revision_reason": 34,  # AH: 수정사유
}

STATUS_WAITING = "대기"
STATUS_PENDING = "발행대기"
STATUS_PUBLISHING = "발행중"
STATUS_PUBLISHED = "발행완료"
STATUS_FAILED = "발행실패"
STATUS_REVISION_PENDING = "수정대기"
STATUS_REVISING = "수정중"
