/**
 * Normalize LLM Response — provider별 응답에서 텍스트 추출
 * Mode: runOnceForEachItem
 * 입력: LLM API 원시 응답 (provider마다 구조가 다름)
 * 출력: { text, _llm_provider }
 *
 * Gemini 응답: candidates[0].content.parts[0].text
 * Claude 응답: content[0].text
 */

const provider = $input.item.json._llm_provider
  || $env.LLM_PROVIDER
  || 'gemini';

let text;
const data = $input.item.json;

if (provider === 'gemini') {
  text = data.candidates[0].content.parts[0].text;
} else if (provider === 'claude') {
  text = data.content[0].text;
} else {
  throw new Error(`지원하지 않는 provider 응답: ${provider}`);
}

return { json: { text, _llm_provider: provider } };
