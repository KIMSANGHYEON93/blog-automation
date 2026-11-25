// Research(Grounding) 단계 테스트 (#17)
// 장문 생성 요청에서는 Gemini가 google_search를 고르지 않아, 짧은 검색 호출을 앞에 둔다.
// 실행: node --test "n8n/code_nodes/tests/*.test.js"
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const build = require('../build_research_request.js');
const check = require('../check_research.js');
const apply = require('../apply_research.js');
const llm = require('../build_llm_request.js');

const N8N = path.join(__dirname, '..', '..');

function grounded(text, queries) {
  return {
    candidates: [{
      content: { parts: [{ text: '생각', thought: true }, { text }] },
      finishReason: 'STOP',
      groundingMetadata: { webSearchQueries: queries, groundingChunks: [{ web: { title: 'postgresql.org' } }] },
    }],
  };
}
const UNGROUNDED = { candidates: [{ content: { parts: [{ text: '- 기억으로 쓴 사실' }] }, finishReason: 'STOP' }] };
const BASE = { keyword: 'bootstrap vs postgresql', user_message: '키워드: bootstrap vs postgresql', system_prompt: 'S', row_index: 7 };

// --- Build Research Request ---

test('Research 요청은 google_search를 켜고 JSON 출력 지시가 없다', () => {
  const body = build.buildResearchBody('bootstrap vs postgresql', '2026-11-26');
  assert.deepEqual(body.tools, [{ google_search: {} }]);
  assert.equal(body.generationConfig.responseMimeType, undefined);
  const prompt = body.contents[0].parts[0].text;
  assert.match(prompt, /bootstrap vs postgresql/);
  assert.match(prompt, /2026-11-26/);
  assert.doesNotMatch(prompt, /JSON/);
});

test('Research 요청은 생각 수준을 낮추고 출력 한도에 여유를 둔다 (1024는 생각 토큰에 잘렸다)', () => {
  const { generationConfig } = build.buildResearchBody('k', '2026-11-26');
  assert.deepEqual(generationConfig.thinkingConfig, { thinkingLevel: 'low' });
  assert.ok(generationConfig.maxOutputTokens >= 2048);
});

// --- Check Research ---

test('검색 쿼리 수는 groundingMetadata.webSearchQueries 길이다', () => {
  assert.equal(check.countSearchQueries(grounded('- a', ['q1', 'q2'])), 2);
  assert.equal(check.countSearchQueries(UNGROUNDED), 0);
  assert.equal(check.countSearchQueries({ error: { message: '503' } }), 0);
  assert.equal(check.countSearchQueries(undefined), 0);
});

test('검색이 0회면 같은 요청을 generateContent로 다시 보낸다', () => {
  const body = build.buildResearchBody('k', '2026-11-26');
  const t = check.retryTarget(true, build.RESEARCH_URL, body);
  assert.equal(t.url, build.RESEARCH_URL);
  assert.deepEqual(t.body, body);
});

test('검색했으면 재시도 노드는 과금 없는 countTokens로만 지나간다', () => {
  const body = build.buildResearchBody('k', '2026-11-26');
  const t = check.retryTarget(false, build.RESEARCH_URL, body);
  assert.match(t.url, /:countTokens$/);
  assert.deepEqual(Object.keys(t.body), ['contents']);
});

// --- Apply Research ---

test('검색한 응답의 사실을 사용자 메시지 끝에 섹션으로 넣는다 (생각 part·URL 제외)', () => {
  const resp = grounded('- PostgreSQL 18.1 출시 (https://www.postgresql.org/about/news/)\n- Bootstrap 5.3', ['q']);
  const out = apply.applyResearch(BASE, { first: resp, retried: false, retry: null, today: '2026-11-26' });
  assert.match(out.user_message, /^키워드: bootstrap vs postgresql/);
  assert.match(out.user_message, /## 검색으로 확인한 최신 사실 \(작성 기준일 2026-11-26\)/);
  assert.match(out.user_message, /PostgreSQL 18\.1 출시/);
  assert.doesNotMatch(out.user_message, /https?:\/\//);
  assert.doesNotMatch(out.user_message, /생각/);
  assert.equal(out._research_queries, 1);
  assert.equal(out._research_attempts, 1);
  assert.equal(out.research_warning, '');
});

test('첫 호출이 0회고 재시도에서 검색하면 재시도 결과를 쓴다', () => {
  const out = apply.applyResearch(BASE, {
    first: UNGROUNDED, retried: true, retry: grounded('- Bootstrap 5.3.8', ['q1', 'q2', 'q3']), today: '2026-11-26',
  });
  assert.match(out.user_message, /Bootstrap 5\.3\.8/);
  assert.doesNotMatch(out.user_message, /기억으로 쓴 사실/);
  assert.equal(out._research_queries, 3);
  assert.equal(out._research_attempts, 2);
  assert.equal(out.research_warning, '');
});

test('재시도까지 0회면 검색 안 된 답은 넣지 않고 경고를 남긴다', () => {
  const out = apply.applyResearch(BASE, { first: UNGROUNDED, retried: true, retry: UNGROUNDED, today: '2026-11-26' });
  assert.equal(out.user_message, BASE.user_message);
  assert.equal(out._research_queries, 0);
  assert.equal(out._research_attempts, 2);
  assert.match(out.research_warning, /검색 0회/);
});

test('Research 실패(HTTP 오류)는 생성을 막지 않고 경고만 남긴다', () => {
  const out = apply.applyResearch(BASE, { first: { error: { message: '503' } }, retried: true, retry: { error: { message: '503' } }, today: '2026-11-26' });
  assert.equal(out.user_message, BASE.user_message);
  assert.match(out.research_warning, /검색 0회/);
});

test('원본 필드는 그대로, 임시 필드(_research_body 등)는 뒤로 넘기지 않는다', () => {
  const base = { ...BASE, _research_body: {}, _research_url: 'u', _research_retry: true, _research_retry_url: 'u', _research_retry_body: {} };
  const out = apply.applyResearch(base, { first: grounded('- a', ['q']), retried: false, retry: null, today: '2026-11-26' });
  assert.equal(out.system_prompt, 'S');
  assert.equal(out.row_index, 7);
  for (const k of ['_research_body', '_research_url', '_research_retry', '_research_retry_url', '_research_retry_body']) {
    assert.equal(k in out, false, k);
  }
});

// --- 생성 요청 ---

test('글 생성 요청에는 google_search를 넣지 않는다 (장문 생성에서는 쓰이지 않았다)', () => {
  const body = llm.PROVIDERS.gemini.body('sys', 'user', llm.optionsFor('content_gen'));
  assert.equal(body.tools, undefined);
});

// --- 워크플로 연결 ---

const CHAIN = [
  'Route Prompt (A/B/C)',
  'Build Research Request',
  'Research Request',
  'Check Research',
  'Research Request (Retry)',
  'Apply Research',
  'Build LLM Request (Content Gen)',
];

for (const file of ['workflow_complete.json', 'workflow_naver.json']) {
  const wf = JSON.parse(fs.readFileSync(path.join(N8N, file), 'utf8'));
  const incoming = {};
  for (const [src, conn] of Object.entries(wf.connections)) {
    for (const outs of conn.main || []) for (const l of outs || []) (incoming[l.node] ||= []).push(src);
  }

  test(`${file}: Route Prompt → Research → 생성이 한 줄로 이어진다`, () => {
    for (let i = 0; i < CHAIN.length - 1; i += 1) {
      const outs = wf.connections[CHAIN[i]].main;
      assert.deepEqual(outs.map((o) => o.map((l) => l.node)), [[CHAIN[i + 1]]], CHAIN[i]);
    }
  });

  test(`${file}: Research 노드는 입력이 하나뿐이다 (입력이 둘이면 n8n이 두 번 실행한다)`, () => {
    for (const name of CHAIN.slice(1)) assert.equal((incoming[name] || []).length, 1, name);
  });

  test(`${file}: Research HTTP 노드는 Gemini 자격증명으로 보내고 실패해도 흐름을 잇는다`, () => {
    for (const name of ['Research Request', 'Research Request (Retry)']) {
      const node = wf.nodes.find((n) => n.name === name);
      assert.equal(node.credentials.httpHeaderAuth.name, 'Gemini API Key (Header)', name);
      assert.equal(node.onError, 'continueRegularOutput', name);
    }
  });
}
