/**
 * Normalize LLM Response — provider별 응답에서 텍스트 추출
 * Mode: runOnceForEachItem
 * 입력: LLM API 원시 응답 (provider마다 구조가 다름)
 * 출력: { text, _llm_provider }
 *
 * Gemini 응답: candidates[0].content.parts[*].text (thought 제외 결합)
 * Claude 응답: content[0].text
 */

const provider = $input.item.json._llm_provider
  || $env.LLM_PROVIDER
  || 'gemini';

let text;
const data = $input.item.json;

if (provider === 'gemini') {
  const parts = data.candidates?.[0]?.content?.parts || [];
  // 추론 모델 + Search Grounding 응답은 텍스트가 여러 part로 분할될 수 있음
  text = parts.filter(p => !p.thought && typeof p.text === 'string').map(p => p.text).join('');
  if (!text) {
    throw new Error(`Gemini 빈 응답 (finishReason: ${data.candidates?.[0]?.finishReason || 'unknown'})`);
  }
} else if (provider === 'claude') {
  text = data.content[0].text;
} else {
  throw new Error(`지원하지 않는 provider 응답: ${provider}`);
}

return { json: { text, _llm_provider: provider } };
