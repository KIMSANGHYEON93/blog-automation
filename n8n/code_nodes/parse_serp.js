/**
 * Parse SERP Data — SerpAPI 결과 구조화 추출
 * Mode: runOnceForEachItem
 * 입력: SerpAPI JSON 응답 (각 아이템)
 * 출력: 구조화된 SERP 텍스트 (프롬프트에 삽입용)
 */

// 공식 문서 도메인 리스트
const OFFICIAL_DOMAINS = [
  'learn.microsoft.com', 'docs.aws.amazon.com', 'cloud.google.com',
  'developer.mozilla.org', 'docs.docker.com', 'kubernetes.io/docs',
  'docs.github.com', 'developer.hashicorp.com', 'docs.ansible.com',
  'docs.oracle.com', 'docs.redhat.com', 'wiki.archlinux.org',
  'man7.org', 'nginx.org/en/docs', 'docs.python.org',
  'go.dev/doc', 'docs.microsoft.com', 'cloud.google.com/docs',
  'docs.anthropic.com', 'platform.openai.com/docs',
];

// n8n Code 노드(vm2)에는 Node 전역 URL이 없다 — url 모듈로 받는다(NODE_FUNCTION_ALLOW_BUILTIN에 url)
const URLParser = (() => {
  if (typeof URL === 'function') return URL;
  try { return require('url').URL; } catch { return null; }
})();

function hostOf(raw) {
  try { return new URLParser(raw).hostname.toLowerCase().replace(/^www\./, ''); } catch { return ''; }
}

/**
 * organic link를 실제 주소로 돌려준다. 못 풀면 null(URL 풀에서 뺀다).
 * 2026-10-30부터 SerpAPI link 상당수가 실제 주소 대신 Google 중계 경로(/goto?url=…)로 온다.
 * 중계 경로는 Google에 한 번 물어 302 Location을 받는다(리다이렉트는 따라가지 않음 — 도착
 * 주소 요청·내부망 검사는 URL Validation이 한다). displayed_link에 호스트가 보이면 같을 때만 쓴다.
 */
async function resolveSerpLink(link, displayedLink, request) {
  const raw = String(link || '');
  if (/^https?:\/\//.test(raw)) return raw;
  if (!URLParser || !(raw.startsWith('/goto?') || raw.startsWith('/url?'))) return null;
  let location;
  try {
    const res = await request({
      method: 'GET',
      url: `https://www.google.com${raw}`,
      timeout: 5000,
      disableFollowRedirect: true,
      ignoreHttpStatusErrors: true,
      returnFullResponse: true,
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; BlogBot/1.0)' },
    });
    const code = Number(res.statusCode ?? res.status);
    if (code < 300 || code >= 400) return null;
    const headers = res.headers || {};
    location = String(headers.location ?? headers.Location ?? '');
  } catch {
    return null;
  }
  if (!/^https?:\/\//.test(location)) return null;
  const host = hostOf(location);
  if (!host || host === 'google.com' || host.endsWith('.google.com')) return null;
  const shownRaw = String(displayedLink || '').split(' ')[0];
  const shown = /^https?:\/\//.test(shownRaw) ? hostOf(shownRaw) : '';
  if (shown && host !== shown && !host.endsWith(`.${shown}`)) return null;
  return location;
}

if (typeof $input === 'undefined') {
  module.exports = { OFFICIAL_DOMAINS, resolveSerpLink };
  return;
}

const serpResults = $input.item.json;
const helpers = this.helpers;
const top7 = (serpResults.organic_results || []).slice(0, 7);

return Promise.all(
  top7.map((r) => resolveSerpLink(r.link, r.displayed_link, (opts) => helpers.httpRequest(opts))),
).then((resolvedLinks) => {

  // 1. Organic Results (상위 7개) — 제목, 스니펫, URL
  let organicText = '';
  const serpUrls = [];
  const officialUrls = [];
  if (top7.length > 0) {
    organicText = top7.map((r, i) =>
      `${i + 1}. ${r.title}\n   ${r.snippet || '(스니펫 없음)'}\n   URL: ${resolvedLinks[i] || '(주소 확인 불가)'}`
    ).join('\n');
    top7.forEach((r, i) => {
      const link = resolvedLinks[i];
      if (!link) return;
      serpUrls.push(link);
      if (OFFICIAL_DOMAINS.some(d => link.includes(d))) {
        officialUrls.push({ url: link, title: r.title, snippet: r.snippet });
      }
    });
  }

  // 2. People Also Ask (관련 질문, 5개) — FAQ 재료
  let paaText = '';
  if (serpResults.related_questions && serpResults.related_questions.length > 0) {
    const top5 = serpResults.related_questions.slice(0, 5);
    paaText = top5.map((q, i) =>
      `${i + 1}. ${q.question}${q.snippet ? '\n   → ' + q.snippet : ''}`
    ).join('\n');
  }

  // 3. Related Searches (관련 검색어, 8개) — internal_link_keywords 후보
  let relatedText = '';
  if (serpResults.related_searches && serpResults.related_searches.length > 0) {
    const top8 = serpResults.related_searches.slice(0, 8);
    relatedText = top8.map(r => r.query).join(', ');
  }

  // 4. Knowledge Graph (있으면) — 정의 앵커
  let kgText = '';
  if (serpResults.knowledge_graph) {
    const kg = serpResults.knowledge_graph;
    kgText = `${kg.title || ''}: ${kg.description || kg.snippet || ''}`;
    if (kg.source) {
      kgText += ` (출처: ${kg.source.name || ''})`;
    }
    // Extract knowledge graph URL
    if (kg.source && kg.source.link) {
      serpUrls.push(kg.source.link);
    }
  }

  // 구조화된 SERP 텍스트 조합
  const sections = [];

  if (organicText) {
    sections.push(`### 검색 상위 콘텐츠 (상위 7개)\n${organicText}`);
  }
  if (paaText) {
    sections.push(`### People Also Ask (사람들이 자주 묻는 질문)\n${paaText}`);
  }
  if (relatedText) {
    sections.push(`### 관련 검색어\n${relatedText}`);
  }
  if (kgText) {
    sections.push(`### 지식 그래프 정의\n${kgText}`);
  }

  const serpText = sections.length > 0
    ? sections.join('\n\n')
    : '(SERP 데이터 없음)';

  // 시트 데이터를 함께 전달
  const sheetData = $('Sheets Read (Status=대기)').item.json;

  return {
    json: {
      ...sheetData,
      serp_text: serpText,
      serp_urls: serpUrls,
      official_urls: officialUrls.slice(0, 3),
      serp_organic_count: serpResults.organic_results ? serpResults.organic_results.length : 0,
      serp_paa_count: serpResults.related_questions ? serpResults.related_questions.length : 0,
      serp_related_count: serpResults.related_searches ? serpResults.related_searches.length : 0,
      serp_has_kg: !!serpResults.knowledge_graph,
    }
  };
});
