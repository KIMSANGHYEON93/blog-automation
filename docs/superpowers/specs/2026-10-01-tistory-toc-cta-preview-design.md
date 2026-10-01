# 티스토리 목차 다듬기 · 네이버 이웃 CTA · 대시보드 미리보기 설계

- 작성일: 2026-10-01
- 상태: 설계 승인 (구현 전)

## 1. 목표와 결정

| 항목 | 결정 |
|------|------|
| 목차 | 이미 있음(`markdown_converter`, H2~H3, 첫 H2 앞). 제목 `<h2>목차</h2>`를 제목 아닌 요소로, 한글 앵커를 읽히는 이름(`#작동-원리`)으로 |
| CTA | 네이버 블로그 이웃 추가 하나. 글 맨 끝('관련 글' 다음), 안내 한 줄 + 버튼 |
| CTA 링크 | `.env` `NAVER_BLOG_ID`로 `https://blog.naver.com/<id>`, 새 탭. 값이 없거나 형식이 이상하면 CTA 없음 |
| 적용 범위 | 앞으로 발행·수정 발행되는 글. 기존 글 일괄 수정 없음(발행일 유지 a1bee5c 실측 전) |
| 확인 | 통합 대시보드 티스토리 탭에 '미리보기' — 블로그에 들어갈 최종 HTML을 그대로 |

## 2. 구조

- **본문 변환 단일화:** `tistory_editor.publish_post`와 `update_post`에 복사돼 있는 변환 단계(마크다운 → 요약 문단 → lazy → nofollow → 내부 링크 → FAQ 스키마 → `optimize_html` → `apply_inline_styles`)를 `src/infrastructure/browser/tistory_render.py`의 `render_tistory_html(post, blog_name, cta_url="") -> str` 하나로 옮긴다. 브라우저를 쓰지 않는 순수 함수다. 발행·수정 발행·미리보기가 모두 이 함수를 쓴다. 이 단계는 출력이 한 글자도 바뀌지 않아야 한다(골든 파일 테스트).
- **목차:** `markdown_converter`의 toc 확장에 `slugify_unicode`를 쓰고, 목차 제목을 `<p class="toc-title"><strong>목차</strong></p>`로 바꾼다. `inline_styler`의 목차 제목 스타일도 이 요소를 잡게 고친다.
- **CTA:** `html_transformer.append_naver_cta(html, url)`가 블록을 HTML 끝에 붙인다. `render_tistory_html`의 맨 마지막 단계(`apply_inline_styles` 뒤)에서 부르므로 스타일러가 손대지 않는다. 블록은 자체 인라인 스타일을 가진다. 링크는 `target="_blank" rel="noopener"`(내 블로그라 nofollow 없음).
- **설정 전달:** `Config.naver_blog_url` 속성(`NAVER_BLOG_ID`가 `^[A-Za-z0-9_-]+$`일 때만 주소, 아니면 빈 문자열). `SeleniumBrowserAdapter(cta_url=...)` → `publish_post/update_post(cta_url=...)` → `render_tistory_html`. 어댑터를 만드는 모든 곳(`cli.py`, `web/platform.py`)이 `config.naver_blog_url`을 넘긴다.
- **미리보기:** `create_app(preview_raw=True)`이면 `/posts/<row>/preview`가 최종 HTML을 독립 문서로 돌려주고, 그 응답에만 CSP `sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`을 건다. 인라인 스타일은 보이고, 스크립트·쿠키·폼은 막힌다. 네이버 미리보기는 지금 그대로다. 티스토리 미리보기는 시트에서 그 행의 Post를 읽어 `render_tistory_html`로 만든다. '관련 글'·내부 링크는 발행 시점에 붙으므로 미리보기에는 없다.

## 3. 테스트

- 변환 단일화 전 출력으로 만든 골든 파일과 `render_tistory_html(cta_url="")` 출력이 같다
- 목차 제목이 `<h2>`가 아니고 스타일이 붙는다, 한글 앵커가 생기고 목차 링크와 일치한다
- `append_naver_cta`: 주소 없으면 그대로, 있으면 링크·문구·새 탭, 주소 이스케이프
- `render_tistory_html(cta_url=...)`: CTA가 맨 끝
- `Config.naver_blog_url`: 정상·빈 값·이상한 값
- 미리보기: 티스토리 응답에 sandbox CSP와 본문, 네이버 미리보기 CSP는 기존 그대로
- 기존 단위 테스트 전부 통과, ruff 0, mypy 기준선(16) 유지

## 4. 반영과 확인

master 병합 후 통합 대시보드를 재시작(`launchctl kickstart -k gui/$(id -u)/com.blog-automation.dashboard-hub`, 사용자 확인)하고 폰에서 티스토리 글 미리보기로 목차·CTA를 본다. 다음 09:00 자동 발행 글에서 한글 앵커가 티스토리 에디터를 거쳐 살아 있는지 확인한다 — 지워지면 `slugify_unicode`만 되돌린다.

## 5. 범위 밖

기존 발행 글 일괄 적용, 광고 위치 변경(CWV), 네이버 글 CTA, 이웃 추가 화면 직행 주소(실측 전).
