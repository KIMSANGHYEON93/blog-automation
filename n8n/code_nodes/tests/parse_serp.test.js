// Parse SERP Data — Google 중계 주소(/goto?url=…)를 실제 주소로 푸는 회귀 테스트
// 2026-10-30부터 SerpAPI organic link 대부분이 중계 경로로 와서 URL 풀·참고자료가 비었다
const test = require('node:test');
const assert = require('node:assert/strict');

const p = require('../parse_serp.js');

function redirectTo(location, statusCode = 302) {
  const calls = [];
  const request = async (opts) => {
    calls.push(opts);
    return { statusCode, headers: location ? { location } : {} };
  };
  return { request, calls };
}

test('실제 주소는 요청 없이 그대로 쓴다', async () => {
  const { request, calls } = redirectTo('https://x.example.org/');
  assert.equal(await p.resolveSerpLink('https://docs.aws.amazon.com/a', '', request),
    'https://docs.aws.amazon.com/a');
  assert.equal(calls.length, 0);
});

test('중계 주소는 Google의 302 Location으로 풀고, 리다이렉트를 따라가지 않는다', async () => {
  const { request, calls } = redirectTo('https://docs.aws.amazon.com/ko_kr/connect/latest/x');
  const out = await p.resolveSerpLink('/goto?url=CAES123',
    'https://docs.aws.amazon.com › latest › c', request);
  assert.equal(out, 'https://docs.aws.amazon.com/ko_kr/connect/latest/x');
  assert.equal(calls[0].url, 'https://www.google.com/goto?url=CAES123');
  assert.equal(calls[0].disableFollowRedirect, true);
});

test('표시 주소의 도메인과 다르면 버린다', async () => {
  const { request } = redirectTo('https://qiita.com/a/items/1');
  assert.equal(await p.resolveSerpLink('/goto?url=CAES1', 'https://trust.anthropic.com › sub', request), null);
});

test('표시 주소에 도메인이 없으면(댓글 수 등) 도착 주소를 쓴다', async () => {
  const { request } = redirectTo('https://www.reddit.com/r/x/comments/1');
  assert.equal(await p.resolveSerpLink('/goto?url=CAES1', '댓글 80개 이상', request),
    'https://www.reddit.com/r/x/comments/1');
});

test('리다이렉트가 아니거나, Google 자신·http 아닌 곳이면 버린다', async () => {
  for (const [loc, code] of [['https://x.example.org/', 200], ['https://www.google.com/sorry', 302],
    ['javascript:alert(1)', 302], ['', 302]]) {
    const { request } = redirectTo(loc, code);
    assert.equal(await p.resolveSerpLink('/goto?url=CAES1', '', request), null, `${loc} ${code}`);
  }
});

test('모르는 형식의 상대 경로와 요청 실패는 버린다', async () => {
  const { request, calls } = redirectTo('https://x.example.org/');
  assert.equal(await p.resolveSerpLink('/search?q=a', '', request), null);
  assert.equal(calls.length, 0);
  const failing = async () => { throw new Error('ETIMEDOUT'); };
  assert.equal(await p.resolveSerpLink('/goto?url=CAES1', '', failing), null);
});

test('URL 전역이 없는 n8n 샌드박스에서도 url 모듈로 동작한다', async () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const vm = require('node:vm');
  const src = fs.readFileSync(path.join(__dirname, '..', 'parse_serp.js'), 'utf8');
  const mod = { exports: {} };
  const ctx = vm.createContext({ console });
  const sandboxRequire = (name) => {
    if (name === 'url') return require('url');
    throw new Error(`Cannot find module '${name}'`);
  };
  vm.runInContext(`(function (module, require) {\n${src}\n})`, ctx)(mod, sandboxRequire);
  const { request } = redirectTo('https://inblog.ai/ko/glossary/guardrails');
  assert.equal(await mod.exports.resolveSerpLink('/goto?url=CAES1', 'https://inblog.ai › 용어집', request),
    'https://inblog.ai/ko/glossary/guardrails');
});
