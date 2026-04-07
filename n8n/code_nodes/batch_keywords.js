/**
 * Batch Keywords — 키워드를 10개씩 배치로 분할
 * Mode: runOnceForAllItems
 * 위치: Sheets Read (검색볼륨 비어있는 행) → [Batch Keywords] → Loop
 * 입력: 검색볼륨이 비어있는 키워드 행 목록
 * 출력: 10개씩 묶인 배치 배열 (각 배치가 하나의 아이템)
 *
 * Google Ads generateKeywordIdeas API는 요청당 최대 20개 키워드를 지원하지만,
 * 안정성과 rate limit을 고려하여 10개씩 배치 처리.
 */

const MAX_BATCH_SIZE = 10;

const items = $input.all();

if (items.length === 0) {
  return [{ json: { batches: [], totalKeywords: 0, totalBatches: 0 } }];
}

// 키워드와 원본 행 데이터를 함께 보존
const keywordRows = items
  .map(item => ({
    keyword: (item.json['키워드'] || '').trim(),
    rowNumber: item.json['No.'] || item.json['row_number'] || '',
  }))
  .filter(row => row.keyword.length > 0);

// 10개씩 배치로 분할
const batches = [];
for (let i = 0; i < keywordRows.length; i += MAX_BATCH_SIZE) {
  const batch = keywordRows.slice(i, i + MAX_BATCH_SIZE);
  batches.push({
    batchIndex: batches.length,
    keywords: batch.map(r => r.keyword),
    rowNumbers: batch.map(r => r.rowNumber),
    size: batch.length,
  });
}

// 각 배치를 별도 아이템으로 출력 (Loop 노드에서 순회)
return batches.map(batch => ({ json: batch }));
