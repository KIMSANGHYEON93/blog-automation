/**
 * Build LLM Request — provider별 URL/headers/body 생성
 * 입력: system_prompt, user_message, _llm_purpose(optional)
 * 출력: _llm_url, _llm_headers, _llm_body, _llm_provider + 원본 데이터 패스스루
 */

const PROVIDERS = {
  gemini: {
    url: `https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent`,
    // API 키는 n8n Credential(Header Auth, x-goog-api-key)이 주입한다 —
    // URL/헤더에 넣으면 실행 기록에 평문으로 남는다
    headers: { 'content-type': 'application/json' },
    body: (sys, user, opts) => {
      // google_search는 넣지 않는다 — 장문 생성 요청에서는 모델이 검색을 고르지 않았다
      // (32건 모두 0회, #17). 검색은 앞 단계 Research Request가 따로 하고 결과를 user_message에 넣는다
      return {
        contents: [{ role: 'user', parts: [{ text: user }] }],
        systemInstruction: { parts: [{ text: sys }] },
        generationConfig: { maxOutputTokens: opts.maxTokens, temperature: opts.temperature },
      };
    },
  },
  claude: {
    url: 'https://api.anthropic.com/v1/messages',
    // API 키는 n8n Credential(Header Auth, x-api-key)이 주입한다.
    // LLM_PROVIDER=claude로 바꿀 때는 LLM Request 노드 2개의 자격증명을
    // 'Claude API Key (Header)'로 함께 바꿔야 한다.
    headers: {
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: (sys, user, opts) => ({
      model: opts.model || 'claude-sonnet-4-5-20250514',
      max_tokens: opts.maxTokens,
      temperature: opts.temperature,
      system: sys,
      messages: [{ role: 'user', content: user }],
    }),
  },
};

function optionsFor(llmPurpose) {
  return llmPurpose === 'verification'
    ? { maxTokens: 4096, temperature: 0, model: 'claude-haiku-4-5-20251001' }
    : { maxTokens: 32768, temperature: 0.7 };
}

if (typeof $input === 'undefined') {
  module.exports = { PROVIDERS, optionsFor };
  return;
}

const provider = $env.LLM_PROVIDER || 'gemini';
const systemPrompt = $input.item.json.system_prompt;
const userMessage = $input.item.json.user_message;
const purpose = $input.item.json._llm_purpose || 'content_gen';

const config = PROVIDERS[provider];
if (!config) throw new Error(`지원하지 않는 LLM provider: ${provider}`);

const opts = optionsFor(purpose);

return {
  json: {
    _llm_url: config.url,
    _llm_headers: config.headers,
    _llm_body: config.body(systemPrompt, userMessage, opts),
    _llm_provider: provider,
    ...Object.fromEntries(
      Object.entries($input.item.json).filter(([k]) => !k.startsWith('_llm'))
    ),
  }
};
