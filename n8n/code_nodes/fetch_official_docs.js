/**
 * Fetch Official Docs — 공식문서 본문 크롤링
 * Mode: runOnceForEachItem
 * 입력: Parse SERP Data 출력 (official_urls 포함)
 * 출력: official_docs_text 필드 추가
 *
 * Firecrawl API 키가 있으면 /v1/scrape로 마크다운 추출,
 * 없으면 직접 GET + HTML 텍스트 추출 (fallback)
 */

const FIRECRAWL_KEY = $env.FIRECRAWL_API_KEY || '';
const officialUrls = $input.item.json.official_urls || [];
const MAX_DOCS = 3;
const MAX_CHARS_PER_DOC = 3000;

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

const docs = [];

for (const entry of officialUrls.slice(0, MAX_DOCS)) {
  try {
    let content = '';

    if (FIRECRAWL_KEY) {
      // Firecrawl API v1/scrape
      const resp = await this.helpers.httpRequest({
        method: 'POST',
        url: 'https://api.firecrawl.dev/v1/scrape',
        headers: {
          'Authorization': `Bearer ${FIRECRAWL_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          url: entry.url,
          formats: ['markdown'],
          onlyMainContent: true,
        }),
        returnFullResponse: false,
        timeout: 15000,
      });

      const parsed = typeof resp === 'string' ? JSON.parse(resp) : resp;
      content = (parsed.data?.markdown || '').slice(0, MAX_CHARS_PER_DOC);
    } else {
      // Fallback: 직접 GET + 텍스트 추출
      const html = await this.helpers.httpRequest({
        method: 'GET',
        url: entry.url,
        timeout: 10000,
        encoding: 'utf-8',
        returnFullResponse: false,
        headers: {
          'User-Agent': 'Mozilla/5.0 (compatible; BlogBot/1.0)',
          'Accept': 'text/html',
        },
      });
      content = extractMainText(html).slice(0, MAX_CHARS_PER_DOC);
    }

    if (content.length > 200) {
      docs.push(`### ${entry.title}\nURL: ${entry.url}\n\n${content}`);
    }
  } catch (e) {
    // 크롤링 실패 시 skip (SERP snippet은 이미 있으므로 치명적이지 않음)
  }
}

const officialDocsText = docs.length > 0
  ? docs.join('\n\n---\n\n')
  : '';

return {
  json: {
    ...$input.item.json,
    official_docs_text: officialDocsText,
  }
};
