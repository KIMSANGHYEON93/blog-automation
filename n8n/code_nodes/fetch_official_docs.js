/**
 * Fetch Official Docs — 공식문서 본문 크롤링
 * Mode: runOnceForEachItem
 * 입력: Parse SERP Data 출력 (official_urls 포함)
 * 출력: official_docs_text 필드 추가
 *
 * Firecrawl API 키가 있으면 /v1/scrape로 마크다운 추출,
 * 없으면 직접 GET + HTML 텍스트 추출 (fallback)
 *
 * 보안(SSRF): official_urls는 Parse SERP Data가 '링크 문자열에 공식 도메인이 들어 있는지'로 고른다
 * (https://evil.org/?u=docs.python.org도 통과). 그래서 여기서 호스트·경로 접두로 다시 확인하고
 * OFFICIAL_DOCS(신뢰 도메인 허용 목록) 안의 주소만 요청한다. 리다이렉트는 자동으로 따라가지 않고
 * 다음 주소도 허용 목록 안일 때만 따라간다. 한계: 허용 도메인의 DNS 자체가 내부 IP를 가리키면 막지 못한다.
 */

// parse_serp.js OFFICIAL_DOMAINS와 같은 목록 ('호스트' 또는 '호스트/경로접두')
const OFFICIAL_DOCS = [
  'learn.microsoft.com', 'docs.aws.amazon.com', 'cloud.google.com',
  'developer.mozilla.org', 'docs.docker.com', 'kubernetes.io/docs',
  'docs.github.com', 'developer.hashicorp.com', 'docs.ansible.com',
  'docs.oracle.com', 'docs.redhat.com', 'wiki.archlinux.org',
  'man7.org', 'nginx.org/en/docs', 'docs.python.org',
  'go.dev/doc', 'docs.microsoft.com', 'cloud.google.com/docs',
  'docs.anthropic.com', 'platform.openai.com/docs',
];
const MAX_DOCS = 3;
const MAX_CHARS_PER_DOC = 3000;
const MAX_HTML_CHARS = 2000000; // 정규식 처리 전에 자른다
const MAX_REDIRECTS = 3;
const REQUEST_TIMEOUT_MS = 10000;

function isOfficialDocUrl(raw) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    return false;
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return false;
  if (u.username || u.password) return false;
  const host = u.hostname.toLowerCase().replace(/\.$/, '');
  return OFFICIAL_DOCS.some((entry) => {
    const slash = entry.indexOf('/');
    const dHost = slash < 0 ? entry : entry.slice(0, slash);
    const prefix = slash < 0 ? '' : entry.slice(slash);
    const hostOk = host === dHost || host.endsWith(`.${dHost}`);
    return hostOk && (!prefix || u.pathname === prefix || u.pathname.startsWith(`${prefix}/`));
  });
}

/** 허용 목록 안에서만 리다이렉트를 따라가며 HTML을 받는다. 실패하면 '' */
async function fetchDocHtml(url, request) {
  let current = url;
  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    if (!isOfficialDocUrl(current)) return '';
    const res = await request({
      method: 'GET',
      url: current,
      timeout: REQUEST_TIMEOUT_MS,
      encoding: 'utf-8',
      disableFollowRedirect: true,
      ignoreHttpStatusErrors: true,
      returnFullResponse: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; BlogBot/1.0)',
        'Accept': 'text/html',
      },
    });
    const code = Number(res.statusCode ?? res.status);
    if (code >= 300 && code < 400) {
      const headers = res.headers || {};
      const loc = headers.location ?? headers.Location;
      if (!loc) return '';
      try {
        current = new URL(String(loc), current).href;
      } catch {
        return '';
      }
      continue;
    }
    if (code < 200 || code >= 300) return '';
    return typeof res.body === 'string' ? res.body.slice(0, MAX_HTML_CHARS) : '';
  }
  return '';
}

/**
 * HTML에서 본문 텍스트 추출 (fallback용)
 * <main>, <article>, <div role="main"> 중 첫 매칭 태그의 텍스트 추출
 */
function extractMainText(html) {
  if (typeof html !== 'string') return '';

  // main/article/div[role=main] 태그 내용 추출 시도
  const patterns = [
    /<main[^>]*>([\s\S]*?)<\/main>/i,
    /<article[^>]*>([\s\S]*?)<\/article>/i,
    /<div[^>]*role\s*=\s*["']main["'][^>]*>([\s\S]*?)<\/div>/i,
  ];

  let bodyText = '';
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match && match[1]) {
      bodyText = match[1];
      break;
    }
  }

  // 매칭 실패 시 <body> 전체 사용
  if (!bodyText) {
    const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    bodyText = bodyMatch ? bodyMatch[1] : html;
  }

  // HTML 태그 제거 + 정리
  return bodyText
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<nav[^>]*>[\s\S]*?<\/nav>/gi, '')
    .replace(/<footer[^>]*>[\s\S]*?<\/footer>/gi, '')
    .replace(/<header[^>]*>[\s\S]*?<\/header>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

if (typeof $input === 'undefined') {
  module.exports = { isOfficialDocUrl, fetchDocHtml, extractMainText, MAX_HTML_CHARS };
  return;
}

const FIRECRAWL_KEY = $env.FIRECRAWL_API_KEY || '';
const helpers = this.helpers;
const officialUrls = ($input.item.json.official_urls || [])
  .filter((entry) => entry && isOfficialDocUrl(entry.url));

async function collectDocs() {
  const docs = [];
  for (const entry of officialUrls.slice(0, MAX_DOCS)) {
    try {
      let content = '';
      if (FIRECRAWL_KEY) {
        // Firecrawl API v1/scrape (요청은 Firecrawl 서버가 한다 — 허용 목록 주소만 넘긴다)
        const resp = await helpers.httpRequest({
          method: 'POST',
          url: 'https://api.firecrawl.dev/v1/scrape',
          headers: {
            'Authorization': `Bearer ${FIRECRAWL_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ url: entry.url, formats: ['markdown'], onlyMainContent: true }),
          returnFullResponse: false,
          timeout: 15000,
        });
        const parsed = typeof resp === 'string' ? JSON.parse(resp) : resp;
        content = ((parsed.data && parsed.data.markdown) || '').slice(0, MAX_CHARS_PER_DOC);
      } else {
        const html = await fetchDocHtml(entry.url, (opts) => helpers.httpRequest(opts));
        content = extractMainText(html).slice(0, MAX_CHARS_PER_DOC);
      }
      if (content.length > 200) {
        docs.push(`### ${entry.title}\nURL: ${entry.url}\n\n${content}`);
      }
    } catch (e) {
      // 크롤링 실패 시 skip (SERP snippet은 이미 있으므로 치명적이지 않음)
    }
  }
  return docs;
}

return collectDocs().then((docs) => ({
  json: {
    ...$input.item.json,
    official_docs_text: docs.length > 0 ? docs.join('\n\n---\n\n') : '',
  },
}));
