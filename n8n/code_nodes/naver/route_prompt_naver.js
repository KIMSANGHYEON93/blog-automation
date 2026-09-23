/**
 * Route Prompt (네이버판) — 키워드 유형별 네이버 프롬프트 선택 + 사용자 메시지 조립
 * Mode: runOnceForEachItem
 * 노드 이름은 'Route Prompt (A/B/C)' 그대로 둔다 — Parse JSON Response·Sheets Update가 참조한다.
 * PROMPTS는 scripts/build_naver_workflow.py가 n8n/prompts/prompt_naver_*.md로 채운다.
 */

const PROMPTS = /*INJECT:PROMPTS*/ { E: 'PROMPT_E', F: 'PROMPT_F', G: 'PROMPT_G' } /*END:PROMPTS*/;

const JSON_SAFETY_NOTE = `

## 중요: JSON 형식 규칙
- 반드시 유효한 JSON을 출력하세요.
- content 필드의 줄바꿈은 반드시 \\n으로 이스케이프하세요.
- 문자열 내 큰따옴표는 반드시 \\"으로 이스케이프하세요.
- 문자열 내 백슬래시는 반드시 \\\\로 이스케이프하세요.
`;

function termNames(row) {
  return [row['용어'], ...String(row['별칭'] || '').split(',')]
    .map((s) => String(s || '').trim().toLowerCase())
    .filter((s) => s.length > 1);
}

function matchBrainTerms(keyword, rows, limit = 3) {
  const kw = String(keyword || '').toLowerCase();
  return (rows || [])
    .filter((r) => termNames(r).some((n) => kw.includes(n) || n.includes(kw)))
    .slice(0, limit);
}

// 부분 일치로 유형을 정하면 'AI' 같은 짧은 용어가 대부분의 키워드를 G로 끌고 간다
function isExactBrainTerm(keyword, rows) {
  const kw = String(keyword || '').trim().toLowerCase();
  return (rows || []).some((r) => termNames(r).includes(kw));
}

function choosePromptType(keyword, category, exactBrainTerm) {
  const kw = String(keyword || '').toLowerCase();
  if (/vs|비교|차이/.test(kw) || String(category || '').includes('비교')) return 'F';
  if (exactBrainTerm || /(란|이란|뜻|개념|쉽게)(\s|$)/.test(kw)) return 'G';
  return 'E';
}

function formatTopPosts(topPosts) {
  if (!topPosts || topPosts.length === 0) return '(네이버 검색 결과 없음)';
  return topPosts.map((p, i) => `${i + 1}. ${p.title}\n   ${p.description}`).join('\n');
}

function buildUserMessage({ keyword, yearMonth, topPosts, brainCards }) {
  const brainSection = brainCards && brainCards.length
    ? '\n\n## 내부 용어 정의 (이 정의를 우선 적용하고, 혼동 포인트를 본문에서 짚을 것)\n'
      + brainCards.map((r) => `### ${r['용어']}\n- 정의: ${r['한줄정의']}\n- 혼동 포인트: ${r['혼동포인트'] || '-'}`).join('\n\n')
    : '';
  return `키워드: ${keyword}\n작성 기준일: ${yearMonth}${brainSection}`
    + `\n\n## 네이버 검색 상위 글 (이 글들에 없는 정보를 1개 이상 넣을 것, 문장 베끼기 금지)\n`
    + formatTopPosts(topPosts);
}

if (typeof $input === 'undefined') {
  module.exports = { PROMPTS, matchBrainTerms, isExactBrainTerm, choosePromptType, buildUserMessage };
  return;
}

const input = $input.item.json;
const keyword = input['키워드'] || '';
const brainRows = $('Sheets Read (Brain Terms)').all().map((i) => i.json);
const promptType = choosePromptType(keyword, input['콘텐츠유형'], isExactBrainTerm(keyword, brainRows));
const today = new Date();

return {
  json: {
    keyword,
    category: input['콘텐츠유형'] || '',
    row_index: input['__row_index'] || input['row_number'] || 0,
    prompt_type: promptType,
    system_prompt: PROMPTS[promptType] + JSON_SAFETY_NOTE,
    user_message: buildUserMessage({
      keyword,
      yearMonth: `${today.getFullYear()}년 ${today.getMonth() + 1}월`,
      topPosts: input.top_posts || [],
      brainCards: matchBrainTerms(keyword, brainRows),
    }),
  },
};
