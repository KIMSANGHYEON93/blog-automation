/**
 * Build Verify Request (네이버판) — 검증 프롬프트 + 상위 글 + 본문
 * Mode: runOnceForEachItem
 * VERIFY_PROMPT는 scripts/build_naver_workflow.py가 n8n/prompts/prompt_naver_h_verification.md로 채운다.
 */

const VERIFY_PROMPT = /*INJECT:VERIFY_PROMPT*/ 'VERIFY_PROMPT' /*END:VERIFY_PROMPT*/;

function buildVerifyMessage({ keyword, title, content, topPosts, today, officialDocs }) {
  const tops = (topPosts || []).map((p, i) => `${i + 1}. ${p.title} — ${p.description}`).join('\n');
  // 기준일·근거가 없으면 검증 LLM이 자기 지식으로 최신 사실을 '없음·미래'로 판정한다(2026-10-14)
  return `키워드: ${keyword}\n작성 기준일: ${today || ''}`
    + `\n\n## 네이버 검색 상위 글\n${tops || '(없음)'}`
    + `\n\n## 근거 자료 (공식 문서 발췌)\n${officialDocs || '(없음)'}`
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
      today: new Date().toISOString().slice(0, 10),
      officialDocs: $('Fetch Official Docs').item.json.official_docs_text || '',
    }),
    _llm_purpose: 'verification',
  },
};
