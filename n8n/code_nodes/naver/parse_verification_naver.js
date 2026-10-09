/**
 * Parse Verification Result (네이버판) — LLM 판정 + 구조 검사 + 검색 결과 유무를 합쳐 통과 여부 결정
 * Mode: runOnceForEachItem
 * 입력: Normalize Response (Verify) 출력 { text } — 앞 노드 필드는 넘어오지 않으므로 $('노드')로 읽는다
 * 출력: verification { passed, quality_score, reason, llm_reason, 항목별 boolean }
 * 모든 항목은 명시적 boolean만 인정한다 — 누락·잘못된 타입은 null로 남기고 실패. 점수는 0~100 정수만.
 * 스키마: BASE_CHECKS는 티스토리 parse_verification.js의 REQUIRED_CHECKS와 같아야 한다(테스트가 확인),
 * NAVER_CHECKS는 네이버 검증 프롬프트(prompt_naver_h_verification.md)에만 있는 항목.
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
  const allChecks = [...BASE_CHECKS, ...NAVER_CHECKS];
  const malformed = allChecks.filter((key) => typeof result[key] !== 'boolean');
  if (malformed.length) reasons.push(`검증 형식 오류(누락·boolean 아님): ${malformed.join(', ')}`);
  const failed = allChecks.filter((key) => result[key] === false);
  if (failed.length) reasons.push(`검증 미통과: ${failed.join(', ')}`);
  const raw = result.quality_score;
  const scoreOk = Number.isInteger(raw) && raw >= 0 && raw <= 100;
  const score = scoreOk ? raw : 0;
  if (!scoreOk) reasons.push(`quality_score 형식 오류(0~100 정수 아님): ${String(raw)}`);
  else if (score < MIN_QUALITY_SCORE) reasons.push(`품질 점수 ${score}점 (최소 ${MIN_QUALITY_SCORE})`);

  // 누락·잘못된 타입은 false로 위장하지 않고 null로 남긴다
  const checks = Object.fromEntries(
    allChecks.map((k) => [k, typeof result[k] === 'boolean' ? result[k] : null]),
  );
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
