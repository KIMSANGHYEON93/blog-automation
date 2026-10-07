/**
 * Check Duplicate (네이버판) — 티스토리·네이버 두 탭의 발행 키워드와 모두 비교
 * Mode: runOnceForAllItems
 * 키워드 출처는 달라도 분야가 같아 주제가 겹칠 수 있다(설계 문서 3.4).
 */

const OVERLAP_THRESHOLD = 0.7;

function keywordOverlap(kwA, kwB) {
  const tokensA = new Set(kwA.toLowerCase().split(/\s+/).filter((t) => t.length > 0));
  const tokensB = new Set(kwB.toLowerCase().split(/\s+/).filter((t) => t.length > 0));
  // 단일 토큰 키워드: 정확 일치만 판정
  if (tokensA.size < 2 || tokensB.size < 2) {
    return kwA.toLowerCase().trim() === kwB.toLowerCase().trim() ? 1.0 : 0;
  }
  const intersection = [...tokensA].filter((t) => tokensB.has(t));
  const smaller = Math.min(tokensA.size, tokensB.size);
  return smaller > 0 ? intersection.length / smaller : 0;
}

function findDuplicate(keyword, existingKeywords, threshold = OVERLAP_THRESHOLD) {
  let maxOverlap = 0;
  let duplicateOf = '';
  for (const existing of existingKeywords) {
    const overlap = keywordOverlap(keyword, existing);
    if (overlap > maxOverlap) {
      maxOverlap = overlap;
      duplicateOf = existing;
    }
  }
  const isDuplicate = maxOverlap >= threshold;
  return {
    is_duplicate: isDuplicate,
    duplicate_of: isDuplicate ? duplicateOf : '',
    max_overlap: Math.round(maxOverlap * 100) / 100,
    threshold,
  };
}

// 대시보드 '본문 생성'은 그 행의 비고에 '생성요청'을 단다 — 있으면 그 행만, 없으면(예약 실행) 전부
function pickRequested(items) {
  const requested = items.filter((i) => String(i.json['비고'] || '').trim() === '생성요청');
  return requested.length > 0 ? requested : items;
}

if (typeof $input === 'undefined') {
  module.exports = { keywordOverlap, findDuplicate, pickRequested };
  return;
}

const keywordsOf = (nodeName) => $(nodeName).all()
  .map((item) => item.json['키워드'] || '')
  .filter((kw) => kw.length > 0);
const existing = [
  ...keywordsOf('Sheets Read (Published Keywords)'),  // 티스토리 탭
  ...keywordsOf('Sheets Read (Naver Published)'),     // 네이버 탭
];

return pickRequested($input.all()).map((item) => ({
  json: { ...item.json, duplicate_check: findDuplicate(item.json['키워드'] || '', existing) },
}));
