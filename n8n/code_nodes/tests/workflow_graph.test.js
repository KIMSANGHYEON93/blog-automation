// 워크플로 연결 구조 검사
// n8n v1 실행 순서에서는 입력이 2개인 노드가 들어오는 갈래마다 한 번씩 실행된다.
// Build Verify Request가 URL Validation·Code Block Lint 두 곳에서 입력을 받아
// 글 1건에 검증 LLM 호출이 2번 나가고, 2번째 Sheets Update가 paired item 오류로
// 끝났다(2026-11-26 실행 191). Merge 노드가 아니면 들어오는 연결은 1개여야 한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const N8N = path.join(__dirname, '..', '..');
const MERGE_TYPES = new Set(['n8n-nodes-base.merge']);
// 스케줄·수동 트리거는 한 실행에 하나만 발화하므로 같은 노드로 들어와도 중복 실행이 아니다
const TRIGGER_TYPES = new Set(['n8n-nodes-base.scheduleTrigger', 'n8n-nodes-base.manualTrigger']);

function load(file) {
  return JSON.parse(fs.readFileSync(path.join(N8N, file), 'utf8'));
}

function incoming(wf) {
  const sources = {};
  for (const [src, outputs] of Object.entries(wf.connections)) {
    for (const branch of outputs.main || []) {
      for (const link of branch) {
        sources[link.node] = (sources[link.node] || []).concat(src);
      }
    }
  }
  return sources;
}

function next(wf, name) {
  const branches = (wf.connections[name] || {}).main || [];
  return branches.flat().map((l) => l.node);
}

for (const file of ['workflow_complete.json', 'workflow_naver.json']) {
  test(`${file}: Merge가 아닌 노드는 들어오는 연결이 1개뿐이다`, () => {
    const wf = load(file);
    const types = Object.fromEntries(wf.nodes.map((n) => [n.name, n.type]));
    for (const [node, all] of Object.entries(incoming(wf))) {
      if (MERGE_TYPES.has(types[node])) continue;
      const sources = all.filter((src) => !TRIGGER_TYPES.has(types[src]));
      assert.ok(sources.length <= 1, `${node} 입력 ${sources.length}개: ${sources.join(', ')}`);
    }
  });

  test(`${file}: 검사 노드는 직렬이다 (Validate Structure → URL Validation → Code Block Lint → Build Verify Request)`, () => {
    const wf = load(file);
    assert.deepEqual(next(wf, 'Validate Structure'), ['URL Validation']);
    assert.deepEqual(next(wf, 'URL Validation'), ['Code Block Lint']);
    assert.deepEqual(next(wf, 'Code Block Lint'), ['Build Verify Request']);
  });
}
