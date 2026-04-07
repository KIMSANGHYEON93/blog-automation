# Pipeline D: 네이버 카페 API 자동 발행

> **STATUS: ROI 평가 중**
>
> Pipeline C(네이버 블로그)가 API 폐지로 NO-GO 판정 후, 대안 채널로 검토.
> 네이버 카페 글쓰기 API는 공식 지원 (200회/일)으로 Selenium 불필요.

---

## 1. 배경

### 1.1 Pipeline C NO-GO 사유

- 네이버 블로그 글쓰기 API(`writePost.json`)가 2020-05-06 공식 폐지
- Selenium 단독 운영 시 ROI 미성립 + 계정 제재 리스크 CRITICAL
- 상세: `docs/pipeline_c_naver_blog.md` Section 13~14 참조

### 1.2 네이버 카페 API 장점

| 비교 | 블로그 (Selenium, NO-GO) | 카페 (API) |
|------|--------------------------|-----------|
| 발행 방식 | 비공식 Selenium | **공식 Open API** |
| 일일 한도 | ~10건 (자체 제한) | **200회/일 (공식)** |
| 봇 탐지 리스크 | CRITICAL | **LOW** (약관 내 사용) |
| 네이버 검색 노출 | 블로그탭 + 통합검색 | 카페탭 + 통합검색 |
| 유지보수 | DOM 변경마다 수정 | API 스펙 변경 시만 |
| 계정 제재 | 높음 | 낮음 |

---

## 2. API 스펙

### 2.1 카페 글쓰기

```
POST https://openapi.naver.com/v1/cafe/{clubid}/menu/{menuid}/articles

Headers:
  Authorization: Bearer {access_token}
  Content-Type: multipart/form-data

Form Data:
  subject: 글 제목
  content: 본문 (HTML)

Response:
  { "message": { "result": { "articleId": 12345, "articleUrl": "..." } } }

Rate Limit: 200회/일
```

### 2.2 카페 가입

```
POST https://openapi.naver.com/v1/cafe/{clubid}/members

Headers:
  Authorization: Bearer {access_token}

Rate Limit: 50회/일
```

### 2.3 인증 (OAuth 2.0)

네이버 로그인 API 기반. Pipeline C 기획서 Section 3.2와 동일한 흐름.

```
[1] 최초 인증 (수동, 1회)
    브라우저 → 네이버 로그인 + 카페 권한 동의
    → code → access_token + refresh_token 교환

[2] 자동 갱신
    access_token 만료 (1시간) → refresh_token으로 갱신
    refresh_token 만료 (1년) → 재인증
```

---

## 3. 운영 모델

### 3.1 자체 카페 운영

IT 기술 블로그 성격의 네이버 카페를 직접 개설하여 콘텐츠를 발행한다.

| 항목 | 설정 |
|------|------|
| 카페 이름 | IT인프라 기술노트 (가칭) |
| 카테고리 | IT/컴퓨터 |
| 게시판 구조 | 키워드 카테고리별 (클라우드, 보안, DevOps, 서버) |
| 가입 조건 | 자유 가입 (트래픽 유입 극대화) |
| 발행 건수 | 5~10건/일 (보수적 시작) |

### 3.2 콘텐츠 소스

Pipeline A(n8n) → Pipeline B(Tistory 발행완료) → Pipeline D(카페 발행)

```
Google Sheets (발행완료)
    ↓ 동일 콘텐츠 읽기
Pipeline D (카페 변환 + API 발행)
    ↓ 발행 완료 시
Google Sheets (카페상태/카페URL 업데이트)
```

### 3.3 콘텐츠 변환 (최소)

네이버 카페는 HTML을 직접 지원하므로 변환이 간단하다.

| 항목 | 변환 |
|------|------|
| FAQ Schema | 제거 (카페 미지원) |
| AdSense 스크립트 | 제거 |
| 내부 링크 (Tistory) | Tistory URL 유지 (트래픽 허브 역할) |
| Mermaid/이미지 | 유지 (kroki.io URL 그대로 사용) |
| 도입부 | 카페 맞춤 인사말 추가 (선택) |

---

## 4. ROI 평가

### 4.1 비용

| 항목 | 예상 비용 |
|------|----------|
| 개발 | 3~5일 (API 기반, Selenium 불필요) |
| 유지보수 | 연 2~3일 (API 변경 시) |
| 인프라 | 없음 (API 호출, 브라우저 불필요) |

### 4.2 기대 수익/효과

| 항목 | 예상 |
|------|------|
| 네이버 검색 노출 | 카페탭 + 통합검색 (블로그와 유사) |
| Tistory 유입 증대 | 카페 글 내 Tistory 링크 → 트래픽 허브 역할 |
| B2B 리드 | 카페 회원 기반 커뮤니티 형성 가능 |
| AdSense 간접 효과 | Tistory 트래픽 증가 → AdSense CPC 300~400원 |

### 4.3 리스크

| 리스크 | 심각도 | 완화 |
|--------|--------|------|
| 카페 회원 부재 (조회수 0) | MEDIUM | 자유 가입 + SEO 키워드 최적화 |
| 중복 콘텐츠 페널티 | LOW | 발행 시간차 (Tistory 09:00 → 카페 10:00) |
| API 중단 가능성 | LOW | 공식 API, 장기 지원 중 |
| OAuth 토큰 만료 | LOW | refresh_token 자동 갱신 |

### 4.4 판정

| 기준 | Pipeline C (블로그) | Pipeline D (카페) |
|------|-------------------|-------------------|
| 개발 비용 | 10~15일 | **3~5일** |
| 봇 탐지 리스크 | CRITICAL | **LOW** |
| 유지보수 비용 | 높음 (DOM 변경) | **낮음 (API)** |
| 네이버 검색 노출 | 블로그탭 | 카페탭 |
| Tistory 트래픽 효과 | 간접적 | **직접적 (링크 포함)** |

→ Pipeline D는 Pipeline C 대비 **1/3 비용, 1/10 리스크**로 유사한 효과 달성 가능.

---

## 5. 구현 단계

### Phase 1: 기반 (1일)

- [ ] 네이버 개발자센터 앱 등록 (카페 API 선택)
- [ ] OAuth 2.0 최초 인증 + 토큰 발급
- [ ] 네이버 카페 개설 + 게시판 구조 설정
- [ ] Google Sheets 카페 컬럼 3개 추가 (카페상태, 카페URL, 카페발행일시)

### Phase 2: 핵심 구현 (2~3일)

- [ ] `NaverCafePort` ABC 정의
- [ ] `NaverCafeApiAdapter` 구현 (글쓰기 API 호출)
- [ ] `OAuthClient` 구현 (토큰 발급/갱신/저장)
- [ ] `CafeContentConverter` 구현 (FAQ/AdSense 제거)
- [ ] `PublishCafeUseCase` 구현
- [ ] 테스트 카페에서 API 1건 발행 검증

### Phase 3: 통합 (1일)

- [ ] CLI `--cafe` 플래그 추가
- [ ] 일일 쿼터 관리
- [ ] 에러 처리 + Slack 알림
- [ ] cron 설정 (10:00 AM)

---

## 6. 선행 조건

- [ ] Pipeline B 미해결 과제 우선 해결 (CWV, URL 버그)
- [ ] 비즈니스 목적 확정 (Tistory 트래픽 허브 vs 카페 자체 커뮤니티)
- [ ] 네이버 개발자센터 앱 등록 + 카페 API 활성화 검증
