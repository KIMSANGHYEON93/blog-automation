/**
 * Parse SERP Data (네이버판) — 네이버 검색 상위 글을 프롬프트용으로 정리
 * Mode: runOnceForEachItem
 * 입력: Naver Search (SerpAPI) 노드 응답 (engine=naver, web_results — 블로그·카페·웹 문서)
 *   네이버 검색 API 발급이 막혀 SerpAPI를 쓴다. SerpAPI는 블로그 전용(where=blog)을 지원하지 않는다.
 * 출력: 시트 행 + serp_text, top_posts, search_ok
 * 노드 이름은 'Parse SERP Data' 그대로 둔다 — URL Validation이 이 이름으로 serp_urls를 읽는다.
 */

const TOP_LIMIT = 5;

function stripTags(value) {
  return String(value || '')
    .replace(/<[^>]+>/g, '')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .trim();
}

function summarizeNaverResults(response, limit = TOP_LIMIT) {
  const items = response && Array.isArray(response.web_results) ? response.web_results : [];
  const topPosts = items.slice(0, limit).map((it) => ({
    title: stripTags(it.title),
    description: stripTags(it.snippet),
    link: it.link || '',
  }));
  const serpText = topPosts
    .map((p, i) => `${i + 1}. ${p.title}\n   ${p.description}`)
    .join('\n');
  return { topPosts, serpText };
}

if (typeof $input === 'undefined') {
  module.exports = { stripTags, summarizeNaverResults };
  return;
}

const summary = summarizeNaverResults($input.item.json);
const sheetData = $('Sheets Read (Status=대기)').item.json;

return {
  json: {
    ...sheetData,
    serp_text: summary.serpText || '(네이버 검색 결과 없음)',
    top_posts: summary.topPosts,
    search_ok: summary.topPosts.length > 0,
    serp_urls: [],      // 경쟁 블로그 글은 인용하지 않는다
    official_urls: [],  // Fetch Official Docs는 건너뛴다
  },
};
