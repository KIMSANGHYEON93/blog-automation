// URL Validation 노드 — SSRF 차단·수동 리다이렉트·일시적 실패 링크 보존 회귀 테스트
// 네트워크는 쓰지 않는다: 가짜 httpRequest·가짜 DNS lookup만 쓴다
const test = require('node:test');
const assert = require('node:assert/strict');

const v = require('../validate_urls.js');

const PUBLIC_IP = '93.184.216.34';
const publicLookup = async () => [{ address: PUBLIC_IP, family: 4 }];

// routes: { 'METHOD url': {statusCode, headers} | Error }
function fakeRequest(routes) {
  const calls = [];
  const request = async (opts) => {
    calls.push(opts);
    const r = routes[`${opts.method} ${opts.url}`] ?? routes[opts.url];
    if (r === undefined) throw Object.assign(new Error('no route'), { code: 'ECONNREFUSED' });
    if (r instanceof Error) throw r;
    return { headers: {}, body: '', ...r };
  };
  return { request, calls };
}

test('공인 주소 판별: 내부·예약·메타데이터 대역은 거부', () => {
  for (const ip of ['127.0.0.1', '10.1.2.3', '172.16.0.1', '192.168.0.1', '169.254.169.254',
    '100.64.0.1', '0.0.0.0', '224.0.0.1', '255.255.255.255', '192.0.2.1', '198.18.0.1',
    '::1', '::', '::ffff:127.0.0.1', '::ffff:7f00:1', 'fe80::1', 'fc00::1', 'fd12:3456::1',
    'ff02::1', '64:ff9b::7f00:1', '2001:db8::1', '2002:7f00:1::1', '[::1]']) {
    assert.equal(v.isPublicIp(ip), false, ip);
  }
  for (const ip of ['8.8.8.8', PUBLIC_IP, '2606:4700::1111', '2a00:1450:4001::200e']) {
    assert.equal(v.isPublicIp(ip), true, ip);
  }
});

const INTERNAL_URLS = [
  'http://127.0.0.1/', 'http://10.0.0.1/admin', 'http://192.168.1.1/', 'http://172.20.0.2:5678/',
  'http://169.254.169.254/latest/meta-data/', 'http://[::1]/', 'http://[::ffff:127.0.0.1]/',
  'http://0.0.0.0/', 'http://2130706433/', 'http://0x7f.1/', 'http://017700000001/',
  'http://[fe80::1]/', 'http://[::]/',
];

for (const url of INTERNAL_URLS) {
  test(`내부 주소는 요청하지 않고 차단: ${url}`, async () => {
    const { request, calls } = fakeRequest({});
    const r = await v.checkUrl(url, { request, lookup: publicLookup });
    assert.equal(r.status, 'blocked');
    assert.equal(calls.length, 0);
  });
}

test('http/https 외 프로토콜과 계정 정보가 든 주소는 차단', async () => {
  const { request, calls } = fakeRequest({});
  for (const url of ['ftp://example.org/a', 'file:///etc/passwd', 'gopher://example.org/',
    'https://user:pw@example.org/']) {
    const r = await v.checkUrl(url, { request, lookup: publicLookup });
    assert.equal(r.status, 'blocked', url);
  }
  assert.equal(calls.length, 0);
});

test('DNS 결과 중 하나라도 내부 IP면 차단 (localhost·재바인딩용 호스트)', async () => {
  const { request, calls } = fakeRequest({});
  const lookup = async (host) => (host === 'localhost'
    ? [{ address: '127.0.0.1', family: 4 }]
    : [{ address: PUBLIC_IP, family: 4 }, { address: '10.0.0.5', family: 4 }]);
  assert.equal((await v.checkUrl('http://localhost:5678/', { request, lookup })).status, 'blocked');
  assert.equal((await v.checkUrl('https://rebind.example.org/', { request, lookup })).status, 'blocked');
  const v6 = async () => [{ address: '::ffff:169.254.169.254', family: 6 }];
  assert.equal((await v.checkUrl('https://v6.example.org/', { request, lookup: v6 })).status, 'blocked');
  assert.equal(calls.length, 0);
});

test('리다이렉트는 자동으로 따라가지 않고, 내부 주소로 넘어가면 차단', async () => {
  const { request, calls } = fakeRequest({
    'HEAD https://public.example.org/a': { statusCode: 302, headers: { location: 'http://169.254.169.254/latest' } },
  });
  const r = await v.checkUrl('https://public.example.org/a', { request, lookup: publicLookup });
  assert.equal(r.status, 'blocked');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].disableFollowRedirect, true);
  assert.equal(calls[0].ignoreHttpStatusErrors, true);
  assert.equal(calls[0].returnFullResponse, true);
});

test('공인 주소로의 리다이렉트는 단계마다 검사하며 따라간다', async () => {
  const { request, calls } = fakeRequest({
    'HEAD https://a.example.org/x': { statusCode: 301, headers: { location: '/y' } },
    'HEAD https://a.example.org/y': { statusCode: 200 },
  });
  const r = await v.checkUrl('https://a.example.org/x', { request, lookup: publicLookup });
  assert.equal(r.status, 'ok');
  assert.equal(calls.length, 2);
  assert.ok(calls.every((c) => c.disableFollowRedirect === true));
});

test('리다이렉트가 상한을 넘으면 확인 실패(링크 보존)', async () => {
  const routes = {};
  for (let i = 0; i < 10; i++) {
    routes[`HEAD https://loop.example.org/${i}`] = { statusCode: 302, headers: { location: `/${i + 1}` } };
  }
  const { request, calls } = fakeRequest(routes);
  const r = await v.checkUrl('https://loop.example.org/0', { request, lookup: publicLookup });
  assert.equal(r.status, 'unverified');
  assert.ok(calls.length <= v.LIMITS.MAX_REDIRECTS + 1);
});

test('상태 판정: 404·410만 없음, 403·429·5xx·타임아웃·네트워크 오류는 확인 실패', async () => {
  const timeout = Object.assign(new Error('timeout of 5000ms exceeded'), { code: 'ECONNABORTED' });
  const reset = Object.assign(new Error('socket hang up'), { code: 'ECONNRESET' });
  const cases = { 404: 'dead', 410: 'dead', 403: 'unverified', 429: 'unverified', 500: 'unverified' };
  for (const [code, expected] of Object.entries(cases)) {
    const url = `https://s.example.org/${code}`;
    const { request } = fakeRequest({ [`HEAD ${url}`]: { statusCode: Number(code) }, [`GET ${url}`]: { statusCode: Number(code) } });
    assert.equal((await v.checkUrl(url, { request, lookup: publicLookup })).status, expected, code);
  }
  for (const err of [timeout, reset]) {
    const { request } = fakeRequest({ 'https://s.example.org/e': err });
    assert.equal((await v.checkUrl('https://s.example.org/e', { request, lookup: publicLookup })).status, 'unverified');
  }
});

test('없는 도메인(ENOTFOUND)은 없음으로 본다', async () => {
  const { request, calls } = fakeRequest({});
  const lookup = async () => { throw Object.assign(new Error('getaddrinfo ENOTFOUND'), { code: 'ENOTFOUND' }); };
  const r = await v.checkUrl('https://no-such-domain.example.org/', { request, lookup });
  assert.equal(r.status, 'dead');
  assert.equal(calls.length, 0);
});

test('HEAD를 거부(405)하면 GET으로 다시 확인한다', async () => {
  const { request, calls } = fakeRequest({
    'HEAD https://h.example.org/': { statusCode: 405 },
    'GET https://h.example.org/': { statusCode: 200 },
  });
  const r = await v.checkUrl('https://h.example.org/', { request, lookup: publicLookup });
  assert.equal(r.status, 'ok');
  assert.equal(calls[1].method, 'GET');
  assert.equal(calls[1].disableFollowRedirect, true);
});

test('응답이 끝나지 않으면 URL별 시간 상한에서 확인 실패로 끝낸다', async () => {
  const request = () => new Promise(() => {});
  const r = await v.checkUrl('https://slow.example.org/', { request, lookup: publicLookup, deadlineMs: 30 });
  assert.equal(r.status, 'unverified');
});

test('dns 모듈을 못 쓰면 신뢰 도메인만 요청하고 나머지는 확인 실패로 남긴다', async () => {
  const { request, calls } = fakeRequest({ 'HEAD https://learn.microsoft.com/ko-kr/azure/': { statusCode: 200 } });
  const ok = await v.checkUrl('https://learn.microsoft.com/ko-kr/azure/', { request, lookup: null });
  const other = await v.checkUrl('https://random-blog.example.org/', { request, lookup: null });
  assert.equal(ok.status, 'ok');
  assert.equal(other.status, 'unverified');
  assert.equal(calls.length, 1);
  // 신뢰 도메인 판별은 접미사 위장에 속지 않는다
  assert.equal(v.isTrustedHost('learn.microsoft.com.evil.org'), false);
  assert.equal(v.isTrustedHost('evillearn.microsoft.com'), false);
});

test('일시적 실패 링크는 본문·references에 남고, 없음·차단 링크만 지운다', async () => {
  const content = [
    '[공식](https://ok.example.org/doc)',
    '[막힘](https://forbidden.example.org/doc)',
    '[없음](https://gone.example.org/doc)',
    '[내부](http://169.254.169.254/latest)',
  ].join('\n');
  const references = ['https://forbidden.example.org/doc', 'https://gone.example.org/doc', '책 이름'];
  const { request } = fakeRequest({
    'HEAD https://ok.example.org/doc': { statusCode: 200 },
    'https://forbidden.example.org/doc': { statusCode: 403 },
    'https://gone.example.org/doc': { statusCode: 404 },
  });
  const out = await v.validateUrls({ content, references, serpUrls: [] }, { request, lookup: publicLookup });
  assert.match(out.content, /\[공식\]\(https:\/\/ok\.example\.org\/doc\)/);
  assert.match(out.content, /\[막힘\]\(https:\/\/forbidden\.example\.org\/doc\)/);
  assert.doesNotMatch(out.content, /gone\.example\.org/);
  assert.doesNotMatch(out.content, /169\.254/);
  assert.deepEqual(out.references, ['https://forbidden.example.org/doc', '책 이름']);
  const uv = out.url_validation;
  assert.equal(uv.dead, 1);
  assert.equal(uv.blocked, 1);
  assert.equal(uv.unverified, 1);
  assert.equal(uv.needs_review, true);
  assert.deepEqual(uv.unverified_urls.map((u) => u.url), ['https://forbidden.example.org/doc']);
  assert.match(uv.unverified_urls[0].reason, /403/);
  assert.match(uv.summary, /^1\/4 \(dead:1/);
  assert.match(uv.summary, /확인실패:1/);
  assert.match(uv.summary, /forbidden\.example\.org/);
});

test('URL 개수 상한을 넘는 주소는 요청하지 않고 확인 실패로 남긴다', async () => {
  const urls = Array.from({ length: v.LIMITS.MAX_URLS + 5 }, (_, i) => `https://n${i}.example.org/`);
  const routes = Object.fromEntries(urls.map((u) => [u, { statusCode: 200 }]));
  const { request, calls } = fakeRequest(routes);
  const out = await v.validateUrls({ content: urls.join('\n'), references: [], serpUrls: [] },
    { request, lookup: publicLookup });
  assert.equal(calls.length, v.LIMITS.MAX_URLS);
  assert.equal(out.url_validation.unverified, 5);
  assert.equal(out.url_validation.total_urls, urls.length);
});

// n8n Code 노드(vm2)에는 Node 전역 URL이 없다 — 2026-10-16~29 실행 기록에서 모든 URL이
// '형식 오류'로 판정돼 본문 링크·참고자료가 전부 지워졌다. 같은 조건(vm 컨텍스트)에서 돌려 본다.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadInSandbox(allowedModules) {
  const src = fs.readFileSync(path.join(__dirname, '..', 'validate_urls.js'), 'utf8');
  const mod = { exports: {} };
  const ctx = vm.createContext({ setTimeout, clearTimeout, console });
  const sandboxRequire = (name) => {
    if (allowedModules.includes(name)) return require(name);
    throw new Error(`Cannot find module '${name}'`);
  };
  vm.runInContext(`(function (module, require) {\n${src}\n})`, ctx)(mod, sandboxRequire);
  return mod.exports;
}

test('URL 전역이 없는 n8n 샌드박스에서도 url 모듈로 주소를 확인한다', async () => {
  const sv = loadInSandbox(['url', 'dns']);
  const { request } = fakeRequest({ 'https://ok.example.org/doc': { statusCode: 200 } });
  const r = await sv.checkUrl('https://ok.example.org/doc', { request, lookup: publicLookup });
  assert.equal(r.status, 'ok');
});

test('url 모듈도 못 쓰면 링크를 지우지 않고 확인 실패로 남긴다', async () => {
  const sv = loadInSandbox([]);
  const { request, calls } = fakeRequest({});
  const out = await sv.validateUrls({
    content: '설명 [공식](https://ok.example.org/doc)',
    references: ['https://ok.example.org/doc'],
    serpUrls: [],
  }, { request, lookup: publicLookup });
  assert.match(out.content, /\[공식\]\(https:\/\/ok\.example\.org\/doc\)/);
  assert.equal(out.references.length, 1);
  assert.equal(out.url_validation.dead, 0);
  assert.equal(out.url_validation.unverified, 1);
  assert.equal(calls.length, 0);
});

test('없는 주소의 링크를 지워도 이미지 문법은 깨뜨리지 않는다', async () => {
  const { request } = fakeRequest({
    'https://gone.example.org/a.png': { statusCode: 404 },
    'https://gone.example.org/page': { statusCode: 404 },
  });
  const content = '![그림](https://gone.example.org/a.png)\n[글](https://gone.example.org/page)';
  const out = await v.validateUrls({ content, references: [], serpUrls: [] },
    { request, lookup: publicLookup });
  assert.match(out.content, /!\[그림\]\(https:\/\/gone\.example\.org\/a\.png\)/);
  assert.match(out.content, /^글$/m);
});

test('남은 참고자료를 글 끝 "참고 자료"에 검색 결과 제목(없으면 도메인)으로 붙인다', async () => {
  const { request } = fakeRequest({
    'https://ok.example.org/doc': { statusCode: 200 },
    'https://www.forbidden.example.org/x': { statusCode: 403 },
    'https://gone.example.org/y': { statusCode: 404 },
  });
  const out = await v.validateUrls({
    content: '본문입니다.',
    references: ['https://ok.example.org/doc', 'https://www.forbidden.example.org/x',
      'https://gone.example.org/y', '책 이름'],
    serpUrls: [],
    titles: { 'https://ok.example.org/doc': '공식 문서 [가이드]' },
  }, { request, lookup: publicLookup });
  assert.equal(out.content, [
    '본문입니다.',
    '',
    '## 참고 자료',
    '',
    '- [공식 문서 가이드](https://ok.example.org/doc)',
    '- [forbidden.example.org](https://www.forbidden.example.org/x)',
    '',
  ].join('\n'));
});

test('참고자료가 없거나 이미 "참고 자료" 절이 있으면 붙이지 않는다', async () => {
  const { request } = fakeRequest({ 'https://ok.example.org/doc': { statusCode: 200 } });
  const deps = { request, lookup: publicLookup };
  const none = await v.validateUrls({ content: '본문', references: [], serpUrls: [] }, deps);
  assert.equal(none.content, '본문');
  const existing = '본문\n\n## 참고 자료\n\n- 직접 쓴 목록';
  const kept = await v.validateUrls(
    { content: existing, references: ['https://ok.example.org/doc'], serpUrls: [] }, deps);
  assert.equal(kept.content, existing);
});

test('검색 결과 텍스트에서 주소별 제목을 뽑는다', () => {
  const serpText = [
    '### 검색 상위 콘텐츠 (상위 7개)',
    '1. 제목A — 사이트',
    '   스니펫입니다',
    '   URL: https://a.example.org/x',
    '2. 제목B',
    '   (스니펫 없음)',
    '   URL: https://b.example.org/',
  ].join('\n');
  assert.deepEqual({ ...v.serpTitles(serpText) }, {
    'https://a.example.org/x': '제목A — 사이트',
    'https://b.example.org/': '제목B',
  });
});
