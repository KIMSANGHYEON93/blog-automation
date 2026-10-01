# 네이버·티스토리 통합 관리자 페이지 설계

- 작성일: 2026-10-01
- 상태: 설계 승인 (구현 전)

## 1. 목표와 결정

지금은 같은 대시보드 코드가 따로 두 번 실행된다 — 네이버(`--platform naver`, 8787, launchd 상시)와 티스토리(기본, 필요할 때 8788).
주소 하나·로그인 한 번으로 두 블로그를 탭으로 전환하며 관리한다.

| 항목 | 결정 |
|------|------|
| 화면 | 한 화면 + 상단 '네이버 \| 티스토리' 탭 전환 |
| 티스토리 탭 기능 | 네이버와 같은 수준 — 지금 티스토리 대시보드 기능 그대로(목록·상세·편집·다시 생성·보관·수동 발행·수정 발행) |
| 구현 | 기존 `create_app`으로 앱 두 개를 만들어 werkzeug `DispatcherMiddleware`로 `/naver`·`/tistory`에 붙인다 |

뺀 방식: 앱 하나로 재작성(라우트·템플릿·테스트 대부분 수정), 두 프로세스 유지 + 서로 링크(포트·로그인·폰 주소가 둘로 남음).

## 2. 구조

```
launchd com.blog-automation.dashboard-hub (127.0.0.1:8787, 기존 naver-dashboard 대체)
  └ python -m src.interface.web hub
       ├ /            → 302 /naver/
       ├ /naver/...   → create_app(네이버 조립 — 지금 _serve("naver")와 같음)
       └ /tistory/... → create_app(티스토리 조립 — 지금 _serve("tistory")와 같음)
```

- `__main__._serve`의 조립 부분을 플랫폼별 앱을 돌려주는 함수로 떼어, 단독 실행과 hub가 같이 쓴다.
- `DispatcherMiddleware`가 `SCRIPT_NAME`을 넘기므로 각 앱의 `url_for`·정적 파일·폼 action·리다이렉트에 접두어가 자동으로 붙는다. 네이버 다시 로그인은 `/naver/naver/login`이 된다(동작에는 문제없음).
- 로그인 공유: 두 앱이 같은 `secret_key`와 같은 세션 쿠키 이름을 쓰고, `SESSION_COOKIE_PATH="/"`를 명시한다. CSRF 토큰도 세션에 있으므로 함께 공유된다.
- 로그인 시도 제한(IP별 5회/15분)은 `LoginThrottle` 인스턴스 하나를 두 앱의 `create_app(throttle=...)`에 넘겨 합산한다(따로 두면 10회가 된다).
- 탭: `base.html` 헤더에 `/naver/`·`/tistory/` 링크를 두고 현재 앱 탭을 강조한다. 단독 실행(`--platform`)에서는 탭을 숨긴다.

## 3. 동작·안전장치

- 작업 실행기(`PublishJobRunner`)는 앱마다 따로다. 브라우저를 여는 작업은 모두 `.pipeline_b.lock`을 먼저 잡으므로, 두 탭에서 동시에 발행하면 두 번째는 "실행 중"으로 거부된다(지금과 같은 동작).
- 티스토리 수동 발행 중 카카오 2단계 인증이 뜨면 기존처럼 텔레그램으로 즉시 알린다.
- 허용 호스트(Tailscale 주소)·보안 쿠키·자동 실행 20분 전 거부는 두 앱에 똑같이 적용된다(같은 `DashboardSettings`).
- `--platform tistory|naver` 단독 실행은 남긴다 — 문제가 생기면 예전 방식으로 되돌리는 길이다.

## 4. 테스트

- `/naver/`·`/tistory/` 각각 목록이 열리고, 링크·폼 action에 접두어가 붙는다
- 한 탭에서 로그인하면 다른 탭도 로그인 상태이고(세션 공유), 로그아웃도 함께 된다
- 로그인 실패 제한이 두 앱 합산 5회
- 탭 링크 표시와 현재 탭 강조, `/` → `/naver/`
- 기존 단위 테스트 전부 유지, `make quality` 통과

## 5. 전환 (운영 변경 — 사용자 확인 후 실행)

1. `scripts/com.blog-automation.dashboard-hub.plist`를 `~/Library/LaunchAgents`에 설치
2. 기존 `com.blog-automation.naver-dashboard`를 `launchctl unload` → 새 hub를 `load` (같은 8787이라 Tailscale `serve` 설정은 그대로)
3. 폰에서 두 탭·로그인·목록 확인
4. 되돌리기: hub unload → 기존 naver-dashboard plist load
5. CLAUDE.md 대시보드 항목 갱신

## 6. 범위 밖

두 블로그를 섞은 통합 목록, 홈 현황판, 작업 실행기 통합.
