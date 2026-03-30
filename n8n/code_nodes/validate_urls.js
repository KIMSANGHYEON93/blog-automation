/**
 * Node 7a: URL 검증 — HTTP HEAD + SERP 교차 대조 + 죽은 URL 자동 제거
 * Mode: runOnceForEachItem
 *
 * 주의: serp_urls는 Normalize Response/Parse JSON에서 소실되므로
 *       $('Parse SERP Data') 노드에서 직접 참조한다.
 */

const helpers = this.helpers;
const item = $input.item.json;
const content = item.content || '';
const references = item.references || [];

// serp_urls는 파이프라인 중간에서 소실 → Parse SERP Data 노드에서 직접 참조
let serpUrls = [];
try {
  serpUrls = $('Parse SERP Data').item.json.serp_urls || [];
} catch { /* 노드 미존재 시 빈 배열 */ }

// URL 추출 (trailing punctuation 제거)
const urlRegex = /https?:\/\/[^\s\)\]"'<>]+/g;
const rawUrls = content.match(urlRegex) || [];
const contentUrls = rawUrls.map(u => u.replace(/[.,;:!?)]+$/, ''));

// 모든 고유 URL 수집 (content + references)
const allUrls = [...new Set([
  ...contentUrls,
  ...references.filter(r => r.startsWith('http')),
])];

const issues = [];
const deadUrls = [];
const serpMatched = [];
const serpUnmatched = [];

// SERP 도메인 추출 (교차 대조용)
const serpDomains = new Set();
for (const url of serpUrls) {
  try { serpDomains.add(new URL(url).hostname); } catch {}
}

/**
 * HTTP 검증 — try/catch 패턴 (axios 기반)
 * 성공(2xx) = 반환값 존재, 실패(4xx/5xx/타임아웃) = 예외 발생
 */
async function checkUrl(url) {
  // 형식 검증 (HTTP 스킵)
  if (url.includes('...') || url.includes(' ')) {
    return { url, status: 'broken_format' };
  }
  if (url.includes('contoso.com') || url.includes('example.com')) {
    return { url, status: 'placeholder' };
  }

  // HEAD 시도
  try {
    await helpers.httpRequest({
      method: 'HEAD',
      url: url,
      timeout: 5000,
    });
    return { url, status: 'ok' };
  } catch {
    // HEAD 실패 → GET 폴백 (일부 서버 HEAD 거부)
    try {
      await helpers.httpRequest({
        method: 'GET',
        url: url,
        timeout: 5000,
        maxContentLength: 1024,
      });
      return { url, status: 'ok' };
    } catch {
      return { url, status: 'dead' };
    }
  }
}

// 병렬 검증 (배치 5개)
const results = [];
for (let i = 0; i < allUrls.length; i += 5) {
  const batch = allUrls.slice(i, i + 5);
  const batchResults = await Promise.all(batch.map(checkUrl));
  results.push(...batchResults);
}

// 결과 분류
for (const r of results) {
  if (r.status === 'placeholder') continue;

  if (r.status === 'broken_format' || r.status === 'dead') {
    issues.push(`접근 불가: ${r.url}`);
    deadUrls.push(r.url);
  }

  // SERP 교차 대조
  try {
    const domain = new URL(r.url).hostname;
    if (serpDomains.has(domain)) {
      serpMatched.push(r.url);
    } else {
      serpUnmatched.push(r.url);
    }
  } catch {}
}

// 죽은 URL 제거: [텍스트](deadUrl) → 텍스트
let cleanedContent = content;
for (const deadUrl of deadUrls) {
  const escaped = deadUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  cleanedContent = cleanedContent.replace(
    new RegExp(`\\[([^\\]]+)\\]\\(${escaped}\\)`, 'g'),
    '$1'
  );
}

// 죽은 URL을 references에서도 제거
const cleanedReferences = references.filter(ref => {
  if (!ref.startsWith('http')) return true;
  return !deadUrls.includes(ref);
});

const passed = deadUrls.length === 0;

return {
  json: {
    ...item,
    content: cleanedContent,
    references: cleanedReferences,
    url_validation: {
      passed,
      total_urls: allUrls.length,
      reachable: results.filter(r => r.status === 'ok').length,
      dead: deadUrls.length,
      serp_matched: serpMatched.length,
      serp_unmatched: serpUnmatched.length,
      issues,
    }
  }
};
