# URL 참조 검증 및 공식 링크 강화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 콘텐츠 생성 시 LLM이 할루시네이션한 가짜 URL 대신 SERP에서 검증된 실제 공식 링크를 사용하고, 모든 URL을 HTTP로 실시간 검증하여 깨진 링크가 발행되지 않도록 한다.

**Architecture:** parse_serp.js에서 SERP URL 풀을 별도 배열로 추출 → 프롬프트에 "SERP URL만 사용" 규칙 추가 → validate_urls.js에서 `$()` 표현식으로 serp_urls 직접 참조 + HTTP 검증 + SERP 교차 대조 → 죽은 URL 자동 제거 → Sheets Write 노드가 검증된 content/references를 읽도록 수정

**Tech Stack:** n8n Code Node (JavaScript), `this.helpers.httpRequest()` (n8n 내장 HTTP 클라이언트, axios 기반)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `n8n/code_nodes/parse_serp.js` | Modify | SERP URL 풀 (`serp_urls`) 배열 추출 추가 |
| `n8n/code_nodes/route_prompt.js` | Modify | user_message에 `serp_urls` 목록 섹션 추가 |
| `n8n/prompts/prompt_a_terminology.md` | Modify | 참조 URL 규칙 섹션 추가 |
| `n8n/prompts/prompt_b_comparison.md` | Modify | 참조 URL 규칙 섹션 추가 |
| `n8n/prompts/prompt_c_troubleshooting.md` | Modify | 참조 URL 규칙 섹션 추가 |
| `n8n/code_nodes/validate_urls.js` | Rewrite | HTTP 검증 + SERP 교차 대조 + 죽은 URL 제거 |
| `n8n/workflow_complete.json` | Modify | Sheets Write 노드가 URL Validation 출력을 참조하도록 수정 |

### 데이터 흐름 (주의사항)

`serp_urls`는 파이프라인 중간에 소실됨 (`Normalize Response` → `Parse JSON` 에서 LLM 응답만 반환하고 나머지 데이터 삭제). 따라서 `validate_urls.js`에서는 n8n `$()` 표현식으로 `Parse SERP Data` 노드의 출력을 직접 참조해야 함:

```
Parse SERP Data → (serp_urls 생성)
       ↓                    ↘
Route Prompt → ... → URL Validation ← $('Parse SERP Data').item.json.serp_urls
```

또한, 현재 Sheets Write 노드는 `Parse JSON Response`에서 references를, `Inject Images`에서 content를 읽고 있음. URL Validation의 정제 결과가 실제로 반영되려면 Sheets Write의 참조 경로를 수정해야 함.

---

### Task 1: SERP URL 풀 추출

**Files:**
- Modify: `n8n/code_nodes/parse_serp.js:10-16,66-77`

- [ ] **Step 1: parse_serp.js에 serp_urls 배열 추출 추가**

organic_results에서 URL만 별도 배열로 추출하여 downstream 노드에 전달:

```javascript
// Line 10-16 영역, organicText 생성 직후에 추가
const serpUrls = [];
if (serpResults.organic_results && serpResults.organic_results.length > 0) {
  const top7 = serpResults.organic_results.slice(0, 7);
  // ... (기존 organicText 생성 코드 유지) ...
  for (const r of top7) {
    if (r.link) serpUrls.push(r.link);
  }
}

// Knowledge Graph 출처 URL도 추가
if (serpResults.knowledge_graph && serpResults.knowledge_graph.source) {
  const kgLink = serpResults.knowledge_graph.source.link;
  if (kgLink) serpUrls.push(kgLink);
}
```

return 객체에 `serp_urls` 필드 추가:

```javascript
return {
  json: {
    ...sheetData,
    serp_text: serpText,
    serp_urls: serpUrls,                    // NEW
    serp_organic_count: /* ... 기존 유지 */,
    serp_paa_count: /* ... 기존 유지 */,
    serp_related_count: /* ... 기존 유지 */,
    serp_has_kg: /* ... 기존 유지 */,
  }
};
```

- [ ] **Step 2: 수동 테스트 — n8n 에디터에서 Parse SERP Data 노드 실행**

n8n 에디터 > Parse SERP Data 노드 > Test step 실행
Expected: 출력 JSON에 `serp_urls` 배열이 포함되고, 각 항목이 유효한 URL 문자열

- [ ] **Step 3: Commit**

```bash
git add n8n/code_nodes/parse_serp.js
git commit -m "feat(n8n): extract serp_urls array from organic results"
```

---

### Task 2: 프롬프트에 참조 URL 규칙 추가

**Files:**
- Modify: `n8n/prompts/prompt_a_terminology.md:28-35`
- Modify: `n8n/prompts/prompt_b_comparison.md:28-35`
- Modify: `n8n/prompts/prompt_c_troubleshooting.md:27-34`

- [ ] **Step 1: 3개 프롬프트의 "SERP 데이터 활용 지침" 섹션에 참조 URL 규칙 추가**

기존 각 프롬프트의 "SERP 데이터 활용 지침" 마지막 줄:
```markdown
- 유용한 정보는 '[출처명](URL)' 형태로 인라인 출처를 삽입하세요
```

해당 줄을 아래 블록으로 **교체**:

```markdown
- 인라인 출처는 '[출처명](URL)' 형태로 삽입하세요

## 참조 URL 규칙 (필수)

- **references 필드**: 반드시 SERP 데이터에 포함된 실제 URL만 사용하세요. URL을 추측하거나 기억에 의존하여 작성하지 마세요
- **인라인 출처 URL**: SERP 데이터의 "URL:" 항목에서 가져오세요. user 메시지의 "참조 가능 URL 풀" 섹션 참고
- **공식 문서 우선**: SERP URL 중 공식 문서 도메인(learn.microsoft.com, docs.aws.amazon.com, cloud.google.com, developer.mozilla.org 등)이 있으면 우선 사용하세요
- **URL을 모를 때**: URL 없이 출처명만 텍스트로 기재하세요 (예: "Microsoft Learn 공식 문서 참고"). 존재하지 않는 URL을 만들어내지 마세요
```

- [ ] **Step 2: 각 프롬프트의 품질 체크리스트에 URL 검증 항목 추가**

기존 체크리스트 끝에 추가:

```markdown
- [ ] references 필드의 모든 URL이 SERP 데이터에서 가져온 것인가?
- [ ] 인라인 출처 URL이 실제 존재하는 URL인가? (추측 URL 사용 금지)
```

- [ ] **Step 3: Commit**

```bash
git add n8n/prompts/prompt_a_terminology.md n8n/prompts/prompt_b_comparison.md n8n/prompts/prompt_c_troubleshooting.md
git commit -m "feat(n8n): enforce SERP-sourced URLs in all prompts"
```

---

### Task 3: user_message에 SERP URL 풀 전달

**Files:**
- Modify: `n8n/code_nodes/route_prompt.js:32-41`

- [ ] **Step 1: route_prompt.js의 user_message 포맷 수정**

기존 (line 32-41):
```javascript
return {
  json: {
    keyword,
    category,
    row_index: rowIndex,
    prompt_type: promptType,
    system_prompt: systemPrompt,
    user_message: `키워드: ${keyword}\n\n## SERP 인텔리전스\n${serpText}`,
  }
};
```

변경:
```javascript
// SERP URL 풀 구성
const serpUrls = $input.item.json.serp_urls || [];
const urlPoolText = serpUrls.length > 0
  ? serpUrls.map((url, i) => `${i + 1}. ${url}`).join('\n')
  : '(SERP URL 없음)';

return {
  json: {
    keyword,
    category,
    row_index: rowIndex,
    prompt_type: promptType,
    system_prompt: systemPrompt,
    user_message: `키워드: ${keyword}\n\n## SERP 인텔리전스\n${serpText}\n\n## 참조 가능 URL 풀\n아래 URL만 references와 인라인 출처에 사용하세요:\n${urlPoolText}`,
  }
};
```

- [ ] **Step 2: n8n 에디터에서 Route Prompt 노드 실행 확인**

Expected: user_message 끝에 "## 참조 가능 URL 풀" 섹션과 번호 매긴 URL 목록 포함

- [ ] **Step 3: Commit**

```bash
git add n8n/code_nodes/route_prompt.js
git commit -m "feat(n8n): pass serp_urls pool in user_message for LLM"
```

---

### Task 4: HTTP URL 검증 + SERP 교차 대조

**Files:**
- Rewrite: `n8n/code_nodes/validate_urls.js`

**핵심 설계 결정:**
1. `serp_urls`는 파이프라인 중간에서 소실되므로 `$('Parse SERP Data').item.json.serp_urls`로 직접 참조
2. `this.helpers.httpRequest()`는 axios 기반이므로 `resolveWithFullResponse` 대신 try/catch 패턴 사용 (성공 = 2xx, 예외 = 접근 불가)
3. GET 폴백 시 `maxContentLength`로 다운로드 크기 제한

- [ ] **Step 1: validate_urls.js 전체 교체**

```javascript
/**
 * Node 7a: URL 검증 — HTTP HEAD + SERP 교차 대조 + 죽은 URL 자동 제거
 * Mode: runOnceForEachItem
 *
 * 주의: serp_urls는 Normalize Response/Parse JSON에서 소실되므로
 *       $('Parse SERP Data') 노드에서 직접 참조한다.
 */

const helpers = this.helpers;
const item = $input.item.json;
const content = item.content || '';
const references = item.references || [];

// serp_urls는 파이프라인 중간에서 소실 → Parse SERP Data 노드에서 직접 참조
let serpUrls = [];
try {
  serpUrls = $('Parse SERP Data').item.json.serp_urls || [];
} catch { /* 노드 미존재 시 빈 배열 */ }

// URL 추출 (trailing punctuation 제거)
const urlRegex = /https?:\/\/[^\s\)\]"'<>]+/g;
const rawUrls = content.match(urlRegex) || [];
const contentUrls = rawUrls.map(u => u.replace(/[.,;:!?)]+$/, ''));

// 모든 고유 URL 수집 (content + references)
const allUrls = [...new Set([
  ...contentUrls,
  ...references.filter(r => r.startsWith('http')),
])];

const issues = [];
const deadUrls = [];
const serpMatched = [];
const serpUnmatched = [];

// SERP 도메인 추출 (교차 대조용)
const serpDomains = new Set();
for (const url of serpUrls) {
  try { serpDomains.add(new URL(url).hostname); } catch {}
}

/**
 * HTTP 검증 — try/catch 패턴 (axios 기반)
 * 성공(2xx) = 반환값 존재, 실패(4xx/5xx/타임아웃) = 예외 발생
 */
async function checkUrl(url) {
  // 형식 검증 (HTTP 스킵)
  if (url.includes('...') || url.includes(' ')) {
    return { url, status: 'broken_format' };
  }
  if (url.includes('contoso.com') || url.includes('example.com')) {
    return { url, status: 'placeholder' };
  }

  // HEAD 시도
  try {
    await helpers.httpRequest({
      method: 'HEAD',
      url: url,
      timeout: 5000,
      ignoreHttpStatusErrors: false,
    });
    return { url, status: 'ok' };
  } catch {
    // HEAD 실패 → GET 폴백 (일부 서버 HEAD 거부)
    try {
      await helpers.httpRequest({
        method: 'GET',
        url: url,
        timeout: 5000,
        ignoreHttpStatusErrors: false,
        maxContentLength: 1024,
      });
      return { url, status: 'ok' };
    } catch {
      return { url, status: 'dead' };
    }
  }
}

// 병렬 검증 (배치 5개)
const results = [];
for (let i = 0; i < allUrls.length; i += 5) {
  const batch = allUrls.slice(i, i + 5);
  const batchResults = await Promise.all(batch.map(checkUrl));
  results.push(...batchResults);
}

// 결과 분류
for (const r of results) {
  if (r.status === 'placeholder') continue;

  if (r.status === 'broken_format' || r.status === 'dead') {
    issues.push(`접근 불가: ${r.url}`);
    deadUrls.push(r.url);
  }

  // SERP 교차 대조
  try {
    const domain = new URL(r.url).hostname;
    if (serpDomains.has(domain)) {
      serpMatched.push(r.url);
    } else {
      serpUnmatched.push(r.url);
    }
  } catch {}
}

// 죽은 URL 제거: [텍스트](deadUrl) → 텍스트
let cleanedContent = content;
for (const deadUrl of deadUrls) {
  const escaped = deadUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  cleanedContent = cleanedContent.replace(
    new RegExp(`\\[([^\\]]+)\\]\\(${escaped}\\)`, 'g'),
    '$1'
  );
}

// 죽은 URL을 references에서도 제거
const cleanedReferences = references.filter(ref => {
  if (!ref.startsWith('http')) return true;
  return !deadUrls.includes(ref);
});

const passed = deadUrls.length === 0;

return [{
  json: {
    ...item,
    content: cleanedContent,
    references: cleanedReferences,
    url_validation: {
      passed,
      total_urls: allUrls.length,
      reachable: results.filter(r => r.status === 'ok').length,
      dead: deadUrls.length,
      serp_matched: serpMatched.length,
      serp_unmatched: serpUnmatched.length,
      issues,
    }
  }
}];
```

- [ ] **Step 2: n8n 에디터에서 URL Validation 노드 단독 테스트**

Test step with sample content containing:
- Known live URL: `https://learn.microsoft.com/en-us/`
- Known dead URL: `https://this-domain-does-not-exist-99999.com/page`

Expected:
- `url_validation.reachable >= 1`
- `url_validation.dead >= 1`
- Dead URL이 content에서 링크 텍스트만 남고 URL 제거됨

- [ ] **Step 3: Commit**

```bash
git add n8n/code_nodes/validate_urls.js
git commit -m "feat(n8n): HTTP HEAD validation + SERP cross-reference + dead URL cleanup"
```

---

### Task 5: Sheets Write 노드 참조 경로 수정

**Files:**
- Modify: `n8n/workflow_complete.json` (n8n 에디터에서 수정)

**배경:** 현재 Sheets Write 노드는 `references`를 `Parse JSON Response`에서, `content`를 `Inject Images`에서 읽고 있어 URL Validation의 정제 결과가 반영되지 않음.

- [ ] **Step 1: n8n 에디터에서 Sheets Write (발행대기) 노드 수정**

현재:
```
참고자료: ={{ JSON.stringify($('Parse JSON Response').item.json.references) }}
본문마크다운: ={{ $('Inject Images').item.json.content }}
```

변경:
```
참고자료: ={{ JSON.stringify($('URL Validation').item.json.references) }}
본문마크다운: ={{ $('URL Validation').item.json.content }}
```

- [ ] **Step 2: URL 검증 메타데이터도 시트에 기록 (선택)**

Sheets Write에 컬럼 추가 (모니터링용):
```
URL검증: ={{ $('URL Validation').item.json.url_validation.reachable + '/' + $('URL Validation').item.json.url_validation.total_urls + ' (dead:' + $('URL Validation').item.json.url_validation.dead + ')' }}
```

- [ ] **Step 3: n8n에서 워크플로우 Export → workflow_complete.json 저장**

```bash
git add n8n/workflow_complete.json
git commit -m "fix(n8n): Sheets Write reads validated content/references from URL Validation node"
```

---

### Task 6: 통합 테스트

- [ ] **Step 1: 전체 파이프라인 수동 실행**

n8n 에디터에서 전체 파이프라인 수동 트리거:
1. Google Sheets에서 테스트 키워드 1건 "대기" 상태로 준비
2. 워크플로우 수동 실행
3. 각 노드 출력 확인:
   - Parse SERP Data: `serp_urls` 배열 존재
   - Route Prompt: `user_message`에 "참조 가능 URL 풀" 섹션 포함
   - URL Validation: `serp_urls` 참조 정상, HTTP 검증 실행됨
   - Sheets Write: 정제된 content/references가 시트에 기록됨

- [ ] **Step 2: 의도적 실패 테스트**

URL Validation 노드의 입력을 수동 편집하여 가짜 URL 삽입:
- `content`에 `[가짜출처](https://this-domain-does-not-exist-99999.com/page)` 추가
Expected: `dead: 1`, 해당 URL이 content에서 텍스트로 대체됨, references에서도 제거됨

- [ ] **Step 3: 데이터 흐름 검증**

Sheets Write 노드의 출력에서:
- `참고자료` 필드에 죽은 URL이 없는지 확인
- `본문마크다운` 필드에 깨진 인라인 링크가 없는지 확인
- (선택) `URL검증` 필드에 "reachable/total (dead:N)" 형식으로 기록되는지 확인

- [ ] **Step 4: Commit (최종)**

```bash
git add n8n/workflow_complete.json
git commit -m "chore(n8n): final workflow export with URL validation pipeline"
```

---

## Notes

- `this.helpers.httpRequest()`는 axios 기반. `resolveWithFullResponse` 옵션 사용 불가. try/catch로 성공/실패 판별
- HTTP 검증은 URL당 5초 타임아웃 × 최대 ~10개 URL, 배치 5개 병렬 = 실제 10~15초 추가 지연
- 일부 서버 HEAD 거부 → GET 폴백 (`maxContentLength: 1024`로 다운로드 제한)
- placeholder URL(contoso.com, example.com)은 HTTP 검증 스킵
- URL regex에서 trailing punctuation(`.`, `,`, `;`) 제거 처리 추가
- SERP 교차 대조는 도메인 레벨 (의도적 trade-off: 같은 도메인의 다른 페이지는 허용)
- `serp_urls` 파이프라인 소실 문제: `$('Parse SERP Data')` 직접 참조로 해결
