/**
 * Node 8: LLM 교차 검증 결과 파싱
 * Mode: runOnceForEachItem
 * 입력: 정규화된 LLM 응답 (text)
 * 출력: 검증 통과/실패 판정 (5항목 + quality_score)
 */

const raw = $input.item.json.text;

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

// JSON 추출 (방어적 파싱)
let result;
try {
  const match = raw.match(/\{[\s\S]*\}/);
  if (!match) {
    throw new Error("JSON 없음");
  }
  let jsonStr = sanitizeJsonStrings(match[0]);
  // 구조 복구: 후행 쉼표 제거
  jsonStr = jsonStr.replace(/,\s*([}\]])/g, '$1');
  result = JSON.parse(jsonStr);
} catch (e) {
  // LLM 파싱 실패 시 검수필요로 분류
  return {
    json: {
      ...$input.item.json,
      verification: {
        passed: false,
        is_accurate: null,
        is_logical: null,
        is_complete: null,
        is_useful: null,
        quality_score: 0,
        reason: `LLM 응답 파싱 실패: ${e.message}`,
        raw_response: raw.substring(0, 300),
      }
    }
  };
}

// 필수 필드 검증 (기존 2항목은 필수, 신규 2항목은 기본값 처리)
if (typeof result.is_accurate !== "boolean" || typeof result.is_logical !== "boolean") {
  return {
    json: {
      ...$input.item.json,
      verification: {
        passed: false,
        is_accurate: result.is_accurate ?? null,
        is_logical: result.is_logical ?? null,
        is_complete: result.is_complete ?? null,
        is_useful: result.is_useful ?? null,
        quality_score: result.quality_score ?? 0,
        reason: "검증 결과 형식 오류 (boolean 아님)",
      }
    }
  };
}

// 신규 항목 기본값 (LLM이 누락하면 true로 간주 — 하위 호환)
const isComplete = typeof result.is_complete === "boolean" ? result.is_complete : true;
const isUseful = typeof result.is_useful === "boolean" ? result.is_useful : true;
const isInDepth = typeof result.is_in_depth === "boolean" ? result.is_in_depth : true;
const qualityScore = typeof result.quality_score === "number" ? result.quality_score : 0;

const MIN_QUALITY_SCORE = 70;
const passed = result.is_accurate === true
  && result.is_logical === true
  && isComplete === true
  && isUseful === true
  && isInDepth === true
  && qualityScore >= MIN_QUALITY_SCORE;

return {
  json: {
    ...$input.item.json,
    verification: {
      passed,
      is_accurate: result.is_accurate,
      is_logical: result.is_logical,
      is_complete: isComplete,
      is_useful: isUseful,
      is_in_depth: isInDepth,
      quality_score: qualityScore,
      reason: result.reason || "",
    }
  }
};
