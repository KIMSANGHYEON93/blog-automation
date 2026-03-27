/**
 * Check Duplicate — 기존 발행글과 키워드 유사도 비교
 * Mode: runOnceForAllItems
 * 위치: Sheets Read (Status=대기) → [Check Duplicate] → IF Not Duplicate?
 * 입력: Sheets Read (대기) 결과 (각 아이템에 키워드 포함)
 * 참조: Sheets Read (Published Keywords) 노드에서 기존 키워드 가져옴
 * 출력: duplicate_check 필드 추가된 아이템
 */

// 이전에 실행된 "Sheets Read (Published Keywords)" 노드에서 발행 완료/대기 키워드 조회
const publishedItems = $('Sheets Read (Published Keywords)').all();
const existingKeywords = publishedItems
  .map(item => item.json['키워드'] || '')
  .filter(kw => kw.length > 0);

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

const results = [];
for (const item of $input.all()) {
  const keyword = item.json['키워드'] || '';
  let isDuplicate = false;
  let duplicateOf = '';
  let maxOverlap = 0;

  for (const existing of existingKeywords) {
    const overlap = keywordOverlap(keyword, existing);
    if (overlap > maxOverlap) {
      maxOverlap = overlap;
      duplicateOf = existing;
    }
    if (overlap >= OVERLAP_THRESHOLD) {
      isDuplicate = true;
      break;
    }
  }

  results.push({
    json: {
      ...item.json,
      duplicate_check: {
        is_duplicate: isDuplicate,
        duplicate_of: isDuplicate ? duplicateOf : '',
        max_overlap: Math.round(maxOverlap * 100) / 100,
        threshold: OVERLAP_THRESHOLD,
      }
    }
  });
}

return results;
