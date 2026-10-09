/**
 * Node 7a: URL 검증 — 안전한 주소만 HTTP로 확인 + SERP 교차 대조 + 없는 URL 제거
 * Mode: runOnceForEachItem
 *
 * 주의: serp_urls는 Normalize Response/Parse JSON에서 소실되므로
 *       $('Parse SERP Data') 노드에서 직접 참조한다.
 *
 * 보안(SSRF): 본문·references의 URL은 LLM이 만든 것이라(검색 결과 프롬프트 주입 포함) 내부망 주소가 섞일 수 있다.
 * - http/https만, 계정 정보(user:pw@) 거부
 * - IP 주소(10진·8진·16진 표기는 WHATWG URL이 점 네 개 표기로 바꿔 준다)와 DNS 해석 결과 전부가
 *   공인 주소일 때만 요청한다. 루프백·사설·링크로컬(169.254.169.254 메타데이터)·CGNAT·멀티캐스트·예약·
 *   IPv4-mapped/NAT64/6to4 IPv6는 거부
 * - 리다이렉트는 자동으로 따라가지 않고(disableFollowRedirect) Location을 같은 검사에 다시 넣는다
 * - dns 모듈은 n8n 환경변수 NODE_FUNCTION_ALLOW_BUILTIN에 dns가 있어야 쓸 수 있다.
 *   못 쓰면 TRUSTED_DOMAINS만 요청하고 나머지는 '확인 실패'로 남긴다(링크 보존)
 * 한계: 검사와 실제 접속 사이에 DNS 응답이 바뀌면(DNS 재바인딩) 막지 못한다 —
 *       this.helpers.httpRequest에 검사한 IP를 고정해 넘길 방법이 없다.
 *
 * 판정: 404·410·없는 도메인(ENOTFOUND)만 'dead'(링크 제거), 내부 주소는 'blocked'(링크 제거).
 *       타임아웃·403·429·5xx·네트워크 오류·상한 초과는 'unverified'(확인 실패 — 링크 보존,
 *       url_validation.unverified_urls와 시트 URL검증 칸에 남겨 재검증·관리자 검수에 쓴다)
 */

const LIMITS = {
  MAX_URLS: 20,             // 글 하나에서 요청하는 URL 수 상한
  MAX_REDIRECTS: 3,
  REQUEST_TIMEOUT_MS: 5000, // 요청 1회
  URL_DEADLINE_MS: 15000,   // URL 하나(리다이렉트·GET 재시도 포함) 전체
  MAX_BODY_BYTES: 1024,     // GET 확인은 앞부분만 (Range 헤더)
  BATCH: 5,
};

// dns 모듈을 못 쓸 때만 쓰는 신뢰 도메인 (parse_serp.js OFFICIAL_DOMAINS의 호스트)
const TRUSTED_DOMAINS = [
  'learn.microsoft.com', 'docs.microsoft.com', 'docs.aws.amazon.com', 'cloud.google.com',
  'developer.mozilla.org', 'docs.docker.com', 'kubernetes.io', 'docs.github.com',
  'developer.hashicorp.com', 'docs.ansible.com', 'docs.oracle.com', 'docs.redhat.com',
  'wiki.archlinux.org', 'man7.org', 'nginx.org', 'docs.python.org', 'go.dev',
  'docs.anthropic.com', 'platform.openai.com',
];

function parseIPv4(s) {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(s);
  if (!m) return null;
  const o = m.slice(1).map(Number);
  return o.every((n) => n <= 255) ? o : null;
}

function parseIPv6(s) {
  let str = String(s).replace(/^\[|\]$/g, '');
  if (!str.includes(':') || str.includes('%')) return null;
  const v4 = /^(.*:)(\d+\.\d+\.\d+\.\d+)$/.exec(str);
  if (v4) {
    const o = parseIPv4(v4[2]);
    if (!o) return null;
    str = `${v4[1]}${((o[0] << 8) | o[1]).toString(16)}:${((o[2] << 8) | o[3]).toString(16)}`;
  }
  const halves = str.split('::');
  if (halves.length > 2) return null;
  const groups = (p) => (p === '' ? [] : p.split(':'));
  const head = groups(halves[0]);
  const tail = halves.length === 2 ? groups(halves[1]) : [];
  const fill = 8 - head.length - tail.length;
  if (halves.length === 2 ? fill < 1 : fill !== 0) return null;
  const all = [...head, ...Array(halves.length === 2 ? fill : 0).fill('0'), ...tail];
  if (all.some((g) => !/^[0-9a-f]{1,4}$/i.test(g))) return null;
  return all.map((g) => parseInt(g, 16));
}

function isBlockedIPv4([a, b, c]) {
  return a === 0 || a === 10 || a === 127 || a >= 224          // this-network, 사설, 루프백, 멀티캐스트·예약
    || (a === 100 && b >= 64 && b <= 127)                        // CGNAT
    || (a === 169 && b === 254)                                  // 링크로컬·클라우드 메타데이터
    || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
    || (a === 192 && b === 0 && (c === 0 || c === 2))            // IETF·문서용
    || (a === 192 && b === 88 && c === 99)                       // 6to4 relay
    || (a === 198 && (b === 18 || b === 19))                     // 벤치마크
    || (a === 198 && b === 51 && c === 100) || (a === 203 && b === 0 && c === 113);
}

// 전역 유니캐스트(2000::/3)만 허용 — ::1, ::, IPv4-mapped, NAT64(64:ff9b::), fc00::/7, fe80::/10, ff00::/8은 밖에 있다
function isPublicIPv6(g) {
  if (g[0] < 0x2000 || g[0] > 0x3fff) return false;
  if (g[0] === 0x2001 && g[1] < 0x0200) return false;           // 2001::/23 (Teredo 등)
  if (g[0] === 0x2001 && g[1] === 0x0db8) return false;         // 문서용
  if (g[0] === 0x2002) return false;                            // 6to4 (IPv4 내장)
  return !(g[0] === 0x3fff && g[1] < 0x1000);                   // 3fff::/20 문서용
}

function isPublicIp(s) {
  const v4 = parseIPv4(s);
  if (v4) return !isBlockedIPv4(v4);
  const v6 = parseIPv6(s);
  return v6 ? isPublicIPv6(v6) : false;
}

function isTrustedHost(host) {
  const h = String(host).toLowerCase().replace(/\.$/, '');
  return TRUSTED_DOMAINS.some((d) => h === d || h.endsWith(`.${d}`));
}

function parseSafeUrl(raw) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    return { status: 'broken_format', reason: 'URL 형식 오류' };
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return { status: 'blocked', reason: `허용하지 않는 프로토콜 ${u.protocol}` };
  if (u.username || u.password) return { status: 'blocked', reason: '계정 정보가 든 URL' };
  if (!u.hostname) return { status: 'broken_format', reason: '호스트 없음' };
  return { url: u };
}

async function resolveHost(hostname, lookup) {
  const host = hostname.replace(/^\[|\]$/g, '').replace(/\.$/, '').toLowerCase();
  if (parseIPv4(host) || parseIPv6(host)) {
    return isPublicIp(host) ? { status: 'ok' } : { status: 'blocked', reason: `내부·예약 주소 ${host}` };
  }
  if (host === 'localhost' || host.endsWith('.localhost')) return { status: 'blocked', reason: 'localhost' };
  if (!lookup) {
    return isTrustedHost(host)
      ? { status: 'ok' }
      : { status: 'unverified', reason: 'DNS 확인 불가(n8n dns 모듈 미허용) — 신뢰 도메인 아님' };
  }
  let addrs;
  try {
    addrs = await lookup(host, { all: true, verbatim: true });
  } catch (e) {
    if (e && e.code === 'ENOTFOUND') return { status: 'dead', reason: 'DNS에 없는 도메인' };
    return { status: 'unverified', reason: `DNS 오류 ${(e && e.code) || ''}`.trim() };
  }
  if (!Array.isArray(addrs) || addrs.length === 0) return { status: 'unverified', reason: 'DNS 응답 없음' };
  const bad = addrs.find((a) => !isPublicIp(a && a.address));
  return bad ? { status: 'blocked', reason: `내부 주소로 해석됨 ${bad && bad.address}` } : { status: 'ok' };
}

function headerValue(headers, name) {
  if (!headers) return undefined;
  const key = Object.keys(headers).find((k) => k.toLowerCase() === name);
  return key ? headers[key] : undefined;
}

async function requestOnce(url, method, request) {
  const opts = {
    method, url,
    timeout: LIMITS.REQUEST_TIMEOUT_MS,
    disableFollowRedirect: true,
    ignoreHttpStatusErrors: true,
    returnFullResponse: true,
    headers: { 'User-Agent': 'Mozilla/5.0 (compatible; BlogBot/1.0)' },
  };
  if (method === 'GET') {
    opts.headers.Range = `bytes=0-${LIMITS.MAX_BODY_BYTES - 1}`;
    opts.maxContentLength = LIMITS.MAX_BODY_BYTES;
  }
  try {
    const res = await request(opts);
    return { code: Number(res.statusCode ?? res.status), location: headerValue(res.headers, 'location') };
  } catch (e) {
    const resp = e && e.response;
    const code = (resp && (resp.status ?? resp.statusCode)) ?? (e && (e.httpCode ?? e.statusCode));
    if (code) return { code: Number(code), location: headerValue(resp && resp.headers, 'location') };
    return { error: (e && (e.code || e.message)) || '알 수 없는 오류' };
  }
}

const isRedirect = (c) => c >= 300 && c < 400;
const isSettled = (c) => (c >= 200 && c < 400) || c === 404 || c === 410;

function classify(res) {
  if (res.error) return { status: 'unverified', reason: `접속 실패(${res.error})` };
  if (res.code >= 200 && res.code < 300) return { status: 'ok' };
  if (res.code === 404 || res.code === 410) return { status: 'dead', reason: `HTTP ${res.code}` };
  return { status: 'unverified', reason: `HTTP ${res.code}` };
}

async function followAndCheck(raw, { request, lookup }) {
  let current = raw;
  for (let hop = 0; hop <= LIMITS.MAX_REDIRECTS; hop++) {
    const parsed = parseSafeUrl(current);
    if (parsed.status) return parsed;
    const dns = await resolveHost(parsed.url.hostname, lookup);
    if (dns.status !== 'ok') return dns;
    let res = await requestOnce(current, 'HEAD', request);
    // HEAD를 거부·실패하는 서버가 있어 GET으로 한 번 더 본다
    if (!res.code || !isSettled(res.code)) res = await requestOnce(current, 'GET', request);
    if (res.code && isRedirect(res.code)) {
      if (!res.location) return { status: 'unverified', reason: `HTTP ${res.code} (Location 없음)` };
      try {
        current = new URL(String(res.location), current).href;
      } catch {
        return { status: 'unverified', reason: '잘못된 리다이렉트 주소' };
      }
      continue;
    }
    return classify(res);
  }
  return { status: 'unverified', reason: `리다이렉트 ${LIMITS.MAX_REDIRECTS}회 초과` };
}

async function checkUrl(url, deps) {
  if (url.includes('...') || url.includes(' ')) return { url, status: 'broken_format', reason: 'URL 형식 오류' };
  if (url.includes('contoso.com') || url.includes('example.com')) return { url, status: 'placeholder' };
  const deadlineMs = deps.deadlineMs ?? LIMITS.URL_DEADLINE_MS;
  let timer;
  const deadline = new Promise((resolve) => {
    timer = setTimeout(() => resolve({ status: 'unverified', reason: `시간 상한 ${deadlineMs}ms 초과` }), deadlineMs);
  });
  try {
    const r = await Promise.race([followAndCheck(url, deps), deadline]);
    return { url, ...r };
  } finally {
    clearTimeout(timer);
  }
}

function stripLinks(content, urls) {
  let out = content;
  for (const url of urls) {
    const escaped = url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out.replace(new RegExp(`\\[([^\\]]+)\\]\\(${escaped}\\)`, 'g'), '$1'); // [텍스트](url) → 텍스트
  }
  return out;
}

async function validateUrls({ content, references, serpUrls }, deps) {
  const refs = Array.isArray(references) ? references : [];
  const urlRegex = /https?:\/\/[^\s\)\]"'<>]+/g;
  const contentUrls = (content.match(urlRegex) || []).map((u) => u.replace(/[.,;:!?)]+$/, ''));
  const allUrls = [...new Set([
    ...contentUrls,
    ...refs.filter((r) => typeof r === 'string' && r.startsWith('http')),
  ])];

  const serpDomains = new Set();
  for (const url of serpUrls || []) {
    try { serpDomains.add(new URL(url).hostname); } catch { /* 무시 */ }
  }

  const results = [];
  const toCheck = allUrls.slice(0, LIMITS.MAX_URLS);
  for (let i = 0; i < toCheck.length; i += LIMITS.BATCH) {
    results.push(...await Promise.all(toCheck.slice(i, i + LIMITS.BATCH).map((u) => checkUrl(u, deps))));
  }
  for (const url of allUrls.slice(LIMITS.MAX_URLS)) {
    results.push({ url, status: 'unverified', reason: `URL ${LIMITS.MAX_URLS}개 상한 초과 — 확인 안 함` });
  }

  const issues = [];
  const deadUrls = [];
  const blockedUrls = [];
  const unverified = [];
  let serpMatched = 0;
  let serpUnmatched = 0;
  for (const r of results) {
    if (r.status === 'placeholder') continue;
    if (r.status === 'broken_format' || r.status === 'dead') {
      issues.push(`접근 불가: ${r.url}`);
      deadUrls.push(r.url);
    } else if (r.status === 'blocked') {
      issues.push(`차단(내부·허용 안 됨): ${r.url} — ${r.reason}`);
      blockedUrls.push(r.url);
    } else if (r.status === 'unverified') {
      issues.push(`확인 실패(일시적, 링크 유지): ${r.url} — ${r.reason}`);
      unverified.push({ url: r.url, reason: r.reason });
    }
    try {
      if (serpDomains.has(new URL(r.url).hostname)) serpMatched++;
      else serpUnmatched++;
    } catch { /* 무시 */ }
  }

  const removed = [...deadUrls, ...blockedUrls];
  const reachable = results.filter((r) => r.status === 'ok').length;
  let summary = `${reachable}/${allUrls.length} (dead:${deadUrls.length}`;
  if (unverified.length) summary += `, 확인실패:${unverified.length}`;
  if (blockedUrls.length) summary += `, 차단:${blockedUrls.length}`;
  summary += ')';
  if (unverified.length) summary += ` 확인실패 URL: ${unverified.map((u) => u.url).join(' ')}`;

  return {
    content: stripLinks(content, removed),
    references: refs.filter((ref) => !(typeof ref === 'string' && ref.startsWith('http') && removed.includes(ref))),
    url_validation: {
      passed: removed.length === 0,
      needs_review: unverified.length > 0,
      total_urls: allUrls.length,
      reachable,
      dead: deadUrls.length,
      blocked: blockedUrls.length,
      unverified: unverified.length,
      unverified_urls: unverified,
      serp_matched: serpMatched,
      serp_unmatched: serpUnmatched,
      issues,
      summary,
    },
  };
}

if (typeof $input === 'undefined') {
  module.exports = { LIMITS, TRUSTED_DOMAINS, isPublicIp, isTrustedHost, checkUrl, validateUrls };
  return;
}

let lookup = null;
try {
  const dns = require('dns');
  lookup = (host, opts) => dns.promises.lookup(host, opts);
} catch {
  // NODE_FUNCTION_ALLOW_BUILTIN에 dns가 없으면 신뢰 도메인만 확인한다 (docs/N8N_SECURITY.md)
}

const helpers = this.helpers;
const item = $input.item.json;
let serpUrls = [];
try {
  serpUrls = $('Parse SERP Data').item.json.serp_urls || [];
} catch { /* 노드 미존재 시 빈 배열 */ }

return validateUrls(
  { content: item.content || '', references: item.references || [], serpUrls },
  { request: (opts) => helpers.httpRequest(opts), lookup },
).then((result) => ({ json: { ...item, ...result } }));
