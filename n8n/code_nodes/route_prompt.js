/**
 * Node 4: 프롬프트 유형 분기 (content_type → 프롬프트 A/B/C 선택)
 * Mode: runOnceForEachItem
 * 입력: Parse SERP Data 노드에서 구조화된 SERP 데이터 + 시트 데이터
 * 출력: 적절한 시스템 프롬프트가 포함된 Claude API 요청 body
 */

const keyword = $input.item.json['키워드'] || $input.item.json.keyword || '';
const category = $input.item.json['콘텐츠유형'] || $input.item.json.category || 'IT 기초 용어';
const rowIndex = $input.item.json['__row_index'] || $input.item.json['row_number'] || 0;
const serpText = $input.item.json.serp_text || '';

// 프롬프트 유형 분기
const PROMPT_A = `(프롬프트 A 전문은 workflow_complete.json에 포함)`;
const PROMPT_B = `(프롬프트 B 전문은 workflow_complete.json에 포함)`;
const PROMPT_C = `(프롬프트 C 전문은 workflow_complete.json에 포함)`;

let systemPrompt;
let promptType;

if (category.includes('비교') || category.includes('트렌드') || keyword.includes('vs')) {
  systemPrompt = PROMPT_B;
  promptType = 'B';
} else if (category.includes('에러') || category.includes('트러블슈팅') || category.includes('해결')) {
  systemPrompt = PROMPT_C;
  promptType = 'C';
} else {
  systemPrompt = PROMPT_A;
  promptType = 'A';
}

// SERP URL 풀 구성
const serpUrls = $input.item.json.serp_urls || [];
const urlPoolText = serpUrls.length > 0
  ? serpUrls.map((url, i) => `${i + 1}. ${url}`).join('\n')
  : '(SERP URL 없음)';

return {
  json: {
    keyword,
    category,
    row_index: rowIndex,
    prompt_type: promptType,
    system_prompt: systemPrompt,
    user_message: `키워드: ${keyword}\n\n## SERP 인텔리전스\n${serpText}\n\n## 참조 가능 URL 풀\n아래 URL만 references와 인라인 출처에 사용하세요:\n${urlPoolText}`,
  }
};
