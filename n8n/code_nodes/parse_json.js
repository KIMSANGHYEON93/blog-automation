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

// 알려진 최상위 JSON 필드 목록 (구조적 키 판별에 사용)
const TOP_LEVEL_KEYS = new Set([
  'title', 'url_slug', 'content', 'meta_description', 'faq_schema',
  'references', 'internal_link_keywords', 'tags', '_warning',
]);

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
          // 다음도 " → 다음 "..." 사이가 유효한 JSON 키인지 검증
          let j = peek + 1;
          let candidateKey = '';
          while (j < str.length && str[j] !== '"' && str[j] !== ':') {
            candidateKey += str[j];
            j++;
          }
          // 조건 강화: (1) " 로 닫혀야 하고 (2) 그 뒤에 : 이 있고
          // (3) 키가 유효한 JSON 키 패턴 (짧고, 알파벳/언더스코어)
          // (4) 알려진 최상위 필드명이어야 구조적 종료로 판단
          if (j < str.length && str[j] === '"') {
            let k = j + 1;
            while (k < str.length && /[\s]/.test(str[k])) k++;
            if (k < str.length && str[k] === ':'
                && candidateKey.length > 0 && candidateKey.length < 30
                && /^[a-zA-Z_][\w_]*$/.test(candidateKey)
                && TOP_LEVEL_KEYS.has(candidateKey)) {
              // "value" "known_key": → 쉼표 누락이지만 구조적 종료
              result += '"';
              i++;
              return;
            }
          }
          // 유효한 키가 아님 → content 내 인용부호
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

// === Step 2.5: 필드 경계 기반 추출 (3차 폴백) ===
// 최상위 키 위치를 정규식으로 찾아 값을 개별 추출 → 안전하게 이스케이프
function extractByFieldBoundary(str) {
  // 최상위 키의 시작 위치 찾기: "key" 다음에 : 이 오는 패턴
  // 들여쓰기 기반 필터: 최상위 키는 보통 2~4칸 들여쓰기 또는 줄 시작
  const keyPattern = /(?:^|[\n{,])\s*"(title|content|meta_description|faq_schema|references|internal_link_keywords)"\s*:/g;
  const seen = new Set();
  const positions = [];
  let m;
  while ((m = keyPattern.exec(str)) !== null) {
    // 각 키의 첫 번째 매치만 사용 (중복 방지)
    if (seen.has(m[1])) continue;
    seen.add(m[1]);
    // 실제 키 시작 위치 보정 (prefix 문자 제외)
    const keyStart = str.indexOf('"' + m[1] + '"', m.index);
    const fullMatch = '"' + m[1] + '"';
    let vs = keyStart + fullMatch.length;
    while (vs < str.length && /[\s:]/.test(str[vs])) vs++;
    positions.push({ key: m[1], start: keyStart, valueStart: vs });
  }
  if (positions.length === 0) {
    throw new Error("필드 경계를 찾을 수 없음");
  }
  // 키 위치 순서로 정렬
  positions.sort((a, b) => a.start - b.start);

  const obj = {};
  for (let pi = 0; pi < positions.length; pi++) {
    const pos = positions[pi];
    // 값 영역: 현재 valueStart ~ 다음 키의 start (또는 문자열 끝)
    const valueEnd = pi + 1 < positions.length ? positions[pi + 1].start : str.length;
    let rawValue = str.substring(pos.valueStart, valueEnd).trim();

    // 후행 쉼표 제거
    if (rawValue.endsWith(',')) rawValue = rawValue.slice(0, -1).trim();
    // 마지막 필드일 때 닫는 } 제거
    if (pi === positions.length - 1 && rawValue.endsWith('}')) {
      rawValue = rawValue.slice(0, -1).trim();
      if (rawValue.endsWith(',')) rawValue = rawValue.slice(0, -1).trim();
    }

    // 배열/객체 값은 직접 파싱 시도
    if (rawValue.startsWith('[') || rawValue.startsWith('{')) {
      try {
        obj[pos.key] = JSON.parse(rawValue);
        continue;
      } catch (_) {
        // 배열/객체 파싱 실패 → 문자열 repair 시도
        try {
          obj[pos.key] = JSON.parse(repairJson(rawValue));
          continue;
        } catch (__) {
          // 배열 필드는 빈 배열로 초기화 (문자열로 저장 방지)
          if (['faq_schema', 'references', 'internal_link_keywords'].includes(pos.key)) {
            obj[pos.key] = [];
            continue;
          }
          // 그 외 → 문자열로 저장
        }
      }
    }

    // 문자열 값: 앞뒤 " 제거 후 내부 " 이스케이프
    if (rawValue.startsWith('"')) rawValue = rawValue.slice(1);
    if (rawValue.endsWith('"')) rawValue = rawValue.slice(0, -1);
    // 이미 이스케이프된 \" 보존, 나머지 " 이스케이프
    rawValue = rawValue.replace(/\\"/g, '<<ESC_Q>>');
    rawValue = rawValue.replace(/"/g, '\\"');
    rawValue = rawValue.replace(/<<ESC_Q>>/g, '\\"');
    // 제어 문자 이스케이프
    rawValue = rawValue.replace(/[\x00-\x1f]/g, (c) => {
      if (c === '\n') return '\\n';
      if (c === '\r') return '\\r';
      if (c === '\t') return '\\t';
      return '';
    });

    try {
      obj[pos.key] = JSON.parse('"' + rawValue + '"');
    } catch (_) {
      obj[pos.key] = rawValue; // 최후 수단: raw 문자열 그대로
    }
  }

  return obj;
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
    // 3차: 필드 경계 추출 (content 필드의 unescaped quote 대응)
    try {
      parsed = extractByFieldBoundary(jsonStr);
    } catch (e3) {
      throw new Error("JSON 파싱 실패: " + e1.message
        + " | repair 후: " + e2.message
        + " | boundary 후: " + e3.message);
    }
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
const FAQ_PLACEHOLDER = /참조|참고하세요|확인하세요|문서를 보세요|홈페이지를 방문/;
for (const faq of parsed.faq_schema) {
  if (!faq.question || !faq.answer) {
    throw new Error("faq_schema 항목에 question/answer 누락");
  }
  if (faq.answer.length < 80) {
    throw new Error(`FAQ 답변 길이 부족: ${faq.answer.length}자 (최소 80자)`);
  }
  if (FAQ_PLACEHOLDER.test(faq.answer) && faq.answer.length < 120) {
    throw new Error(`FAQ 답변이 플레이스홀더: "${faq.answer.slice(0, 50)}..."`);
  }
}

// references 플레이스홀더 필터링
if (Array.isArray(parsed.references)) {
  parsed.references = parsed.references.filter(ref => {
    if (typeof ref !== 'string') return false;
    if (ref.length < 10) return false;
    if (/^참조|^참고|^확인|^검색/.test(ref) && !ref.startsWith('http')) return false;
    return true;
  });
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
