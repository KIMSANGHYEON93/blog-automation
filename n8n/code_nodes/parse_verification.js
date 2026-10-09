/**
 * Node 8: LLM 교차 검증 결과 파싱
 * Mode: runOnceForEachItem
 * 입력: 정규화된 LLM 응답 (text)
 * 출력: 검증 통과/실패 판정 (5항목 + quality_score)
 *
 * 항목은 명시적 boolean만 인정한다. 누락·잘못된 타입은 null로 남기고 검수필요(passed=false)로 보낸다.
 * 점수는 0~100 정수만 인정한다. 네이버판(naver/parse_verification_naver.js)의 BASE_CHECKS와
 * REQUIRED_CHECKS는 같아야 한다(테스트가 확인) — 네이버는 여기에 NAVER_CHECKS 4개를 더 본다.
 */

const REQUIRED_CHECKS = ['is_accurate', 'is_logical', 'is_complete', 'is_useful', 'is_in_depth'];
const MIN_QUALITY_SCORE = 70;

// JSON 문자열 정리 (제어 문자 + 유효하지 않은 이스케이프 복구)
function sanitizeJsonStrings(str) {
  const VALID_ESCAPES = '"\\\/bfnrtu';
  let result = '';
  let inString = false;
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (inString) {
      if (ch === '\\' && i + 1 < str.length) {
        const next = str[i + 1];
        if (VALID_ESCAPES.includes(next)) {
          result += ch + next;
        } else {
          result += '\\\\' + next;
        }
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
  // 구조 복구: 후행 쉼표 제거
  return JSON.parse(sanitizeJsonStrings(match[0]).replace(/,\s*([}\]])/g, '$1'));
}

function isValidScore(score) {
  return Number.isInteger(score) && score >= 0 && score <= 100;
}

function judgeVerification(result) {
  const reasons = [];
  const malformed = REQUIRED_CHECKS.filter((k) => typeof result[k] !== 'boolean');
  if (malformed.length) reasons.push(`검증 형식 오류(누락·boolean 아님): ${malformed.join(', ')}`);
  const failed = REQUIRED_CHECKS.filter((k) => result[k] === false);
  if (failed.length) reasons.push(`검증 미통과: ${failed.join(', ')}`);
  const scoreOk = isValidScore(result.quality_score);
  if (!scoreOk) reasons.push(`quality_score 형식 오류(0~100 정수 아님): ${String(result.quality_score)}`);
  const score = scoreOk ? result.quality_score : 0;
  if (scoreOk && score < MIN_QUALITY_SCORE) reasons.push(`품질 점수 ${score}점 (최소 ${MIN_QUALITY_SCORE})`);

  const checks = Object.fromEntries(
    REQUIRED_CHECKS.map((k) => [k, typeof result[k] === 'boolean' ? result[k] : null]),
  );
  const llmReason = typeof result.reason === 'string' ? result.reason : '';
  // 통과 여부는 항목·점수 형식 사유만 본다 (LLM reason은 참고용)
  const passed = reasons.length === 0;
  return {
    passed,
    ...checks,
    quality_score: score,
    reason: passed ? llmReason : [...reasons, llmReason].filter(Boolean).join(' / ').slice(0, 300),
  };
}

if (typeof $input === 'undefined') {
  module.exports = { parseLlmJson, judgeVerification, REQUIRED_CHECKS, MIN_QUALITY_SCORE };
  return;
}

const raw = $input.item.json.text;
let parsed;
try {
  parsed = parseLlmJson(raw);
} catch (e) {
  // LLM 파싱 실패 시 검수필요로 분류
  return {
    json: {
      ...$input.item.json,
      verification: {
        ...judgeVerification({}),
        reason: `LLM 응답 파싱 실패: ${e.message}`,
        raw_response: String(raw || '').substring(0, 300),
      },
    },
  };
}

return {
  json: {
    ...$input.item.json,
    verification: judgeVerification(parsed && typeof parsed === 'object' ? parsed : {}),
  },
};
