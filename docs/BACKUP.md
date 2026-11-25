# 로컬 백업 (`scripts/backup.py`)

n8n 워크플로·자격증명과 `keyword_calendar_v2` 시트를 잃어도 되살릴 수 있게 매일 로컬에 복사해 둔다.
**읽기 전용**이다(n8n·시트를 바꾸지 않는다). 원격(클라우드) 백업은 범위 밖이다.

## 무엇을 백업하나

| 대상 | 방법 | 산출물 | 크기(2026-11-25) |
|------|------|--------|------------------|
| n8n | 컨테이너에서 `n8n export:workflow --all`, `export:credentials --all`(암호화 상태) + 암호화 키 파일 `config` | `backups/n8n/n8n_YYYYMMDD_HHMMSS.tar.gz` | 약 70KB |
| Sheets | 모든 탭을 읽기 전용 범위(`spreadsheets.readonly`)로 읽어 CSV | `backups/sheets/YYYYMMDD_HHMMSS/<탭>.csv` + `manifest.json`(탭별 행·열 수) | 약 6.5MB(대부분 `키워드 캘린더`) |

각각 최근 7개만 남긴다(`--keep`). 파일은 0600, 디렉터리는 0700, `backups/`는 gitignore.
저장 위치는 `BLOG_BACKUP_DIR`로 바꿀 수 있다(외장 디스크 등).

**백업하지 않는 것**: n8n 실행 이력(`execution_entity`, 약 150MB의 대부분), n8n 사용자 계정(복구 후 소유자 계정을 새로 만든다), `.env`·`credentials.json`(비밀값은 이 스크립트가 다루지 않는다 — 따로 보관).

## 사용

```bash
.venv/bin/python scripts/backup.py --dry-run     # 읽기 가능 여부만 확인, 파일 안 만듦
.venv/bin/python scripts/backup.py               # 둘 다 실행
.venv/bin/python scripts/backup.py --only n8n    # 한쪽만
```

종료 코드: 0 성공, 1 하나 이상 실패(한쪽이 실패해도 다른 쪽은 계속한다).

## ⚠️ 보안

`n8n_*.tar.gz`에는 **암호화된 자격증명과 그것을 푸는 키(`config`)가 함께** 들어 있다. 이 파일을 가진 사람은 자격증명을
복호화할 수 있다. 그래서 권한을 0600으로 두고, **암호화 없이 클라우드·메신저·git에 올리지 않는다.** 원격 백업을 붙일 때는
`config`를 분리하거나 파일 전체를 암호화한다(다음 라운드).

## 복구 절차

### n8n (워크플로·자격증명)

살아 있는 컨테이너에 되살리는 경우(같은 ID로 덮어쓴다 — 덮어쓰기 전에 현재 상태를 한 번 더 백업할 것):

```bash
T=$(mktemp -d) && tar -xzf backups/n8n/n8n_<시각>.tar.gz -C "$T"
docker cp "$T/workflows.json"   blog-automation-n8n-1:/tmp/workflows.json
docker cp "$T/credentials.json" blog-automation-n8n-1:/tmp/credentials.json
docker exec blog-automation-n8n-1 n8n import:workflow    --input=/tmp/workflows.json
docker exec blog-automation-n8n-1 n8n import:credentials --input=/tmp/credentials.json
docker exec blog-automation-n8n-1 rm /tmp/workflows.json /tmp/credentials.json
docker compose restart n8n        # 가져온 워크플로의 활성 상태·스케줄 반영
```

볼륨을 통째로 잃은 경우(새 볼륨): 컨테이너를 만들기 **전에** `config`를 `/home/node/.n8n/config`에 넣어야 같은 암호화 키로
자격증명이 풀린다. 새 컨테이너가 키를 새로 만들면 가져온 자격증명을 복호화하지 못한다.
가져온 뒤 n8n UI에서 소유자 계정을 만들고 워크플로 활성화 상태(Content Generation은 활성)를 확인한다.

### Sheets

탭 단위로 CSV를 되살린다. 새 스프레드시트나 같은 시트의 새 탭에서 **파일 → 가져오기 → 업로드(`<탭>.csv`)** →
"새 시트 삽입"을 고른다. 서비스 계정에 편집 권한이 있는 시트여야 파이프라인이 다시 쓴다. `manifest.json`의 행·열 수와 비교해
빠진 것이 없는지 확인한다. 파이프라인이 쓰는 탭 이름(`키워드 캘린더`, `naver_calendar` 등)은 그대로여야 한다.

## 복구 검증 기록 (2026-11-25)

- **n8n**: 백업 tar.gz만으로 일회용 컨테이너(`n8nio/n8n:1.123.22`, 빈 볼륨)에 `import:workflow`·`import:credentials` 실행 →
  워크플로 2개·자격증명 3개 가져옴. 원본과 복원본을 각각 내보내 해시(워크플로 id·이름·노드·연결, 자격증명 복호화 값)로 비교해
  **둘 다 일치**(키 `config`가 백업에 있어 복호화 가능). 운영 컨테이너·볼륨은 건드리지 않았다.
- **Sheets**: 백업 직후 7개 탭을 라이브 시트와 대조해 행 수·셀 내용이 **모두 일치**.

## launchd 등록 (사용자 승인 후)

`scripts/com.blog-automation.backup.plist`는 템플릿이고, **2026-11-25에 설치했다**(아래는 재설치·이전할 때의 절차). 매일 03:30(01:00 n8n 생성·02:00 네이버 실행 뒤)에 실행한다.

```bash
.venv/bin/python scripts/backup.py --dry-run     # 설치 전 확인
cp scripts/com.blog-automation.backup.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.blog-automation.backup.plist
```

**롤백**: `launchctl unload ~/Library/LaunchAgents/com.blog-automation.backup.plist && rm ~/Library/LaunchAgents/com.blog-automation.backup.plist`
(이미 만든 `backups/`는 그대로 남는다).

## 알려진 한계

- 같은 맥의 디스크에만 있다 — 디스크가 죽으면 백업도 같이 잃는다(원격 백업은 다음 라운드). 디스크 여유가 적으니(2026-11-25 기준 15GB) 7개 보관(약 50MB)은 괜찮지만 주기적으로 확인한다.
- 백업이 실패해도 알림은 아직 없다(`logs/backup.err`·종료 코드 1만 남는다). 헬스 체크에 "최근 백업 시각" 점검을 추가하는 것이 후속 후보.
- 맥이 03:30에 잠들어 있으면 깨어난 직후에 실행된다.
