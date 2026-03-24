"""TistoryThumbnailUploader — ThumbnailUploadPort implementation using Tistory API.

Python requests로 발행 페이지에서 title/content를 읽고,
Selenium JS로 POST /manage/post.json을 호출하여 thumbnail 설정.
"""
from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from src.domain.ports.thumbnail_upload_port import ThumbnailUploadPort

logger = logging.getLogger(__name__)


def _scrape_post(blog_name: str, entry_id: str) -> dict:
    """발행된 포스트 페이지에서 title/content/tags를 스크래핑."""
    url = f"https://{blog_name}.tistory.com/{entry_id}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # title: og:title이 가장 안정적
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title:
        title = og_title.get("content", "").strip()
    if not title:
        for selector in [
            "h2.title-article", ".entry-title", ".post-title",
        ]:
            el = soup.select_one(selector)
            if el and el.get_text(strip=True):
                title = el.get_text(strip=True)
                break
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            title = re.sub(r"\s*[-|].*$", "", title).strip()

    # content (article body HTML)
    content = ""
    for selector in [
        ".contents_style", ".article-view .contents_style",
        ".entry-content .tt_article_useless_p_margin",
        ".article-view", ".entry-content", "article",
    ]:
        el = soup.select_one(selector)
        if el and len(str(el)) > 100:
            content = str(el)
            break

    # tags
    tags = []
    for tag_el in soup.select(".article-tag a, .tags a, .tag_label a"):
        t = tag_el.get_text(strip=True).lstrip("#")
        if t:
            tags.append(t)

    return {"title": title, "content": content, "tags": ",".join(tags)}


class TistoryThumbnailUploader(ThumbnailUploadPort):
    """Tistory API를 통해 기존 포스트에 썸네일을 설정하는 어댑터.

    SeleniumBase 인스턴스(sb)가 이미 로그인된 상태에서
    에디터 페이지(/manage/newpost)에 접속한 상태로 전달되어야 함.
    """

    def __init__(self, sb, blog_name: str):
        self._sb = sb
        self._blog_name = blog_name

    def upload_thumbnail(self, entry_id: str, image_url: str) -> bool:
        """기존 포스트에 썸네일 URL 설정.

        1. requests로 발행 페이지 스크래핑 (title, content, tags)
        2. Selenium JS로 POST /manage/post.json 저장
        """
        import json as json_mod

        if not entry_id:
            logger.error("entry_id 없음 — 썸네일 업로드 불가")
            return False

        # Step 1: 발행 페이지에서 기존 데이터 읽기
        try:
            post_data = _scrape_post(self._blog_name, entry_id)
        except Exception as e:
            logger.error(f"발행 페이지 스크래핑 실패: entry_id={entry_id} — {e}")
            return False

        title = post_data["title"]
        content = post_data["content"]
        tags = post_data["tags"]

        if not title:
            logger.error(f"포스트 제목 읽기 실패: entry_id={entry_id}")
            return False

        logger.info(
            f"포스트 데이터 읽기 완료: entry_id={entry_id}, "
            f"title={title[:40]}, content_len={len(content)}, tags={tags[:50]}"
        )

        # Step 2: Selenium JS로 API 호출
        self._sb.driver.set_script_timeout(60)

        try:
            result_json = self._sb.driver.execute_async_script(
                _JS_UPDATE_THUMBNAIL,
                entry_id,
                title,
                content,
                tags,
                image_url,
                self._blog_name,
            )

            if result_json:
                result = json_mod.loads(result_json)
                if result.get("success"):
                    logger.info(
                        f"썸네일 업로드 완료: entry_id={entry_id}, "
                        f"url={image_url[:80]}"
                    )
                    return True
                logger.error(
                    f"썸네일 업로드 API 실패: entry_id={entry_id}, "
                    f"status={result.get('status')}, "
                    f"resp={str(result.get('response', ''))[:200]}"
                )
                return False

        except Exception as e:
            logger.error(f"썸네일 업로드 예외: entry_id={entry_id} — {e}")
            return False

        return False


_JS_UPDATE_THUMBNAIL = """
var callback = arguments[arguments.length - 1];
var entryId = arguments[0];
var title = arguments[1];
var content = arguments[2];
var tags = arguments[3];
var thumbnailUrl = arguments[4];
var blogName = arguments[5];

var manageUrl = '';
if (window.appInfo && window.appInfo.manageUrl) {
    manageUrl = window.appInfo.manageUrl;
} else {
    manageUrl = 'https://' + blogName + '.tistory.com/manage';
}

var postData = {
    id: entryId,
    title: title,
    content: content,
    slogan: '',
    visibility: '20',
    category: 0,
    categoryId: 0,
    tag: tags,
    acceptComment: '1',
    published: '1',
    password: '',
    thumbnail: thumbnailUrl,
    type: 'post',
    attachments: '[]',
    recaptchaValue: '',
    draftSequence: null
};

var url = manageUrl + '/post.json';

fetch(url, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest'
    },
    body: JSON.stringify(postData),
    credentials: 'include'
})
.then(function(resp) {
    return resp.text().then(function(text) {
        return { status: resp.status, text: text };
    });
})
.then(function(r) {
    callback(JSON.stringify({
        success: r.status >= 200 && r.status < 300,
        status: r.status,
        response: r.text.substring(0, 500)
    }));
})
.catch(function(e) {
    callback(JSON.stringify({
        success: false, error: 'fetch:' + e.message
    }));
});
"""
