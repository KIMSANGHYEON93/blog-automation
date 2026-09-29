# 네이버 세션 원격 복구 설계

- 작성일: 2026-09-30
- 상태: 설계 승인 (구현 전)

## 1. 목표와 결정 사항

네이버 세션(`.browser_data_naver`)이 만료되면 지금은 맥 앞에서 `python scripts/naver_blog.py login`으로
사람이 직접 로그인해야 한다. 폰만 들고 있을 때도 세션을 되살릴 수 있게 한다.

| 항목 | 결정 | 이유 |
|------|------|------|
| 계정 보안 | 네이버 2단계 인증 사용 중 | 아이디·비밀번호 자동 입력 뒤 폰 네이버 앱 승인으로 끝낼 수 있다 |
| 알림 시점 | 매일 07:30 점검(만료일 때만) + 대시보드 발행·수정 발행이 로그인 실패로 끝날 때 | 발행하려는 순간이 아니라 미리 알게 한다 |
| 알림 채널 | 새 텔레그램 봇 `@shykimsh_bot` (`NAVER_TELEGRAM_BOT_TOKEN`), 채팅은 기존 `TELEGRAM_CHAT_ID` | 네이버 알림을 기존 티스토리 알림·재실행 봇과 분리 |
| 로그인 실행 | 대시보드 '네이버 다시 로그인' 버튼 | 상시 봇 프로세스 없이 대시보드의 인증·CSRF·락·자동 실행 시간 거부·작업 화면을 재사용 |

검토 후 뺀 방식: 새 봇이 `/naver_login` 명령까지 받는 방식(상시 롱폴링 프로세스와 명령 필터·락·진행 표시를
따로 만들어야 함), 기존 재실행 봇에 명령 추가(새 봇을 쓰지 않게 됨).

## 2. 흐름

```
[07:30 launchd] python scripts/naver_blog.py check --notify
   세션 유효 → 알림 없음
   만료     → @shykimsh_bot: "네이버 세션 만료 — 대시보드에서 [네이버 다시 로그인]  <대시보드 주소>"
[대시보드 발행·수정 발행이 로그인 실패로 끝날 때] → 같은 알림

[폰] 대시보드 '네이버 다시 로그인' (POST, CSRF)
   → PublishJobRunner kind="login" (동시에 1건, .pipeline_b.lock, 자동 실행 20분 전 거부 — 모두 기존 장치)
   → NaverBrowserAdapter.relogin()
        로그인 페이지 → 아이디·비밀번호 입력 → '로그인 상태 유지' 체크 → 제출
        → 폰 네이버 앱 승인 대기(최대 300초)
        → editor.is_logged_in 으로 세션 확인
   → 작업 화면에 결과
```

대시보드 주소는 `.env`의 `DASHBOARD_EXTRA_HOSTS` 첫 값으로 `https://<호스트>/`를 만든다. 값이 없으면 알림에 주소를 빼고 문구만 보낸다.

## 3. 구성 요소

| 위치 | 변경 |
|------|------|
| `src/infrastructure/browser/naver/selectors.py` | 로그인 페이지 셀렉터·판정 문구(비밀번호 오류, 캡차·보호조치, 2단계 인증 대기)를 한곳에 |
| `src/infrastructure/browser/naver/editor.py` | `classify_login_page(url, page_text, has_captcha) -> LoginOutcome` (순수 함수), `auto_login(sb, login_id, login_pw, timeout=300) -> LoginOutcome` |
| `src/infrastructure/browser/naver/adapter.py` | `relogin(login_id, login_pw) -> tuple[bool, str]`: 브라우저 시작 → `auto_login` → `is_logged_in` → 종료 |
| `src/infrastructure/config.py` | `naver_login_id`, `naver_login_pw`, `naver_telegram_bot_token` |
| `src/interface/web/jobs.py` | 작업 종류 `login` (기존 `generate`처럼 row 0) |
| `src/interface/web/app.py` | `POST /naver/login` 라우트와 버튼 — `runner.enabled("login")`일 때만(네이버 대시보드) |
| `src/interface/web/__main__.py` | 네이버일 때 `login` 작업 조립, 발행·수정 발행 로그인 실패 시 새 봇 알림 |
| `scripts/naver_blog.py` | `check --notify`: 만료면 새 봇으로 알림, 락이 잡혀 있으면 건너뜀 |
| `scripts/com.blog-automation.naver-session-check.plist` | 07:30 실행. 기존 launchd 스케줄은 바꾸지 않는다 |

`LoginOutcome`은 성공 / 승인 대기 / 승인 시간 초과 / 비밀번호 오류 / 캡차·보호조치 / 결과 불명 6가지.
`relogin`은 네이버 전용이라 `BrowserPort`에 넣지 않고 Composition Root(`__main__.py`)가 어댑터를 직접 부른다.

## 4. 실패 처리와 안전장치

**버튼 한 번에 로그인 시도 한 번. 자동 재시도 없음** — 실패가 반복되면 네이버가 보호조치(계정 잠김)를 건다.

| 상황 | 감지 | 결과 |
|------|------|------|
| 성공 | 로그인 페이지를 벗어나고 세션 확인 통과 | "네이버 로그인 성공" |
| 폰 승인 대기 | 2단계 인증 대기 화면 | 최대 300초 대기 |
| 승인 시간 초과 | 300초 뒤에도 로그인 페이지 | "승인 시간 초과 — 다시 누르세요" |
| 비밀번호 오류 | 오류 문구 | 즉시 중단, "아이디·비밀번호 확인 필요(.env)" |
| 캡차·보호조치 | 캡차 영역·보호조치 문구 | 즉시 중단, "캡차 — 맥에서 `naver_blog.py login`으로 직접 로그인" |
| 알 수 없는 화면 | 위 어디에도 해당 없음 | 중단, "로그인 결과 불명 — 직접 확인". 성공으로 간주하지 않는다 |
| `.env` 값 누락 | 아이디·비밀번호 빈 값 | 브라우저를 열지 않고 거부 |
| 자동 실행 중·20분 전 | 기존 락·시간 검사 | 기존 거부 메시지 |

비밀번호 보호:
- 아이디·비밀번호는 `.env`에만 둔다. 로그·작업 메시지·예외 문자열에 넣지 않는다
- 로그인 실패 때는 스크린샷을 남기지 않는다(화면에 아이디가 보임)
- 입력은 스크립트로 입력란 값만 설정한다. 클립보드·셸 명령에 남기지 않는다

알림 빈도: 아침 점검은 하루 1회이고 만료일 때만 보낸다. 발행 실패 알림은 사람이 버튼을 눌렀을 때만 생긴다.

남는 위험: 네이버가 판정 문구나 화면 구조를 바꾸면 "결과 불명"으로 끝난다. 이 경우 성공으로 넘어가지 않고 멈춘다.

## 5. 테스트

자동(브라우저 없음):
- `classify_login_page`: 6가지 상태 판정
- `auto_login`: 가짜 브라우저로 비밀번호 오류·캡차에서 1회 시도 후 중단, 로그에 비밀번호 미출력
- 대시보드: 버튼·라우트가 네이버 대시보드에만 있음, CSRF 없으면 거부, 자동 실행 20분 전 거부, 작업 중 거부
- 설정: 세 값 누락 시 거부
- `check --notify`: 가짜 알림으로 유효 → 0건, 만료 → 주소 포함 1건
- `make quality` 통과

실측(1회): 대시보드 버튼 → 폰 승인 → "로그인 성공", `check --notify` 한 번(유효 → 알림 없음), 시험 알림 1건 도착 확인.
세션을 일부러 만료시키지는 않는다 — 만료 경로는 자동 테스트로 확인한다.

## 6. 사용자 준비

1. `.env`에 `NAVER_TELEGRAM_BOT_TOKEN`, `NAVER_LOGIN_ID`, `NAVER_LOGIN_PW` 추가 (토큰이 채팅에 노출됐으므로 BotFather `/revoke`로 재발급한 값 권장)
2. 텔레그램에서 `@shykimsh_bot`에게 `/start`
3. 07:30 launchd 등록 승인
