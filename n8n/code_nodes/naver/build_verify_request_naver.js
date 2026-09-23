/**
 * Build Verify Request (네이버판) — 검증 프롬프트 + 상위 글 + 본문
 * Mode: runOnceForEachItem
 * VERIFY_PROMPT는 scripts/build_naver_workflow.py가 n8n/prompts/prompt_naver_h_verification.md로 채운다.
 */

const VERIFY_PROMPT = /*INJECT:VERIFY_PROMPT*/ 'VERIFY_PROMPT' /*END:VERIFY_PROMPT*/;

function buildVerifyMessage({ keyword, title, content, topPosts }) {
  const tops = (topPosts || []).map((p, i) => `${i + 1}. ${p.title} — ${p.description}`).join('\n');
  return `키워드: ${keyword}\n\n## 네이버 검색 상위 글\n${tops || '(없음)'}`
    + `\n\n## 검증할 글\n제목: ${title}\n본문:\n${content}`;
}

if (typeof $input === 'undefined') {
  module.exports = { VERIFY_PROMPT, buildVerifyMessage };
  return;
}

const item = $input.item.json;
return {
  json: {
    ...item,
    system_prompt: VERIFY_PROMPT,
    user_message: buildVerifyMessage({
      keyword: $('Route Prompt (A/B/C)').item.json.keyword || '',
      title: item.title || '',
      content: item.content || '',
      topPosts: $('Parse SERP Data').item.json.top_posts || [],
    }),
    _llm_purpose: 'verification',
  },
};
