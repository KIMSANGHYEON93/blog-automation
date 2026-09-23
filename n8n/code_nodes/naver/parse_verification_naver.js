/**
 * Parse Verification Result (네이버판) — LLM 판정 + 구조 검사 + 검색 결과 유무를 합쳐 통과 여부 결정
 * Mode: runOnceForEachItem
 * 입력: Normalize Response (Verify) 출력 { text } — 앞 노드 필드는 넘어오지 않으므로 $('노드')로 읽는다
 * 출력: verification { passed, quality_score, reason, llm_reason, 항목별 boolean }
 * 네이버 4개 항목은 LLM이 빠뜨리면 false로 본다(기존 티스토리 판정은 true로 봄 — 네이버는 엄격하게).
 */

const BASE_CHECKS = ['is_accurate', 'is_logical', 'is_complete', 'is_useful', 'is_in_depth'];
const NAVER_CHECKS = ['no_fabricated_experience', 'natural_keyword_use', 'has_unique_info', 'mobile_readable'];
const MIN_QUALITY_SCORE = 70;

// JSON 문자열 정리 (제어 문자 + 유효하지 않은 이스케이프 복구)
function sanitizeJsonStrings(str) {
  const VALID_ESCAPES = '"\\/bfnrtu';
  let result = '';
  let inString = false;
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (inString) {
      if (ch === '\\' && i + 1 < str.length) {
        const next = str[i + 1];
        result += VALID_ESCAPES.includes(next) ? ch + next : '\\\\' + next;
        i++;
        continue;
      }
      if (ch === '"') {
        inString = false;
        result += ch;
        continue;
      }
      const code = ch.charCodeAt(0);
      if (code <= 0x1f) {
        if (code === 0x0a) result += '\\n';
        else if (code === 0x0d) result += '\\r';
        else if (code === 0x09) result += '\\t';
        continue;
      }
      result += ch;
    } else {
      if (ch === '"') inString = true;
      result += ch;
    }
  }
  return result;
}

function parseLlmJson(raw) {
  const match = String(raw || '').match(/\{[\s\S]*\}/);
  if (!match) throw new Error('JSON 없음');
  const cleaned = sanitizeJsonStrings(match[0]).replace(/,\s*([}\]])/g, '$1');
  return JSON.parse(cleaned);
}

function judgeNaver(result, { structurePassed, structureIssues, searchOk }) {
  const reasons = [];
  if (!searchOk) reasons.push('네이버 검색 결과 0건');
  if (!structurePassed) reasons.push(`구조 검사 실패: ${(structureIssues || []).join(', ')}`);
  const failed = [...BASE_CHECKS, ...NAVER_CHECKS].filter((key) => result[key] !== true);
  if (failed.length) reasons.push(`검증 미통과: ${failed.join(', ')}`);
  const score = typeof result.quality_score === 'number' ? result.quality_score : 0;
  if (score < MIN_QUALITY_SCORE) reasons.push(`품질 점수 ${score}점 (최소 ${MIN_QUALITY_SCORE})`);

  const checks = Object.fromEntries([...BASE_CHECKS, ...NAVER_CHECKS].map((k) => [k, result[k] === true]));
  return {
    passed: reasons.length === 0,
    quality_score: score,
    reason: reasons.length ? reasons.join(' / ').slice(0, 300) : (result.reason || ''),
    llm_reason: result.reason || '',
    ...checks,
  };
}

if (typeof $input === 'undefined') {
  module.exports = { parseLlmJson, judgeNaver, BASE_CHECKS, NAVER_CHECKS };
  return;
}

let result;
try {
  result = parseLlmJson($input.item.json.text);
} catch (e) {
  result = { quality_score: 0, reason: `LLM 응답 파싱 실패: ${e.message}` };
}
const structure = $('Validate Structure').item.json.structure_validation
  || { passed: false, issues: ['구조 검사 결과 없음'] };

return {
  json: {
    ...$input.item.json,
    verification: judgeNaver(result, {
      structurePassed: structure.passed === true,
      structureIssues: structure.issues || [],
      searchOk: $('Parse SERP Data').item.json.search_ok === true,
    }),
  },
};
