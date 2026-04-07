/**
 * Parse Keyword Metrics — Google Ads generateKeywordIdeas 응답 파싱
 * Mode: runOnceForEachItem
 * 위치: HTTP Request (Google Ads) → [Parse Keyword Metrics] → Sheets Update
 * 입력: Google Ads API 응답 + 원본 배치 키워드/행번호
 * 출력: 각 키워드별 검색볼륨/예상CPC/난이도/우선순위
 *
 * 응답 파싱 로직:
 * - avgMonthlySearches: 범위 중앙값 (100-1K→550, 1K-10K→5500 등)
 * - averageCpcMicros: ÷1,000,000 → 원화 CPC
 * - competition: LOW→30, MEDIUM→50, HIGH→80
 * - 우선순위: score = volume × CPC ÷ difficulty → A(>5)/B(>1)/C(≤1)
 */

// 월간 검색량 범위 → 중앙값 매핑
const VOLUME_MIDPOINTS = {
  'UNKNOWN': 0,
  '0': 0,
  '1-100': 50,
  '100-1K': 550,
  '1K-10K': 5500,
  '10K-100K': 55000,
  '100K-1M': 550000,
  '1M-10M': 5500000,
};

// competition enum → 난이도 점수
const COMPETITION_SCORES = {
  'UNSPECIFIED': 20,
  'UNKNOWN': 20,
  'LOW': 30,
  'MEDIUM': 50,
  'HIGH': 80,
};

/**
 * avgMonthlySearches를 숫자로 변환
 * API v18은 정수 또는 범위 문자열을 반환할 수 있음
 */
function parseSearchVolume(metrics) {
  // v18: keywordIdeaMetrics.avgMonthlySearches (정수)
  if (metrics.avgMonthlySearches != null) {
    const vol = parseInt(metrics.avgMonthlySearches, 10);
    return isNaN(vol) ? 0 : vol;
  }
  // 범위 문자열 fallback (이전 버전 호환)
  const range = metrics.monthlySearchVolumes || metrics.searchVolumeRange || '';
  return VOLUME_MIDPOINTS[range] || 0;
}

/**
 * CPC micros → 원화 변환
 * Google Ads는 micros 단위 (1,000,000 = 1 통화단위)
 */
function parseCpc(metrics) {
  const raw = metrics.averageCpcMicros;
  if (raw == null) return 0;
  const micros = Number(raw);
  // micros → KRW (이미 원화 단위)
  return isNaN(micros) || micros === 0 ? 0 : Math.round(micros / 1000000);
}

/**
 * competition enum → 난이도 점수 (0-100)
 */
function parseDifficulty(metrics) {
  const competition = metrics.competition || 'UNKNOWN';
  // competitionIndex (0-100)가 있으면 직접 사용
  if (metrics.competitionIndex != null) {
    const idx = parseInt(metrics.competitionIndex, 10);
    if (!isNaN(idx) && idx >= 0 && idx <= 100) return idx;
  }
  return COMPETITION_SCORES[competition] || 20;
}

/**
 * 우선순위 계산: score = volume × CPC ÷ difficulty
 * A: score > 5  |  B: score > 1  |  C: score ≤ 1
 */
function calculatePriority(volume, cpc, difficulty) {
  if (difficulty === 0 || volume === 0) return 'C';
  // volume을 1000 단위로 정규화
  const normalizedVolume = volume / 1000;
  // CPC를 100 단위로 정규화
  const normalizedCpc = cpc > 0 ? cpc / 100 : 0.1;
  const score = (normalizedVolume * normalizedCpc) / (difficulty / 100);
  if (score > 5) return 'A';
  if (score > 1) return 'B';
  return 'C';
}

// --- 메인 로직 ---

const apiResponse = $json.response || $json;
const batchKeywords = $json.batchKeywords || [];
const batchRowNumbers = $json.batchRowNumbers || [];

// Google Ads API 응답에서 results 추출
const results = apiResponse.results || [];

// 키워드 → 메트릭 매핑 (API 응답 기준)
const metricsMap = new Map();
for (const result of results) {
  const keyword = (result.text || result.keyword || '').toLowerCase().trim();
  const metrics = result.keywordIdeaMetrics || {};

  const volume = parseSearchVolume(metrics);
  const cpc = parseCpc(metrics);
  const difficulty = parseDifficulty(metrics);
  const priority = calculatePriority(volume, cpc, difficulty);

  metricsMap.set(keyword, { volume, cpc, difficulty, priority });
}

// 배치 키워드별 결과 생성
const output = [];
for (let i = 0; i < batchKeywords.length; i++) {
  const keyword = batchKeywords[i];
  const rowNumber = batchRowNumbers[i] || '';
  const keyLower = keyword.toLowerCase().trim();

  // API 결과에서 정확 일치만 사용 (부분 일치는 오탐 위험)
  const metrics = metricsMap.get(keyLower) ||
    { volume: 0, cpc: 0, difficulty: 20, priority: 'C' };
  const matched = metricsMap.has(keyLower);

  output.push({
    json: {
      keyword,
      rowNumber,
      검색볼륨: metrics.volume,
      예상CPC: metrics.cpc,
      난이도: metrics.difficulty,
      우선순위: metrics.priority,
      matched,
    }
  });
}

return output;
