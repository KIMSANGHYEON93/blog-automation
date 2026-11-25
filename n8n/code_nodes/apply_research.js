/**
 * Apply Research — 검색으로 확인한 사실을 글 생성 요청의 사용자 메시지에 넣는다
 * Mode: runOnceForEachItem
 * 입력: Research Request (Retry) 응답. 첫 응답은 $('Research Request'), 원본은 $('Check Research')
 * 출력: 원본 항목(user_message에 사실 섹션 추가) + _research_queries, _research_attempts, research_warning
 *
 * - 검색한 응답만 쓴다. 재시도까지 검색 0회면 모델 기억으로 쓴 답이므로 넣지 않고 경고만 남긴다
 * - 사실 목록의 URL은 지운다. references는 지금처럼 SERP URL만 쓴다
 *   (grounding 출처는 vertexaisearch 리다이렉트 주소라 그대로 쓸 수 없다)
 * - Research가 실패해도(HTTP 오류) 생성은 이어간다 — 지금까지와 같은 입력으로 쓴다
 */

const TEMP_FIELDS = ['_research_url', '_research_body', '_research_retry', '_research_retry_url', '_research_retry_body'];

function countSearchQueries(response) {
  const queries = response?.candidates?.[0]?.groundingMetadata?.webSearchQueries;
  return Array.isArray(queries) ? queries.length : 0;
}

function extractFacts(response) {
  const parts = response?.candidates?.[0]?.content?.parts || [];
  return parts
    .filter((p) => !p.thought && typeof p.text === 'string')
    .map((p) => p.text)
    .join('')
    .replace(/\s*\(?https?:\/\/[^\s)]+\)?/g, '')
    .trim();
}

function factsSection(facts, today) {
  return `\n\n## 검색으로 확인한 최신 사실 (작성 기준일 ${today})\n`
    + '아래는 Google 검색으로 확인한 내용입니다. 버전·출시일·숫자는 이 목록을 우선 참고하세요.\n'
    + facts;
}

function applyResearch(base, { first, retried, retry, today }) {
  const response = retried ? retry : first;
  const queries = countSearchQueries(response);
  const facts = queries > 0 ? extractFacts(response) : '';
  const out = Object.fromEntries(Object.entries(base).filter(([k]) => !TEMP_FIELDS.includes(k)));
  return {
    ...out,
    user_message: facts ? base.user_message + factsSection(facts, today) : base.user_message,
    _research_queries: queries,
    _research_attempts: retried ? 2 : 1,
    research_warning: facts
      ? ''
      : `Research 사실 없음(검색 ${queries}회, 시도 ${retried ? 2 : 1}회) — 검색 사실 없이 생성: ${base.keyword || ''}`,
  };
}

if (typeof $input === 'undefined') {
  module.exports = { countSearchQueries, extractFacts, factsSection, applyResearch };
  return;
}

const base = $('Check Research').item.json;
const result = applyResearch(base, {
  first: $('Research Request').item.json,
  retried: base._research_retry === true,
  retry: $input.item.json,
  today: new Date().toISOString().slice(0, 10),
});
if (result.research_warning) console.warn(result.research_warning);

return { json: result };
