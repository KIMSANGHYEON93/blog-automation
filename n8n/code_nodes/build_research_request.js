/**
 * Build Research Request — 글 생성 전에 Google 검색으로 최신 사실을 확인하는 요청
 * Mode: runOnceForEachItem
 * 입력: Route Prompt 결과 (keyword, system_prompt, user_message …)
 * 출력: _research_url, _research_body + 원본 데이터 패스스루
 *
 * 왜 따로 부르나 (#17): 장문 글을 한 번에 쓰라는 요청에서는 Gemini가 google_search를
 * 고르지 않는다(저장된 생성 32건 모두 grounding 0회, 검색을 지시해도 0회).
 * 짧은 사실 확인 질문에는 검색한다 — 그래서 검색만 하는 호출을 앞에 둔다.
 * JSON 출력 지시는 넣지 않는다(검색을 덜 고르게 된다).
 * Grounding은 Gemini 기능이라 LLM_PROVIDER와 상관없이 Gemini로 보낸다.
 * API 키는 HTTP 노드의 n8n Credential(Header Auth)이 주입한다.
 */

const RESEARCH_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent';
// 생각 토큰도 이 한도 안에서 쓰인다. 1024에 기본 생각 수준이면 6건 모두 MAX_TOKENS로
// 잘리고 검색도 1건만 했다. thinkingLevel low + 여유 한도로 9건 모두 검색·STOP(2026-11-26 실측,
// 출력 480~760토큰, 8~14초)
const RESEARCH_MAX_TOKENS = 2048;

function buildResearchPrompt(keyword, today) {
  return `작성 기준일: ${today}\n`
    + `"${keyword}"에 대한 기술 블로그 글을 쓰기 전에 사실을 확인하려 합니다. `
    + 'Google 검색으로 아래 항목을 확인하고, 확인한 사실만 한국어 불릿 10줄 이내로 적으세요.\n'
    + '- 관련 제품·기술의 현재 최신 버전과 출시일\n'
    + '- 가격, 한도, 성능 수치처럼 글에 쓸 만한 숫자\n'
    + '- 최근 1년 안의 주요 변경(지원 종료, 이름 변경 등)\n'
    + '검색으로 확인하지 못한 항목은 쓰지 마세요. 서론과 맺음말 없이 불릿만 적으세요.';
}

function buildResearchBody(keyword, today) {
  return {
    contents: [{ role: 'user', parts: [{ text: buildResearchPrompt(keyword, today) }] }],
    tools: [{ google_search: {} }],
    generationConfig: {
      maxOutputTokens: RESEARCH_MAX_TOKENS,
      temperature: 0.3,
      thinkingConfig: { thinkingLevel: 'low' },
    },
  };
}

if (typeof $input === 'undefined') {
  module.exports = { RESEARCH_URL, RESEARCH_MAX_TOKENS, buildResearchPrompt, buildResearchBody };
  return;
}

const item = $input.item.json;
const today = new Date().toISOString().slice(0, 10);

return {
  json: {
    ...item,
    _research_url: RESEARCH_URL,
    _research_body: buildResearchBody(item.keyword || '', today),
  },
};
