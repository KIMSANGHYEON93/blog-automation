/**
 * Node 4: 프롬프트 유형 분기 (content_type → 프롬프트 A/B/C 선택)
 * 입력: Google Sheets에서 읽은 키워드 + category
 * 출력: 적절한 시스템 프롬프트가 포함된 Claude API 요청 body
 */

const keyword = $input.first().json.keyword;
const category = $input.first().json.category || "IT 기초 용어";
const serpData = $input.first().json.serp_data || "";

// 프롬프트 유형 분기
const PROMPT_A = `당신은 B2B IT 인프라 전문 기술 블로거입니다...`; // prompt_a_terminology.md 전문
const PROMPT_B = `당신은 B2B IT 인프라 전문 기술 블로거입니다...`; // prompt_b_comparison.md 전문
const PROMPT_C = `당신은 B2B IT 인프라 전문 기술 블로거입니다...`; // prompt_c_troubleshooting.md 전문

let systemPrompt;
let promptType;

if (category.includes("비교") || category.includes("트렌드") || keyword.includes("vs")) {
  systemPrompt = PROMPT_B;
  promptType = "B";
} else if (category.includes("에러") || category.includes("트러블슈팅") || category.includes("해결")) {
  systemPrompt = PROMPT_C;
  promptType = "C";
} else {
  systemPrompt = PROMPT_A;
  promptType = "A";
}

return [{
  json: {
    keyword,
    category,
    prompt_type: promptType,
    system_prompt: systemPrompt,
    user_message: `키워드: ${keyword}\nSERP 데이터:\n${serpData}`,
  }
}];
