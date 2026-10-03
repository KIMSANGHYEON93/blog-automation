// 네이버 n8n 노드의 순수 함수 테스트 — 실행: node --test "n8n/code_nodes/naver/tests/*.test.js"
const test = require('node:test');
const assert = require('node:assert/strict');

const search = require('../parse_naver_search.js');
const route = require('../route_prompt_naver.js');
const structure = require('../validate_structure_naver.js');
const verifyReq = require('../build_verify_request_naver.js');
const verdict = require('../parse_verification_naver.js');
const dup = require('../check_duplicate_naver.js');

test('검색 결과: SerpAPI 네이버 web_results에서 태그·엔티티를 벗기고 상위 5개만', () => {
  const web_results = Array.from({ length: 7 }, (_, i) => ({
    position: i + 1, title: `<b>MCP</b>란 ${i}`, snippet: '뜻&amp;예시', link: `https://blog.naver.com/a/${i}`,
  }));
  const r = search.summarizeNaverResults({ web_results });
  assert.equal(r.topPosts.length, 5);
  assert.equal(r.topPosts[0].title, 'MCP란 0');
  assert.equal(r.topPosts[0].description, '뜻&예시');
  assert.match(r.serpText, /^1\. MCP란 0/);
});

test('검색 결과: 비어 있으면 빈 목록', () => {
  const r = search.summarizeNaverResults({});
  assert.equal(r.topPosts.length, 0);
  assert.equal(r.serpText, '');
});

test('프롬프트 유형: 비교 키워드는 F', () => {
  assert.equal(route.choosePromptType('Claude vs ChatGPT 업무용', '', false), 'F');
  assert.equal(route.choosePromptType('노션 AI 옵시디언 차이', '', false), 'F');
});

test('프롬프트 유형: 개념 키워드와 볼트 용어 정확 일치는 G', () => {
  assert.equal(route.choosePromptType('MCP란', '', false), 'G');
  assert.equal(route.choosePromptType('RAG 쉽게', '', false), 'G');
  assert.equal(route.choosePromptType('하네스', '', true), 'G');
});

test('프롬프트 유형: 나머지는 E', () => {
  assert.equal(route.choosePromptType('노션 AI 사용법', '', false), 'E');
});

test('볼트 용어: 부분 일치는 정확 일치가 아니다', () => {
  const rows = [{ 용어: 'AI', 별칭: '인공지능' }, { 용어: '하네스', 별칭: 'harness' }];
  assert.equal(route.isExactBrainTerm('노션 AI 사용법', rows), false);
  assert.equal(route.isExactBrainTerm('Harness', rows), true);
});

test('사용자 메시지에 상위 글과 용어 정의가 들어간다', () => {
  const msg = route.buildUserMessage({
    keyword: 'MCP란', yearMonth: '2026년 9월',
    topPosts: [{ title: 'MCP 총정리', description: '설명' }],
    brainCards: [{ 용어: 'MCP', 한줄정의: '모델 컨텍스트 프로토콜', 혼동포인트: 'MCP ≠ API' }],
  });
  assert.match(msg, /키워드: MCP란/);
  assert.match(msg, /1\. MCP 총정리/);
  assert.match(msg, /모델 컨텍스트 프로토콜/);
});

function goodContent(keyword) {
  const para = `${keyword}는 업무에 도움이 돼요. 짧은 문단으로 씁니다.`;
  const sections = ['시작하기 전에', '단계별로 따라하기', '자주 묻는 질문']
    .map((h) => `## ${h}\n\n${'가나다라마바사 아자차카타파하. '.repeat(8)}\n\n${'설명 문장입니다. '.repeat(10)}`);
  // 문단 하나가 300자를 넘지 않게 짧은 문단 20개로 채운다 (총 3,600자 안팎)
  const filler = Array.from({ length: 20 }, () => '본문 채우기 문장이에요. '.repeat(10)).join('\n\n');
  return [para, ...sections, `${keyword} 정리예요.`, filler].join('\n\n');
}

test('구조 검사: 좋은 글은 통과', () => {
  const r = structure.validateNaverStructure({
    title: '노션 AI 사용법 총정리', content: goodContent('노션 AI 사용법'), keyword: '노션 AI 사용법',
    tags: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
  });
  assert.deepEqual(r.issues, []);
  assert.equal(r.passed, true);
});

test('구조 검사: 사진 설명 주석은 길이·문단 검사에서 뺀다', () => {
  // 주석은 블로그에 보이지 않는다 — 3,000자를 채우거나 첫 문단을 긴 문단으로 만들면 안 된다
  const kw = '노션 AI 사용법';
  const scene = `<!-- 사진: ${'a person working at a desk '.repeat(12)}-->`;
  const short = goodContent(kw).slice(0, 2900);
  const r = structure.validateNaverStructure({
    title: `${kw} 정리`, content: `${short}\n${scene}`, keyword: kw,
    tags: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'],
  });
  assert.match(r.issues.join(' | '), /본문 길이 부족/);
  assert.doesNotMatch(r.issues.join(' | '), /긴 문단/);
});

test('구조 검사: 키워드 반복 과다·외부 링크 과다·긴 문단·태그 부족을 잡는다', () => {
  const kw = '노션 AI 사용법';
  const content = goodContent(kw)
    + `\n\n${`${kw} `.repeat(7)}`
    + '\n\n[1](https://a.com) [2](https://b.com) [3](https://c.com) [4](https://d.com)'
    + `\n\n${'긴 문단입니다. '.repeat(60)}`;
  const r = structure.validateNaverStructure({ title: `${kw} 정리`, content, keyword: kw, tags: ['a'] });
  const joined = r.issues.join(' | ');
  assert.equal(r.passed, false);
  assert.match(joined, /키워드 반복 과다/);
  assert.match(joined, /외부 링크 과다/);
  assert.match(joined, /긴 문단/);
  assert.match(joined, /태그 수/);
});

test('구조 검사: 제목에 키워드가 없으면 실패', () => {
  assert.equal(structure.titleHasKeyword('업무 자동화 가이드', '노션 AI 사용법'), false);
  assert.equal(structure.titleHasKeyword('노션AI 사용법 정리', '노션 AI 사용법'), true);
});

test('검증 요청 메시지에 상위 글과 본문이 들어간다', () => {
  const msg = verifyReq.buildVerifyMessage({
    keyword: 'MCP란', title: 'MCP란 무엇인가요', content: '본문',
    topPosts: [{ title: '상위글', description: '요약' }],
  });
  assert.match(msg, /상위글 — 요약/);
  assert.match(msg, /제목: MCP란 무엇인가요/);
});

const ALL_TRUE = {
  is_accurate: true, is_logical: true, is_complete: true, is_useful: true, is_in_depth: true,
  no_fabricated_experience: true, natural_keyword_use: true, has_unique_info: true,
  mobile_readable: true, quality_score: 85, reason: '좋음',
};

test('판정: 모두 통과', () => {
  const v = verdict.judgeNaver(ALL_TRUE, { structurePassed: true, structureIssues: [], searchOk: true });
  assert.equal(v.passed, true);
  assert.equal(v.quality_score, 85);
});

test('판정: 경험 날조는 점수와 무관하게 실패', () => {
  const v = verdict.judgeNaver({ ...ALL_TRUE, no_fabricated_experience: false },
    { structurePassed: true, structureIssues: [], searchOk: true });
  assert.equal(v.passed, false);
  assert.match(v.reason, /no_fabricated_experience/);
});

test('판정: 네이버 항목 누락은 실패로 본다', () => {
  const { has_unique_info, ...missing } = ALL_TRUE;
  const v = verdict.judgeNaver(missing, { structurePassed: true, structureIssues: [], searchOk: true });
  assert.equal(v.passed, false);
});

test('판정: 구조 검사 실패와 검색 0건이 사유에 남는다', () => {
  const v = verdict.judgeNaver(ALL_TRUE, {
    structurePassed: false, structureIssues: ['소제목(H2) 부족'], searchOk: false,
  });
  assert.equal(v.passed, false);
  assert.match(v.reason, /네이버 검색 결과 0건/);
  assert.match(v.reason, /소제목\(H2\) 부족/);
});

test('LLM JSON 파싱: 앞뒤 텍스트와 후행 쉼표를 견딘다', () => {
  const r = verdict.parseLlmJson('결과:\n{"quality_score": 80, "reason": "ok",}\n끝');
  assert.equal(r.quality_score, 80);
});

test('중복 검사: 두 탭 키워드와 비교한다', () => {
  const existing = ['노션 AI 사용법', 'MCP란'];
  assert.equal(dup.findDuplicate('노션 AI 사용법 정리', existing).is_duplicate, true);
  assert.equal(dup.findDuplicate('MCP란', existing).is_duplicate, true);
  assert.equal(dup.findDuplicate('RAG 쉽게', existing).is_duplicate, false);
});
