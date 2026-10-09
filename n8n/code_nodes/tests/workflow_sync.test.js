// 워크플로 JSON의 Code 노드 jsCode가 원본 .js와 같은지, 모두 문법이 맞는지 검사한다
// 티스토리(workflow_complete.json)는 동기화 스크립트가 없어 손으로 복사한다 — 어긋나면 여기서 잡는다.
// 네이버(workflow_naver.json)는 build_naver_workflow.py --check가 같은 역할을 한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const N8N = path.join(__dirname, '..', '..');
const CODE = path.join(N8N, 'code_nodes');

// 노드 이름 → 원본 파일 (code_nodes/ 기준)
const SOURCES = {
  'workflow_complete.json': {
    'Parse SERP Data': 'parse_serp.js',
    'Route Prompt (A/B/C)': 'route_prompt_workflow.js',
    'Build LLM Request (Content Gen)': 'build_llm_request.js',
    'Build LLM Request (Verify)': 'build_llm_request.js',
    'Normalize Response (Content Gen)': 'normalize_llm_response.js',
    'Normalize Response (Verify)': 'normalize_llm_response.js',
    'Parse JSON Response': 'parse_json.js',
    'Inject Images': 'inject_images.js',
    'Validate Structure': 'validate_structure.js',
    'URL Validation': 'validate_urls.js',
    'Code Block Lint': 'lint_code_blocks.js',
    'Build Verify Request': 'build_verify_request.js',
    'Parse Verification Result': 'parse_verification.js',
    'Check Duplicate': 'check_duplicate.js',
    'Fetch Official Docs': 'fetch_official_docs.js',
  },
};
// 원본 파일 없이 JSON에만 있는 한두 줄짜리 축약 노드
const INLINE_ONLY = new Set(['Reduce to Trigger', 'Reduce Brain Terms', 'Reduce Naver Published']);

function codeNodes(file) {
  const wf = JSON.parse(fs.readFileSync(path.join(N8N, file), 'utf8'));
  return wf.nodes.filter((n) => n.type === 'n8n-nodes-base.code');
}

for (const [file, sources] of Object.entries(SOURCES)) {
  test(`${file}: 모든 Code 노드에 원본이 있고 내용이 같다`, () => {
    for (const node of codeNodes(file)) {
      if (INLINE_ONLY.has(node.name)) continue;
      const src = sources[node.name];
      assert.ok(src, `원본 매핑 없음: ${node.name}`);
      const expected = fs.readFileSync(path.join(CODE, src), 'utf8').trimEnd();
      assert.equal(node.parameters.jsCode.trimEnd(), expected, `${node.name} ≠ code_nodes/${src}`);
    }
  });
}

for (const file of ['workflow_complete.json', 'workflow_naver.json']) {
  test(`${file}: 모든 jsCode가 n8n처럼 async 함수로 감쌌을 때 문법이 맞다`, () => {
    for (const node of codeNodes(file)) {
      assert.doesNotThrow(
        () => new vm.Script(`(async function () {\n${node.parameters.jsCode}\n})`),
        `${node.name} 문법 오류 (줄바꿈 이중 이스케이프 확인)`,
      );
    }
  });
}
