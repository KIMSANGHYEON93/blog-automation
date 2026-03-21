/**
 * Parse SERP Data — SerpAPI 결과 구조화 추출
 * Mode: runOnceForEachItem
 * 입력: SerpAPI JSON 응답 (각 아이템)
 * 출력: 구조화된 SERP 텍스트 (프롬프트에 삽입용)
 */

const serpResults = $input.item.json;

// 1. Organic Results (상위 7개) — 제목, 스니펫, URL
let organicText = '';
const serpUrls = [];
if (serpResults.organic_results && serpResults.organic_results.length > 0) {
  const top7 = serpResults.organic_results.slice(0, 7);
  organicText = top7.map((r, i) =>
    `${i + 1}. ${r.title}\n   ${r.snippet || '(스니펫 없음)'}\n   URL: ${r.link || ''}`
  ).join('\n');
  for (const r of top7) {
    if (r.link) serpUrls.push(r.link);
  }
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
    serp_organic_count: serpResults.organic_results ? serpResults.organic_results.length : 0,
    serp_paa_count: serpResults.related_questions ? serpResults.related_questions.length : 0,
    serp_related_count: serpResults.related_searches ? serpResults.related_searches.length : 0,
    serp_has_kg: !!serpResults.knowledge_graph,
  }
};
