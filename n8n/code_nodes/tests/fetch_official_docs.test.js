// Fetch Official Docs — 공식 문서 허용 목록·수동 리다이렉트 회귀 테스트 (가짜 httpRequest만 사용)
const test = require('node:test');
const assert = require('node:assert/strict');

const f = require('../fetch_official_docs.js');

test('공식 문서 판별은 호스트·경로 접두로 한다 (문자열 포함 위장 거부)', () => {
  assert.equal(f.isOfficialDocUrl('https://docs.python.org/3/library/os.html'), true);
  assert.equal(f.isOfficialDocUrl('https://kubernetes.io/docs/concepts/'), true);
  assert.equal(f.isOfficialDocUrl('https://ko.learn.microsoft.com/a'), true);
  for (const url of [
    'https://evil.org/?u=docs.python.org', 'https://docs.python.org.evil.org/',
    'http://169.254.169.254/docs.python.org', 'https://kubernetes.io/blog/', 'https://kubernetes.io/docsx',
    'ftp://docs.python.org/', 'https://user:pw@docs.python.org/', 'not a url',
  ]) {
    assert.equal(f.isOfficialDocUrl(url), false, url);
  }
});

function fakeRequest(routes) {
  const calls = [];
  return {
    calls,
    request: async (opts) => {
      calls.push(opts);
      const r = routes[opts.url];
      if (!r) throw Object.assign(new Error('no route'), { code: 'ECONNREFUSED' });
      return { headers: {}, body: '', ...r };
    },
  };
}

test('공식 문서가 아닌 곳으로의 리다이렉트는 따라가지 않는다', async () => {
  const { request, calls } = fakeRequest({
    'https://docs.python.org/a': { statusCode: 302, headers: { location: 'http://10.0.0.1/' } },
  });
  assert.equal(await f.fetchDocHtml('https://docs.python.org/a', request), '');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].disableFollowRedirect, true);
});

test('공식 문서 안의 리다이렉트는 따라가 본문을 받는다', async () => {
  const { request } = fakeRequest({
    'https://docs.python.org/a': { statusCode: 301, headers: { location: '/b' } },
    'https://docs.python.org/b': { statusCode: 200, body: '<main>본문</main>' },
  });
  assert.equal(await f.fetchDocHtml('https://docs.python.org/a', request), '<main>본문</main>');
});

test('공식 문서가 아니면 요청하지 않고, 큰 응답은 자른다', async () => {
  const big = 'x'.repeat(f.MAX_HTML_CHARS + 100);
  const { request, calls } = fakeRequest({ 'https://docs.python.org/big': { statusCode: 200, body: big } });
  assert.equal(await f.fetchDocHtml('https://evil.org/?u=docs.python.org', request), '');
  assert.equal(calls.length, 0);
  assert.equal((await f.fetchDocHtml('https://docs.python.org/big', request)).length, f.MAX_HTML_CHARS);
});

// n8n Code 노드(vm2)에는 Node 전역 URL이 없다 — 전역에 기대면 모든 공식 문서가 '허용 목록 밖'이 됐다
test('URL 전역이 없는 n8n 샌드박스에서도 허용 목록 주소를 알아본다', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const vm = require('node:vm');
  const src = fs.readFileSync(path.join(__dirname, '..', 'fetch_official_docs.js'), 'utf8');
  const mod = { exports: {} };
  const ctx = vm.createContext({ setTimeout, clearTimeout, console });
  const sandboxRequire = (name) => {
    if (name === 'url') return require('url');
    throw new Error(`Cannot find module '${name}'`);
  };
  vm.runInContext(`(function (module, require) {\n${src}\n})`, ctx)(mod, sandboxRequire);
  assert.equal(mod.exports.isOfficialDocUrl('https://learn.microsoft.com/ko-kr/azure/'), true);
  assert.equal(mod.exports.isOfficialDocUrl('https://evil.org/?u=docs.python.org'), false);
});
