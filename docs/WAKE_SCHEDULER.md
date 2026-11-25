# 잠자기 대응: 깨우기 예약 LaunchDaemon (`scripts/wake/`)

맥이 잠들어 있어도 00:00 discover-keywords, 01:00 n8n 생성, 09:00 발행이 빠지지 않게, 매일 **00:55·08:55 깨우기**를
다시 예약한다. (#4, 방식 B = root LaunchDaemon으로 결정)

## 왜 필요한가

- `pmset schedule`은 **일회성 이벤트**라 매일 새로 넣어야 하고 root 권한이 필요하다. 자동화가 없어서 예약이 끊긴 날
  (11/24 00:55) 잠자기로 00:00·01:00 작업이 빠졌다.
- 이전 저장소 버전(`schedule_wake.sh` + 사용자 LaunchAgent plist)은 경로가 `~/Documents/GitHub/...`로 틀렸고
  사용자 권한으로는 `pmset schedule`이 실패해서 동작할 수 없었다(설치된 적도 없음). 이 구조로 대체했다.
- **하드웨어 전제: 충전기를 상시 연결한다.** 이 맥은 MacBook Pro이고 배터리 방전으로 꺼진 이력이 있다(11/22~23). 소프트웨어로 막을 수 없다.

## 구성과 보안 설계 (최소 권한)

| 파일 | 설치 위치 | 소유 |
|------|-----------|------|
| `wake-scheduler.sh` | `/Library/Application Support/blog-automation/wake-scheduler.sh` | root:wheel 755 |
| `com.blog-automation.wake-scheduler.plist` | `/Library/LaunchDaemons/` | root:wheel 644 |
| 로그 | `/var/log/blog-automation-wake.log` | root |

- root가 실행하는 것은 **설치된 root 소유 사본**뿐이다. 저장소(사용자가 쓸 수 있는 경로)의 파일은 root가 실행하지 않는다 → 권한 상승 경로 없음.
  저장소를 고쳐도 운영에 반영되지 않으며, 바꾸려면 설치 스크립트를 다시 실행해야 한다.
- 스크립트가 하는 일은 `pmset -g sched`로 현재 예약을 읽고 `pmset schedule wake`를 등록하는 것뿐이다. 인자·환경변수·설정 파일을 읽지 않고 시각과 경로는 파일에 고정돼 있다. 네트워크·sudoers 변경 없음.
- 오늘 포함 +3일까지(00:55·08:55) 예약하고, 이미 있는 시각은 건너뛰며(멱등), 지난 시각은 예약하지 않는다. 하루 이틀 실행이 빠져도 예약이 이어진다.
- 실행 시점: 설치/부팅 직후 1회 + 매일 12:00·23:00. 로그인 없이도(재부팅 후 로그인 전에도) 동작한다.

## 설치 (사용자가 직접 — 에이전트는 sudo를 실행하지 않는다)

설치 전에 `scripts/wake/wake-scheduler.sh`, `install.sh`, plist를 읽어 확인한다. 저장소 루트에서:

```bash
sudo bash scripts/wake/install.sh
```

확인:

```bash
pmset -g sched                       # wake at <내일> 00:55:00 / 08:55:00 ... 앞으로 며칠치가 보여야 한다
sudo launchctl print system/com.blog-automation.wake-scheduler | grep -E 'state|last exit'
cat /var/log/blog-automation-wake.log
```

다음 날 아침 `logs/`에 00:00 discover·09:00 publish 로그가 있고 헬스 체크(09:30)가 조용하면 성공이다.

## 롤백 (제거)

```bash
sudo bash scripts/wake/uninstall.sh
```

LaunchDaemon·root 스크립트·로그를 지우고, 이 스크립트가 예약한 00:55·08:55 깨우기를 취소한다(다른 프로그램의 예약은 건드리지 않는다). 확인: `pmset -g sched`.

## 한계

- 충전기 미연결로 배터리가 방전되면 깨우기도 소용없다.
- 깨우기 직후 맥이 곧 다시 잠들 수 있다. launchd는 깨어난 사이 놓친 달력 작업을 곧바로 실행하지만, 오래 걸리는 작업(09:00 발행 약 15분)이 도는 동안 시스템이 잠들지 않는지 첫 주에 로그로 확인한다(문제가 있으면 작업 쪽에 `caffeinate`를 거는 후속 작업).
- `pmset -g sched`로 예약 존재를 확인하는 헬스 체크 항목은 별도 티켓(후속)이다.
