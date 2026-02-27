/**
 * Node 6: Claude API 응답 JSON 파싱 + 필수 필드 검증
 * 입력: Claude API 응답 (content[0].text)
 * 출력: 파싱된 JSON 또는 에러
 */

const raw = $input.first().json.content[0].text;

// JSON 블록 추출 (```json ... ``` 또는 bare JSON)
const match = raw.match(/```json\s*([\s\S]*?)\s*```/) ||
              raw.match(/(\{[\s\S]*\})/);

if (!match) {
  throw new Error("JSON 추출 실패: " + raw.substring(0, 200));
}

let parsed;
try {
  parsed = JSON.parse(match[1] || match[0]);
} catch (e) {
  throw new Error("JSON 파싱 실패: " + e.message + "\n원문: " + (match[1] || match[0]).substring(0, 200));
}

// 필수 필드 검증
const required = ["title", "content", "meta_description", "faq_schema",
                  "references", "internal_link_keywords"];
const missing = required.filter(f => !parsed[f]);
if (missing.length > 0) {
  throw new Error("필수 필드 누락: " + missing.join(", "));
}

// meta_description 길이 검증 (120~155자)
const metaLen = parsed.meta_description.length;
if (metaLen < 120 || metaLen > 155) {
  // 경고만 — 차단하지 않음 (후처리에서 조정 가능)
  parsed._warning = `meta_description 길이: ${metaLen}자 (권장 120~155자)`;
}

// faq_schema 형식 검증
if (!Array.isArray(parsed.faq_schema) || parsed.faq_schema.length === 0) {
  throw new Error("faq_schema가 비어있거나 배열이 아닙니다");
}
for (const faq of parsed.faq_schema) {
  if (!faq.question || !faq.answer) {
    throw new Error("faq_schema 항목에 question/answer 누락");
  }
}

return [{ json: parsed }];
