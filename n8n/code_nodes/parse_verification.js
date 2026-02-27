/**
 * Node 8: Haiku 교차 검증 결과 파싱
 * 입력: Haiku API 응답
 * 출력: 검증 통과/실패 판정
 */

const raw = $input.first().json.content[0].text;

// JSON 추출 (방어적 파싱)
let result;
try {
  const match = raw.match(/\{[\s\S]*\}/);
  if (!match) {
    throw new Error("JSON 없음");
  }
  result = JSON.parse(match[0]);
} catch (e) {
  // Haiku 파싱 실패 시 검수필요로 분류
  return [{
    json: {
      ...$input.first().json,
      verification: {
        passed: false,
        is_accurate: null,
        is_logical: null,
        reason: `Haiku 응답 파싱 실패: ${e.message}`,
        raw_response: raw.substring(0, 300),
      }
    }
  }];
}

// 필수 필드 검증
if (typeof result.is_accurate !== "boolean" || typeof result.is_logical !== "boolean") {
  return [{
    json: {
      ...$input.first().json,
      verification: {
        passed: false,
        is_accurate: result.is_accurate ?? null,
        is_logical: result.is_logical ?? null,
        reason: "검증 결과 형식 오류 (boolean 아님)",
      }
    }
  }];
}

const passed = result.is_accurate === true && result.is_logical === true;

return [{
  json: {
    ...$input.first().json,
    verification: {
      passed,
      is_accurate: result.is_accurate,
      is_logical: result.is_logical,
      reason: result.reason || "",
    }
  }
}];
