"""기존 발행 글 카테고리 일괄 수정 스크립트 (one-time migration).

전략 (v2 — UI 자동화):
1. posts.json 페이지네이션으로 전체 포스트 카테고리 맵 구축
2. Google Sheets 대상과 교차 비교하여 실제 수정 필요 항목만 선별
3. 각 포스트의 편집 페이지(/manage/post/{id})에서 발행 레이어 UI로 카테고리 변경
   (POST /manage/post.json 직접 호출은 중복 포스트를 생성하므로 사용 불가)

Usage:
    cd blog-automation
    python scripts/fix_categories.py --dry-run    # 수정 필요 목록만 출력
    python scripts/fix_categories.py --test-one   # 첫 1건만 실제 수정
    python scripts/fix_categories.py --explore 293 # 편집 페이지 DOM 탐색
    python scripts/fix_categories.py --delete 330,331  # 중복 포스트 삭제
    python scripts/fix_categories.py              # 전체 수정
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import sys
import time

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs", "fix_categories.log",
)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# 수정 대상 카테고리 매핑 (기본값 966384와 다른 것만)
CATEGORY_MAP: dict[str, str] = {
    "용어": "991463",
    "비교": "984395",
    "트러블슈팅": "966385",
    "AI": "993759",
    "Windows": "983175",
    "Linux": "998284",
}


def get_sheets_targets(blog_name: str) -> list[dict]:
    """Google Sheets에서 카테고리 수정 후보 포스트 목록 조회."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(
        os.environ["GOOGLE_CREDS"], scopes=scopes,
    )
    client = gspread.authorize(creds)
    sheet = client.open(os.environ["SHEET_NAME"]).sheet1
    all_rows = sheet.get_all_values()

    targets = []
    for i, row in enumerate(all_rows[1:], start=2):
        status = row[9] if len(row) > 9 else ""
        category = row[2] if len(row) > 2 else ""
        entry_id = row[27] if len(row) > 27 else ""
        keyword = row[1] if len(row) > 1 else ""
        url = row[16] if len(row) > 16 else ""

        if (
            status == "발행완료"
            and category in CATEGORY_MAP
            and entry_id
            and blog_name in url
        ):
            targets.append({
                "row_index": i,
                "keyword": keyword,
                "category": category,
                "target_cat_id": CATEGORY_MAP[category],
                "entry_id": entry_id,
            })

    return targets


def fetch_all_category_ids(sb) -> dict[str, str]:
    """posts.json 페이지네이션으로 모든 포스트의 {entry_id: categoryId} 맵 구축."""
    cat_map: dict[str, str] = {}
    page = 1
    while True:
        result = sb.driver.execute_async_script("""
            var callback = arguments[arguments.length - 1];
            var page = arguments[0];
            fetch('/manage/posts.json?page=' + page, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'include'
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                callback(JSON.stringify({
                    total: data.totalCount, count: data.count,
                    items: (data.items || []).map(function(p) {
                        return { id: p.id, catId: p.categoryId };
                    })
                }));
            })
            .catch(function(e) {
                callback(JSON.stringify({error: e.message}));
            });
        """, page)

        data = json.loads(result)
        if data.get("error") or not data.get("items"):
            break

        for item in data["items"]:
            cat_map[item["id"]] = item["catId"]

        total = data.get("total", 0)
        if page * data.get("count", 15) >= total:
            break
        page += 1
        time.sleep(0.3)

    logger.info(f"posts.json에서 {len(cat_map)}건 조회 ({page}페이지)")
    return cat_map


def filter_need_fix(
    targets: list[dict], tistory_cats: dict[str, str],
) -> list[dict]:
    """실제 수정이 필요한 포스트만 필터링."""
    need_fix = []
    for t in targets:
        current = tistory_cats.get(t["entry_id"])
        if current is None:
            logger.warning(
                f"  entry {t['entry_id']} 미발견 (삭제됨?) — 건너뜀"
            )
            continue
        if current == t["target_cat_id"]:
            continue
        t["current_cat_id"] = current
        need_fix.append(t)
    return need_fix


# ---------------------------------------------------------------------------
# 편집 페이지 DOM 탐색 (디버깅용)
# ---------------------------------------------------------------------------

def explore_edit_page(sb, blog_name: str, entry_id: str) -> None:
    """편집 페이지의 DOM 구조를 탐색하여 카테고리 관련 요소 출력."""
    edit_url = f"https://{blog_name}.tistory.com/manage/post/{entry_id}"
    logger.info(f"편집 페이지 탐색: {edit_url}")
    sb.open(edit_url)
    time.sleep(8)

    # 에디터 로드 확인
    info = sb.execute_script("""
        var result = {};

        // 제목
        var titleEl = document.querySelector('#post-title-inp');
        result.title = titleEl ? titleEl.value : '(없음)';

        // 완료/발행 버튼
        var pubBtn = document.querySelector('#publish-layer-btn');
        result.publishLayerBtn = pubBtn ? {
            text: pubBtn.textContent.trim(),
            visible: pubBtn.offsetParent !== null
        } : null;

        // 카테고리 관련 select 요소
        var selects = document.querySelectorAll('select');
        result.selects = [];
        for (var i = 0; i < selects.length; i++) {
            var s = selects[i];
            var opts = [];
            for (var j = 0; j < Math.min(s.options.length, 20); j++) {
                opts.push({
                    value: s.options[j].value,
                    text: s.options[j].text.trim()
                });
            }
            result.selects.push({
                name: s.name || '',
                id: s.id || '',
                classes: s.className || '',
                value: s.value,
                optionCount: s.options.length,
                options: opts
            });
        }

        // 카테고리 버튼/드롭다운
        var catBtns = document.querySelectorAll(
            '[class*="category"], [class*="Category"], '
            + '[id*="category"], [id*="Category"]'
        );
        result.categoryElements = [];
        for (var i = 0; i < catBtns.length; i++) {
            var el = catBtns[i];
            result.categoryElements.push({
                tag: el.tagName,
                id: el.id || '',
                classes: el.className || '',
                text: el.textContent.trim().substring(0, 100)
            });
        }

        return result;
    """)

    logger.info(f"=== 편집 페이지 탐색 결과 ===")
    logger.info(f"  제목: {info.get('title', '?')}")
    logger.info(f"  완료 버튼: {info.get('publishLayerBtn')}")
    logger.info(f"  select 요소: {len(info.get('selects', []))}개")
    for s in info.get("selects", []):
        logger.info(f"    name={s['name']}, id={s['id']}, value={s['value']}, "
                     f"options={s['optionCount']}개")
        for opt in s.get("options", [])[:10]:
            logger.info(f"      {opt['value']}: {opt['text']}")
    logger.info(f"  카테고리 관련 요소: {len(info.get('categoryElements', []))}개")
    for el in info.get("categoryElements", []):
        logger.info(f"    <{el['tag']}> id={el['id']} class={el['classes'][:60]} "
                     f"text={el['text'][:50]}")

    # 발행 레이어 열기
    logger.info("완료 버튼 클릭 → 발행 레이어 탐색...")
    sb.execute_script("""
        var btn = document.querySelector('#publish-layer-btn');
        if (btn) btn.click();
    """)
    time.sleep(2)

    layer_info = sb.execute_script("""
        var result = {};

        // 발행 레이어 내 select
        var selects = document.querySelectorAll('select');
        result.selects = [];
        for (var i = 0; i < selects.length; i++) {
            var s = selects[i];
            var opts = [];
            for (var j = 0; j < Math.min(s.options.length, 20); j++) {
                opts.push({
                    value: s.options[j].value,
                    text: s.options[j].text.trim()
                });
            }
            result.selects.push({
                name: s.name || '',
                id: s.id || '',
                classes: s.className || '',
                value: s.value,
                optionCount: s.options.length,
                options: opts
            });
        }

        // 발행 버튼 (발행하기)
        var pubBtn = document.querySelector('#publish-btn');
        result.publishBtn = pubBtn ? {
            text: pubBtn.textContent.trim(),
            visible: pubBtn.offsetParent !== null,
            disabled: pubBtn.disabled
        } : null;

        // 발행 레이어 내 visibility 라디오
        var radios = document.querySelectorAll('input[type="radio"]');
        result.radios = [];
        for (var i = 0; i < radios.length; i++) {
            var r = radios[i];
            result.radios.push({
                name: r.name,
                id: r.id,
                value: r.value,
                checked: r.checked
            });
        }

        // 레이어 내 카테고리 관련 요소
        var catEls = document.querySelectorAll(
            '[class*="category"], [class*="Category"], '
            + '[id*="category"], [id*="Category"]'
        );
        result.categoryElements = [];
        for (var i = 0; i < catEls.length; i++) {
            var el = catEls[i];
            result.categoryElements.push({
                tag: el.tagName,
                id: el.id || '',
                classes: el.className || '',
                text: el.textContent.trim().substring(0, 100)
            });
        }

        return result;
    """)

    logger.info(f"=== 발행 레이어 탐색 결과 ===")
    logger.info(f"  발행 버튼: {layer_info.get('publishBtn')}")
    logger.info(f"  select 요소: {len(layer_info.get('selects', []))}개")
    for s in layer_info.get("selects", []):
        logger.info(f"    name={s['name']}, id={s['id']}, value={s['value']}, "
                     f"options={s['optionCount']}개")
        for opt in s.get("options", [])[:10]:
            logger.info(f"      {opt['value']}: {opt['text']}")
    logger.info(f"  라디오 버튼: {layer_info.get('radios', [])}")
    logger.info(f"  카테고리 관련 요소: {len(layer_info.get('categoryElements', []))}개")
    for el in layer_info.get("categoryElements", []):
        logger.info(f"    <{el['tag']}> id={el['id']} class={el['classes'][:60]} "
                     f"text={el['text'][:50]}")


# ---------------------------------------------------------------------------
# 카테고리 변경 (UI 자동화)
# ---------------------------------------------------------------------------

def change_category_via_ui(
    sb, blog_name: str, entry_id: str, new_cat_id: str,
) -> bool:
    """편집 페이지에서 TinyMCE 카테고리 드롭다운 UI로 카테고리 변경.

    전략:
    1. 편집 페이지(/manage/post/{id}) 열기
    2. #category-btn 클릭 → TinyMCE 드롭다운 열림
    3. #category-item-{target} 클릭 → 카테고리 선택
    4. #publish-layer-btn (완료) 클릭 → 발행 설정 레이어
    5. #publish-btn (공개 발행) 클릭 → 저장
    """
    # 0. 페이지 로드 후 fetch 인터셉터 설치 (저장 API 모니터링)
    #    CDP addScriptToEvaluateOnNewDocument는 누적되어 무한 재귀를 유발하므로
    #    페이지 로드 후 execute_script로 1회만 설치

    # 1. 편집 페이지 열기
    edit_url = f"https://{blog_name}.tistory.com/manage/post/{entry_id}"
    sb.open(edit_url)
    time.sleep(8)

    # 에디터 로드 확인
    title = sb.execute_script("""
        var el = document.querySelector('#post-title-inp');
        return el ? el.value : null;
    """)
    if not title:
        logger.error(f"  편집 페이지 로드 실패 (entry={entry_id})")
        return False
    logger.info(f"  편집 페이지: '{title[:40]}...'")

    # fetch 인터셉터 설치 (페이지 로드 후 1회)
    with contextlib.suppress(Exception):
        sb.execute_script("""
            if (!window.__fetchIntercepted) {
                window.__savedRequests = [];
                var _origFetch = window.fetch;
                window.fetch = function() {
                    var url = (arguments[0] || '').toString();
                    var opts = arguments[1] || {};
                    if (url.indexOf('post.json') !== -1 && opts.method === 'POST') {
                        var bodyStr = '';
                        try { bodyStr = opts.body ? opts.body.substring(0, 500) : ''; }
                        catch(e) { bodyStr = '(body read error)'; }
                        window.__savedRequests.push({
                            url: url, body: bodyStr, ts: Date.now()
                        });
                    }
                    return _origFetch.apply(this, arguments);
                };
                window.__fetchIntercepted = true;
            }
        """)

    # 현재 카테고리 확인
    current_cat = sb.execute_script("""
        var btn = document.querySelector('#category-btn');
        return btn ? btn.textContent.trim().replace('더보기', '') : '?';
    """)
    logger.info(f"  현재 카테고리: {current_cat}")

    # 2. 카테고리 드롭다운 열기 (#category-btn 클릭)
    sb.execute_script("""
        var btn = document.querySelector('#category-btn');
        if (btn) btn.click();
    """)
    time.sleep(1)

    # 3. 대상 카테고리 항목 클릭 (#category-item-{id})
    cat_result = sb.execute_script("""
        var targetId = arguments[0];
        var itemSel = '#category-item-' + targetId;
        var item = document.querySelector(itemSel);

        if (!item) {
            // fallback: category-id 속성으로 탐색
            item = document.querySelector(
                'div[category-id=\"' + targetId + '\"]'
            );
        }

        if (!item) {
            // 드롭다운에 있는 전체 항목 리스트 반환
            var allItems = document.querySelectorAll('.mce-menu-item');
            var itemList = [];
            for (var i = 0; i < allItems.length; i++) {
                itemList.push({
                    id: allItems[i].id,
                    catId: allItems[i].getAttribute('category-id'),
                    text: allItems[i].textContent.trim()
                });
            }
            return JSON.stringify({
                error: 'item-not-found',
                target: targetId,
                available: itemList
            });
        }

        var catName = item.textContent.trim();
        item.click();
        return JSON.stringify({ok: true, name: catName, itemId: item.id});
    """, new_cat_id)

    if not cat_result:
        logger.error("  카테고리 항목 클릭 JS 실패")
        return False

    cat_data = json.loads(cat_result)
    if cat_data.get("error"):
        logger.error(f"  카테고리 항목 미발견: target={new_cat_id}")
        for item in cat_data.get("available", [])[:10]:
            logger.error(f"    {item['catId']}: {item['text']}")
        return False

    logger.info(f"  카테고리 선택: '{cat_data.get('name')}' (id={new_cat_id})")
    time.sleep(1)

    # 선택 후 버튼 텍스트 확인
    new_btn_text = sb.execute_script("""
        var btn = document.querySelector('#category-btn');
        return btn ? btn.textContent.trim().replace('더보기', '') : '?';
    """)
    logger.info(f"  카테고리 버튼: {current_cat} → {new_btn_text}")

    # 4. 완료 버튼 클릭 → 발행 설정 레이어
    sb.execute_script("""
        var btn = document.querySelector('#publish-layer-btn');
        if (btn) btn.click();
    """)
    time.sleep(2)

    # 발행 레이어 열림 확인
    layer_open = sb.execute_script("""
        var btn = document.querySelector('#publish-btn');
        return btn && btn.offsetParent !== null;
    """)
    if not layer_open:
        logger.error("  발행 레이어가 열리지 않음")
        return False

    # 5. 공개 발행 버튼 클릭 → 저장
    pub_result = sb.execute_script("""
        var btn = document.querySelector('#publish-btn');
        if (!btn) return JSON.stringify({error: 'no-publish-btn'});

        var result = {text: btn.textContent.trim()};

        // React fiber onClick
        var keys = Object.keys(btn);
        var propsKey = keys.find(function(k) {
            return k.startsWith('__reactProps$');
        });
        if (propsKey && btn[propsKey] && btn[propsKey].onClick) {
            btn[propsKey].onClick(new MouseEvent('click', {bubbles: true}));
            result.method = 'react-onClick';
            return JSON.stringify(result);
        }

        btn.click();
        result.method = 'native-click';
        return JSON.stringify(result);
    """)

    if not pub_result:
        logger.error("  발행 버튼 JS 실행 실패")
        return False

    pub_data = json.loads(pub_result)
    if pub_data.get("error"):
        logger.error(f"  발행 버튼 미발견: {pub_data['error']}")
        return False

    logger.info(
        f"  발행: '{pub_data.get('text')}' ({pub_data.get('method')})"
    )

    # 6. 저장 완료 대기
    time.sleep(5)

    # 인터셉트된 요청 확인
    intercepted = sb.execute_script(
        "return JSON.stringify(window.__savedRequests || [])"
    )
    if intercepted:
        reqs = json.loads(intercepted)
        if reqs:
            for r in reqs:
                body_preview = r.get("body", "")[:300]
                logger.info(f"  [인터셉트] POST → {body_preview[:200]}")
                if body_preview:
                    try:
                        body_obj = json.loads(r["body"])
                        sent_id = body_obj.get("id", "?")
                        sent_cat = body_obj.get("categoryId", "?")
                        logger.info(
                            f"  [인터셉트] id={sent_id}, categoryId={sent_cat}"
                        )
                    except (json.JSONDecodeError, KeyError):
                        pass
        else:
            logger.warning("  인터셉트된 저장 요청 없음")

    # 7. 페이지 전환 확인
    current_url = sb.get_current_url()
    logger.info(f"  저장 후 URL: {current_url}")

    return True


# ---------------------------------------------------------------------------
# 포스트 삭제 (중복 포스트 정리용)
# ---------------------------------------------------------------------------

def delete_posts(sb, blog_name: str, entry_ids: list[str]) -> None:
    """포스트 삭제 (DELETE /manage/post/{id}.json)."""
    for eid in entry_ids:
        logger.info(f"포스트 삭제 시도: entry={eid}")
        result = sb.driver.execute_async_script("""
            var callback = arguments[arguments.length - 1];
            var entryId = arguments[0];

            fetch('/manage/post/' + entryId + '.json', {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'include'
            })
            .then(function(resp) {
                return resp.text().then(function(text) {
                    callback(JSON.stringify({
                        ok: resp.status >= 200 && resp.status < 300,
                        status: resp.status,
                        response: text.substring(0, 300)
                    }));
                });
            })
            .catch(function(e) {
                callback(JSON.stringify({ok: false, error: e.message}));
            });
        """, eid)

        if result:
            resp = json.loads(result)
            if resp.get("ok"):
                logger.info(f"  삭제 성공: entry={eid} (status={resp.get('status')})")
            else:
                logger.error(
                    f"  삭제 실패: entry={eid} — "
                    f"{resp.get('error', resp.get('response', '?')[:200])}"
                )
        else:
            logger.error(f"  삭제 응답 없음: entry={eid}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# 카테고리 변경 검증
# ---------------------------------------------------------------------------

def verify_category_changes(
    sb, entry_ids: list[str], expected_cats: dict[str, str],
) -> tuple[int, int]:
    """posts.json으로 카테고리 변경 결과 검증. (성공, 실패) 건수 반환."""
    cat_map = fetch_all_category_ids(sb)
    ok_count = 0
    fail_count = 0
    for eid in entry_ids:
        actual = cat_map.get(eid)
        expected = expected_cats.get(eid)
        if actual == expected:
            ok_count += 1
            logger.info(f"  ✓ entry={eid} → {actual}")
        else:
            fail_count += 1
            logger.error(f"  ✗ entry={eid}: expected={expected}, actual={actual}")
    return ok_count, fail_count


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def setup_browser(blog_name: str):
    """브라우저 시작 + 인증."""
    from seleniumbase import SB

    browser_data = os.path.abspath(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".browser_data",
        )
    )
    os.makedirs(browser_data, exist_ok=True)

    sb_ctx = SB(
        headless=False,
        chromium_arg=f"--user-data-dir={browser_data}",
    )
    sb = sb_ctx.__enter__()

    # 인증 (관리 페이지 진입)
    init_url = f"https://{blog_name}.tistory.com/manage"
    sb.open(init_url)
    time.sleep(5)

    current = sb.get_current_url()
    if "accounts.kakao.com" in current or "login" in current.lower():
        logger.info("카카오 로그인 수행...")
        from src.infrastructure.browser.kakao_auth import kakao_login
        kakao_login(sb, os.environ["KAKAO_ID"], os.environ["KAKAO_PW"])
        time.sleep(5)
        sb.open(init_url)
        time.sleep(5)

    with contextlib.suppress(Exception):
        sb.driver.set_script_timeout(60)

    try:
        sb.execute_script("return document.title;")
        logger.info("브라우저 연결 확인 OK")
    except Exception as e:
        logger.error(f"브라우저 연결 실패: {e}")
        sb_ctx.__exit__(None, None, None)
        raise

    return sb, sb_ctx


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="기존 글 카테고리 일괄 수정 (v2)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="실제 수정 없이 수정 필요 목록만 출력",
    )
    parser.add_argument(
        "--test-one", action="store_true",
        help="첫 1건만 실제 수정 (안전 테스트)",
    )
    parser.add_argument(
        "--explore", type=str, metavar="ENTRY_ID",
        help="편집 페이지 DOM 탐색 (디버깅용)",
    )
    parser.add_argument(
        "--delete", type=str, metavar="IDS",
        help="중복 포스트 삭제 (쉼표 구분, 예: 330,331)",
    )
    args = parser.parse_args()

    blog_name = os.environ.get("TISTORY_BLOG", "")
    if not blog_name:
        logger.error("TISTORY_BLOG 환경 변수 미설정")
        return

    # --- 탐색 모드 ---
    if args.explore:
        sb, sb_ctx = setup_browser(blog_name)
        try:
            explore_edit_page(sb, blog_name, args.explore)
        finally:
            sb_ctx.__exit__(None, None, None)
        return

    # --- 삭제 모드 ---
    if args.delete:
        ids = [x.strip() for x in args.delete.split(",") if x.strip()]
        if not ids:
            logger.error("삭제할 ID 없음")
            return
        logger.info(f"삭제 대상: {ids}")
        sb, sb_ctx = setup_browser(blog_name)
        try:
            delete_posts(sb, blog_name, ids)
        finally:
            sb_ctx.__exit__(None, None, None)
        return

    # --- 카테고리 수정 모드 ---
    # 1. Google Sheets에서 후보 목록 조회
    logger.info("Google Sheets에서 카테고리 수정 후보 조회...")
    targets = get_sheets_targets(blog_name)
    logger.info(f"후보: {len(targets)}건")

    if not targets:
        logger.info("후보 없음 — 종료")
        return

    # 2. 브라우저 시작
    logger.info("브라우저 시작...")
    sb, sb_ctx = setup_browser(blog_name)

    try:
        # 3. Tistory 실제 카테고리 조회 (posts.json 페이지네이션)
        logger.info("Tistory 포스트 카테고리 조회...")
        tistory_cats = fetch_all_category_ids(sb)

        # 4. 실제 수정 필요 항목 필터링
        need_fix = filter_need_fix(targets, tistory_cats)
        logger.info(
            f"수정 필요: {len(need_fix)}건 "
            f"(이미 올바름: {len(targets) - len(need_fix)}건)"
        )

        if not need_fix:
            logger.info("수정 필요 없음 — 종료")
            return

        for p in need_fix:
            logger.info(
                f"  entry={p['entry_id']:>4s} | "
                f"{p['current_cat_id']} → {p['target_cat_id']} | "
                f"{p['keyword'][:50]}"
            )

        if args.dry_run:
            logger.info("[DRY-RUN] 실제 수정 없이 종료")
            return

        # 5. 카테고리 수정 실행
        work = need_fix[:1] if args.test_one else need_fix
        success = 0
        fail = 0

        for i, p in enumerate(work, 1):
            logger.info(
                f"[{i}/{len(work)}] {p['keyword'][:40]} "
                f"(entry={p['entry_id']}) "
                f"→ cat {p['target_cat_id']}"
            )

            ok = change_category_via_ui(
                sb, blog_name, p["entry_id"], p["target_cat_id"],
            )
            if ok:
                success += 1
            else:
                fail += 1

            if i < len(work):
                time.sleep(2)

        # 6. 변경 검증
        logger.info("=== 카테고리 변경 검증 ===")
        expected = {p["entry_id"]: p["target_cat_id"] for p in work}
        entry_ids = [p["entry_id"] for p in work]

        # 관리 페이지로 이동 (posts.json 호출 위해)
        sb.open(f"https://{blog_name}.tistory.com/manage")
        time.sleep(3)

        ok_count, fail_count = verify_category_changes(sb, entry_ids, expected)

        logger.info(
            f"=== 완료: 시도={len(work)}, UI성공={success}, "
            f"검증통과={ok_count}, 검증실패={fail_count} ==="
        )

    finally:
        sb_ctx.__exit__(None, None, None)


if __name__ == "__main__":
    main()
