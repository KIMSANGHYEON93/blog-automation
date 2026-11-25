# 운영 헬스 체크 (`scripts/health_check.py`)

장애가 조용히 이어지지 않게, 하루 한 번 상태를 점검해 이상이 있으면 텔레그램으로 요약 1건을 보낸다.
**읽기 전용**이다 — 아무것도 고치거나 재시작하지 않는다(자동 복구 없음). 비밀값은 출력하지 않는다.

## 점검 항목

| 항목 | 기준 | 등급 |
|------|------|------|
| launchd | `launchctl list`의 `com.blog-automation.*` 마지막 종료 코드 ≠ 0 | 오류 |
| launchd 상주 | `telegram-bot`·`dashboard-hub`에 PID 없음 | 오류 |
| 발행 | 09:00 이후, 당일 `logs/publish_YYYYMMDD_*.log`: 없음(경고)·exit≠0(오류, 예외 이름 포함)·발행 가능한데 0건(경고)·`[SKIP]`(경고) | 오류/경고 |
| 로그 신선도 | `logs/*.log` 중 가장 최근 것이 36시간 넘음 | 오류 |
| 락 | `.pipeline_b.lock` 소유 PID가 죽었거나 2시간 넘게 유지 | 오류 |
| n8n 컨테이너 | `blog-automation-n8n-1`이 running이 아님 / Docker 접근 불가 | 오류 |
| n8n 01:00 | 가장 최근 01:00(KST) 슬롯에 Content Generation 실행이 없거나 success가 없음 (01:30 전에는 판정 보류) | 오류 |

n8n 실행 이력은 컨테이너 안에서 `docker exec … node`로 `execution_entity`를 **읽기 전용(`OPEN_READONLY`)**
으로 조회한다(`startedAt`은 UTC, 스크립트가 KST로 바꿔 비교). n8n 이미지에 내장된 `sqlite3` 모듈을 쓰므로
호스트에 DB 복사본(약 150MB)을 만들지 않는다.

## 사용

```bash
.venv/bin/python scripts/health_check.py --dry-run                  # 메시지만 출력, 전송 안 함
.venv/bin/python scripts/health_check.py --dry-run --daily-summary  # 정상이어도 요약을 출력
.venv/bin/python scripts/health_check.py                            # 이상이 있을 때만 텔레그램 전송
.venv/bin/python scripts/health_check.py --daily-summary            # 정상 요약도 전송(생존 신호)
```

종료 코드: 0 정상, 1 이상 발견, 2 알림 전송 실패. 운영 저장소가 아닌 곳(worktree)에서 돌릴 때는
`BLOG_PROJECT_DIR=<운영 저장소>`로 logs/·락 위치를 지정한다(`run_pipeline_b.sh`와 같은 규약).

알림은 기존 `TelegramNotificationAdapter`를 그대로 쓴다(`.env`의 `TELEGRAM_BOT_TOKEN`·`TELEGRAM_CHAT_ID`,
메시지 앞에 `❌ [ERROR]`/`⚠️ [WARNING]`/`✅ [INFO]` 접두). 새 채널·새 비밀값은 없다.

## launchd 등록 (사용자 승인 후)

저장소의 `scripts/com.blog-automation.health-check.plist`는 **템플릿일 뿐 아직 설치되지 않았다.**
매일 09:30에 `--daily-summary`로 실행한다. 09:00 발행이 보통 15분 안에 끝나므로 09:30이면 당일 결과를 볼 수 있다.

```bash
# 설치 전 확인: 지금 상태로 어떤 메시지가 나가는지 본다
.venv/bin/python scripts/health_check.py --dry-run --daily-summary

cp scripts/com.blog-automation.health-check.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.blog-automation.health-check.plist
launchctl start com.blog-automation.health-check     # 즉시 1회 시험(실제 전송됨)
```

**롤백**: `launchctl unload ~/Library/LaunchAgents/com.blog-automation.health-check.plist && rm ~/Library/LaunchAgents/com.blog-automation.health-check.plist`.
다른 plist·`run_*.sh`·`.env`는 건드리지 않으므로 이것만으로 원상복구된다.

## 알려진 한계

- 맥이 09:30에 잠들어 있으면 깨어난 직후에 실행된다. 맥이 아예 꺼져 있으면 알림도 없다(`--daily-summary`를 켜 두면 "오늘 요약이 안 왔다"가 신호가 된다 — 외부 데드맨 감시는 범위 밖).
- 같은 이상이 이어지면 매일 같은 알림이 온다(중복 억제 없음).
- 발행 건수는 Sheets가 아니라 당일 발행 로그를 센다. 대시보드 수동 발행은 이 로그에 없다.
- `--daily-summary` 없이 쓰면 스크립트 자체가 죽었을 때 침묵한다 — 그래서 템플릿은 요약을 켜 둔 상태다.
