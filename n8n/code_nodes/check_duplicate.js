/**
 * Check Duplicate — 기존 발행글과 키워드 유사도 비교
 * Mode: runOnceForEachItem
 * 콘텐츠 생성 후, Haiku 검증 전에 배치
 * 입력: 생성된 콘텐츠 + 기존 키워드 목록 (Sheets에서 조회)
 * 출력: 중복 여부 판정
 */

const newKeyword = $input.item.json.keyword || '';

// Google Sheets에서 가져온 기존 키워드 목록 (이전 노드에서 조회)
const existingKeywords = $input.item.json.existing_keywords || [];

const OVERLAP_THRESHOLD = 0.7;

function keywordOverlap(kwA, kwB) {
  const tokensA = new Set(kwA.toLowerCase().split(/\s+/).filter(t => t.length > 0));
  const tokensB = new Set(kwB.toLowerCase().split(/\s+/).filter(t => t.length > 0));
  // 단일 토큰 키워드: 정확 일치만 판정
  if (tokensA.size < 2 || tokensB.size < 2) {
    return kwA.toLowerCase().trim() === kwB.toLowerCase().trim() ? 1.0 : 0;
  }
  const intersection = [...tokensA].filter(t => tokensB.has(t));
  const smaller = Math.min(tokensA.size, tokensB.size);
  return smaller > 0 ? intersection.length / smaller : 0;
}

let isDuplicate = false;
let duplicateOf = '';
let maxOverlap = 0;

for (const existing of existingKeywords) {
  const overlap = keywordOverlap(newKeyword, existing);
  if (overlap > maxOverlap) {
    maxOverlap = overlap;
    duplicateOf = existing;
  }
  if (overlap >= OVERLAP_THRESHOLD) {
    isDuplicate = true;
    break;
  }
}

return {
  json: {
    ...$input.item.json,
    duplicate_check: {
      is_duplicate: isDuplicate,
      duplicate_of: isDuplicate ? duplicateOf : '',
      max_overlap: Math.round(maxOverlap * 100) / 100,
      threshold: OVERLAP_THRESHOLD,
    }
  }
};
