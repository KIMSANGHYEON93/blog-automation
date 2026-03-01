# SEO 등록 가이드 — Blog Automation Phase 5

> **작성일**: 2026-02-28
> **대상 블로그**: https://kimsanghyeon.tistory.com

---

## 사전 확인 결과

| 항목 | 상태 | 비고 |
|------|------|------|
| robots.txt | ✅ 정상 | `/guestbook`, `/manage`, `/admin`, `/search` 차단 |
| sitemap.xml | ✅ 존재 | Tistory 자동 생성, ~154번 글까지 포함 |
| RSS | ✅ 존재 | `https://kimsanghyeon.tistory.com/rss`, 8건 |
| 최근 글 (176~181) | ⚠️ 비공개 | RSS/sitemap에 미포함 — **공개 전환 필요** |
| robots.txt Sitemap 지시 | ❌ 없음 | Tistory 관리자에서 설정 불가 (자동 관리) |
| HTTPS | ✅ | SSL 적용됨 |

### 비공개 → 공개 전환 (필수 선행 작업)

Pipeline B가 비공개로 발행한 글을 공개 전환해야 SEO가 시작됩니다.

1. https://kimsanghyeon.tistory.com/manage/posts 접속
2. 비공개 글 6건 (176~181) 선택
3. 각 글 편집 → 공개 설정 변경 → 저장
4. 또는 **Pipeline B의 `tistory_editor.py`**에서 공개 발행 로직이 정상 동작하면 향후 자동 처리됨

---

## 5.3 Google Search Console 등록

### 절차

1. https://search.google.com/search-console 접속 (Google 계정 로그인)
2. **속성 추가** → `https://kimsanghyeon.tistory.com` 입력
3. **소유권 확인** 방법 선택:
   - **권장: HTML 태그 방식**
     - 제공되는 메타 태그 복사
     - 티스토리 관리 → 꾸미기 → 스킨 편집 → HTML 편집
     - `<head>` 섹션에 메타 태그 붙여넣기 → 저장
     - Search Console에서 "확인" 클릭
   - **대안: TXT 레코드** (커스텀 도메인 사용 시)
4. **사이트맵 제출**:
   - 사이트맵 → URL 입력: `sitemap.xml` → 제출
   - 추가로 `rss` 도 제출 (RSS 피드)
5. **확인 사항**:
   - 색인 생성 → 페이지 → 색인이 생성된 페이지 수 확인
   - URL 검사 → 주요 글 URL 입력하여 색인 상태 확인

### 기대 결과
- 제출 후 2~7일 내 색인 시작
- 초기에는 크롤링 빈도가 낮으므로 수동 색인 요청 병행

---

## 5.4 Google Analytics 4 (GA4) 설정

### 절차

1. https://analytics.google.com 접속
2. **속성 만들기** → 속성 이름: "김상현 IT 블로그"
3. **데이터 스트림 추가** → 웹 → URL: `https://kimsanghyeon.tistory.com`
4. **측정 ID** 복사 (G-XXXXXXXXXX 형식)
5. 티스토리에 적용:
   - 티스토리 관리 → 꾸미기 → 스킨 편집 → HTML 편집
   - `</head>` 바로 위에 GA4 스크립트 삽입:
   ```html
   <!-- Google Analytics 4 -->
   <script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
   <script>
     window.dataLayer = window.dataLayer || [];
     function gtag(){dataLayer.push(arguments);}
     gtag('js', new Date());
     gtag('config', 'G-XXXXXXXXXX');
   </script>
   ```
6. **실시간 보고서**에서 데이터 수집 확인

### 추적 이벤트 (향후)
- 페이지뷰, 스크롤 깊이, 외부 링크 클릭
- 평균 체류 시간, 이탈률

---

## 5.5 네이버 서치어드바이저 등록

### 절차

1. https://searchadvisor.naver.com 접속 (네이버 계정 로그인)
2. **웹마스터 도구** → **사이트 추가**
3. URL 입력: `https://kimsanghyeon.tistory.com`
4. **소유 확인**:
   - HTML 태그 방식: 제공되는 메타 태그를 `<head>`에 삽입 (GA4와 동일 위치)
5. **사이트맵 제출**:
   - 요청 → 사이트맵 제출 → `https://kimsanghyeon.tistory.com/sitemap.xml`
6. **RSS 제출**:
   - 요청 → RSS 제출 → `https://kimsanghyeon.tistory.com/rss`
7. **robots.txt 확인**:
   - 검증 → robots.txt → 수집 허용 상태 확인
   - 현재 robots.txt에 네이버봇 차단은 없음 ✅

### 네이버 특이사항
- 네이버는 사이트맵보다 RSS를 더 활발히 크롤링
- 블로그 콘텐츠는 네이버 검색 "VIEW" 탭에 노출
- Tistory 블로그는 네이버에서 자체 수집하는 경우도 있음

---

## 5.6 수동 색인 요청 (첫 5건)

Google Search Console 등록 후 진행합니다.

### 절차

1. Search Console → URL 검사
2. 아래 URL을 하나씩 입력하고 "색인 생성 요청" 클릭:

| # | URL | 키워드 | 비고 |
|---|-----|--------|------|
| 1 | /181 | IAM이란 무엇인가 | 공개 전환 필요 |
| 2 | /176 | Azure AD vs Okta 비교 | 공개 전환 필요 |
| 3 | /177 | SAML vs OAuth 차이 | 공개 전환 필요 |
| 4 | /178 | 제로 트러스트 보안 모델이란 | 공개 전환 필요 |
| 5 | /179 | MFA 설정 방법 가이드 | 공개 전환 필요 |

3. 각 URL 형식: `https://kimsanghyeon.tistory.com/181`
4. "색인 생성 요청" 후 1~3일 내 색인 기대

### 참고
- 하루 색인 요청 한도: 약 10~20건
- 요청 후 "URL이 Google에 등록되어 있습니다" 메시지 확인

---

## robots.txt 개선 사항 (선택)

현재 robots.txt에 `Sitemap` 지시가 없습니다. Tistory는 자동 관리하므로 직접 수정은 불가하지만, Google/네이버에 사이트맵을 수동 제출하면 동일한 효과를 얻습니다.

---

## 체크리스트

- [ ] 비공개 글 → 공개 전환 (6건)
- [ ] Google Search Console 등록 + 소유권 확인
- [ ] Search Console에 sitemap.xml + rss 제출
- [ ] GA4 속성 생성 + 추적 코드 삽입
- [ ] 네이버 서치어드바이저 등록 + 소유 확인
- [ ] 네이버에 사이트맵 + RSS 제출
- [ ] 수동 색인 요청 5건
- [ ] 발행대기 14건 → Pipeline B로 공개 발행 (태그 포함)
