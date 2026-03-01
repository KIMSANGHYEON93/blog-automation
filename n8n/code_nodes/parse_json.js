/**
 * Node 6: LLM 응답 JSON 파싱 + 필수 필드 검증
 * Mode: runOnceForEachItem
 * 입력: 정규화된 LLM 응답 (text)
 * 출력: 파싱된 JSON 또는 에러
 *
 * LLM이 생성한 JSON의 일반적 문제를 자동 복구:
 * - 문자열 내 이스케이프되지 않은 " (YAML, 코드블록 등)
 * - 제어 문자 (raw newline/tab)
 * - 유효하지 않은 이스케이프 시퀀스 (\g, \e 등)
 */

const raw = $input.item.json.text;

// === Step 1: JSON 블록 추출 ===
let jsonStr;
const fenceStart = raw.indexOf('```json');
if (fenceStart !== -1) {
  const contentStart = raw.indexOf('\n', fenceStart);
  const fenceEnd = raw.lastIndexOf('```');
  if (contentStart !== -1 && fenceEnd > fenceStart + 7) {
    jsonStr = raw.substring(contentStart + 1, fenceEnd).trim();
  }
}
if (!jsonStr) {
  const match = raw.match(/(\{[\s\S]*\})/);
  if (!match) {
    throw new Error("JSON 추출 실패: " + raw.substring(0, 200));
  }
  jsonStr = match[1];
}

// === Step 2: Lenient JSON repair ===
// 구조적 파싱으로 이스케이프되지 않은 " 와 제어 문자를 자동 복구
function repairJson(str) {
  const VALID_ESCAPES = '"\\\/bfnrtu';
  let result = '';
  let i = 0;

  function skipWS() {
    while (i < str.length && /\s/.test(str[i])) { result += str[i++]; }
  }

  function parseValue() {
    skipWS();
    if (i >= str.length) return;
    if (str[i] === '"') parseString();
    else if (str[i] === '{') parseObject();
    else if (str[i] === '[') parseArray();
    else parseLiteral();
  }

  function parseString() {
    result += str[i++]; // opening "

    while (i < str.length) {
      const ch = str[i];

      // 이스케이프 시퀀스
      if (ch === '\\' && i + 1 < str.length) {
        const next = str[i + 1];
        if (VALID_ESCAPES.includes(next)) {
          result += ch + next;
        } else {
          // 유효하지 않은 이스케이프 → 백슬래시 이중 이스케이프
          result += '\\\\' + next;
        }
        i += 2;
        continue;
      }

      // 큰따옴표: 구조적 종료인지 content 내 인용부호인지 판단
      if (ch === '"') {
        // 다음 비공백 문자로 판단
        let peek = i + 1;
        while (peek < str.length && /[\s\n\r\t]/.test(str[peek])) peek++;

        if (peek >= str.length || ',:]}'.indexOf(str[peek]) !== -1) {
          // 구조적 종료: 뒤에 , ] } : 또는 EOF
          result += '"';
          i++;
          return;
        } else if (str[peek] === '"') {
          // 다음도 " → 다음 " 뒤에 : 이 있으면 객체 키 → 구조적 종료
          let j = peek + 1;
          while (j < str.length && str[j] !== '"' && str[j] !== ':') j++;
          if (j < str.length && str[j] === ':') {
            // "value" "key": → 쉼표 누락이지만 구조적 종료
            result += '"';
            i++;
            return;
          }
          // 다음 " 뒤에 : 없음 → content 내 인용부호
          result += '\\"';
          i++;
          continue;
        } else {
          // 뒤에 일반 문자 → content 내 이스케이프되지 않은 인용부호
          result += '\\"';
          i++;
          continue;
        }
      }

      // 제어 문자
      const code = ch.charCodeAt(0);
      if (code <= 0x1f) {
        if (code === 0x0a) result += '\\n';
        else if (code === 0x0d) result += '\\r';
        else if (code === 0x09) result += '\\t';
        i++;
        continue;
      }

      result += ch;
      i++;
    }
  }

  function parseObject() {
    result += str[i++]; // {
    skipWS();
    let first = true;
    while (i < str.length && str[i] !== '}') {
      if (!first) {
        if (str[i] === ',') result += str[i++];
        // 쉼표 누락: "}" 아닌 다른 문자가 오면 쉼표 삽입
        else {
          skipWS();
          if (i < str.length && str[i] === '"') result += ',';
        }
      }
      first = false;
      skipWS();
      if (i >= str.length || str[i] === '}') break;
      parseString(); // key
      skipWS();
      if (i < str.length && str[i] === ':') result += str[i++];
      parseValue();   // value
      skipWS();
    }
    if (i < str.length && str[i] === '}') result += str[i++];
  }

  function parseArray() {
    result += str[i++]; // [
    skipWS();
    let first = true;
    while (i < str.length && str[i] !== ']') {
      if (!first) {
        if (str[i] === ',') result += str[i++];
        else {
          skipWS();
          if (i < str.length && str[i] !== ']') result += ',';
        }
      }
      first = false;
      skipWS();
      if (i >= str.length || str[i] === ']') break;
      parseValue();
      skipWS();
    }
    if (i < str.length && str[i] === ']') result += str[i++];
  }

  function parseLiteral() {
    // number, boolean, null
    while (i < str.length && /[^\s,\]}\[]/.test(str[i])) {
      result += str[i++];
    }
  }

  parseValue();
  return result;
}

// === Step 3: 파싱 ===
let parsed;

// 1차: 그대로 파싱
try {
  parsed = JSON.parse(jsonStr);
} catch (e1) {
  // 2차: lenient repair 후 파싱
  try {
    const repaired = repairJson(jsonStr);
    parsed = JSON.parse(repaired);
  } catch (e2) {
    throw new Error("JSON 파싱 실패: " + e1.message + " | repair 후: " + e2.message);
  }
}

// === Step 4: 필수 필드 검증 ===
const required = ["title", "content", "meta_description", "faq_schema",
                  "references", "internal_link_keywords"];
const missing = required.filter(f => !parsed[f]);
if (missing.length > 0) {
  throw new Error("필수 필드 누락: " + missing.join(", "));
}

// meta_description 길이 검증 (120~155자)
const metaLen = parsed.meta_description.length;
if (metaLen < 120 || metaLen > 155) {
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

// 본문 길이 검증 (프롬프트 유형별 최소 글자 수)
const promptType = $('Route Prompt (A/B/C)').item.json.prompt_type || 'A';
const LENGTH_RULES = {
  'A': { min: 1500 },
  'B': { min: 2000 },
  'C': { min: 2000 }
};
const rule = LENGTH_RULES[promptType] || LENGTH_RULES['A'];
if (parsed.content.length < rule.min) {
  throw new Error(`본문 길이 부족: ${parsed.content.length}자 (최소 ${rule.min}자, 유형: ${promptType})`);
}

return { json: parsed };
