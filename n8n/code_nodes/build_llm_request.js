/**
 * Build LLM Request — provider별 URL/headers/body 생성
 * Mode: runOnceForEachItem
 * 입력: system_prompt, user_message, _llm_purpose(optional)
 * 출력: _llm_url, _llm_headers, _llm_body, _llm_provider + 원본 데이터 패스스루
 *
 * .env의 LLM_PROVIDER 값에 따라 요청 형식을 자동 분기:
 *   - gemini: Gemini API (URL에 API key 포함)
 *   - claude: Anthropic Messages API (헤더에 API key)
 */

const provider = $env.LLM_PROVIDER || 'gemini';
const systemPrompt = $input.item.json.system_prompt;
const userMessage = $input.item.json.user_message;
const purpose = $input.item.json._llm_purpose || 'content_gen';

const PROVIDERS = {
  gemini: {
    url: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${$env.GOOGLE_API_KEY}`,
    headers: { 'content-type': 'application/json' },
    body: (sys, user, opts) => {
      const payload = {
        contents: [{ role: 'user', parts: [{ text: user }] }],
        systemInstruction: { parts: [{ text: sys }] },
        generationConfig: { maxOutputTokens: opts.maxTokens, temperature: opts.temperature },
      };
      // Search Grounding: 콘텐츠 생성 시 Google 검색으로 실시간 팩트 기반 응답
      if (opts.useSearchGrounding) {
        payload.tools = [{ google_search: {} }];
      }
      return payload;
    },
  },
  claude: {
    url: 'https://api.anthropic.com/v1/messages',
    headers: {
      'x-api-key': $env.CLAUDE_API_KEY,
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

const config = PROVIDERS[provider];
if (!config) throw new Error(`지원하지 않는 LLM provider: ${provider}`);

const opts = purpose === 'verification'
  ? { maxTokens: 800, temperature: 0, model: 'claude-haiku-4-5-20251001' }
  : { maxTokens: 32768, temperature: 0.7, useSearchGrounding: true };

return {
  json: {
    _llm_url: config.url,
    _llm_headers: config.headers,
    _llm_body: config.body(systemPrompt, userMessage, opts),
    _llm_provider: provider,
    // 원본 데이터 패스스루 (_llm 접두사 필드 제외)
    ...Object.fromEntries(
      Object.entries($input.item.json).filter(([k]) => !k.startsWith('_llm'))
    ),
  }
};
