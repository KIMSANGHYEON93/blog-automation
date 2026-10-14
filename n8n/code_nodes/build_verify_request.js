/**
 * Build Verify Request — 검증용 system_prompt/user_message 생성
 * 입력: 파싱된 콘텐츠 (title, content 등)
 * 출력: system_prompt, user_message, _llm_purpose + 원본 데이터 패스스루
 * 작성 기준일·공식 문서를 함께 준다 — 없으면 검증 LLM이 자기 지식으로 최신 사실을
 * '없음·미래'로 판정한다(2026-10-14 네이버 65점 사례, 같은 규칙을 티스토리에도).
 */

const SYSTEM_PROMPT = '당신은 B2B IT 기술 콘텐츠 품질 검증 AI입니다. 아래 블로그 글을 검토하고, 정확히 다섯 항목을 평가하세요. '
  + '정확성 판정: 사용자 메시지의 "작성 기준일"이 오늘이며 그 이전 일은 과거입니다. 당신의 학습 시점 이후에 나온 모델·버전일 수 있으니 '
  + '모른다는 이유만으로 오류로 보지 말고, "근거 자료"와 어긋나거나 글 안에서 모순되거나 널리 알려진 사실과 분명히 다를 때만 is_accurate를 false로 하세요. '
  + 'false면 틀렸다고 본 문장을 inaccurate_claims에 원문 그대로 최대 5개 적고, true면 빈 배열로 두세요. '
  + '반드시 JSON 형식으로만 응답: {"is_accurate": true/false, "is_logical": true/false, "is_complete": true/false, '
  + '"is_useful": true/false, "is_in_depth": true/false, "inaccurate_claims": [], "quality_score": 0-100, "reason": "사유 100자 이내"}';

function buildVerifyMessage({ title, content, today, officialDocs }) {
  return `작성 기준일: ${today || ''}`
    + `\n\n## 근거 자료 (공식 문서 발췌)\n${officialDocs || '(없음)'}`
    + `\n\n## 검증할 글\n제목: ${title}\n본문:\n${content}`;
}

if (typeof $input === 'undefined') {
  module.exports = { SYSTEM_PROMPT, buildVerifyMessage };
  return;
}

return {
  json: {
    ...$input.item.json,
    system_prompt: SYSTEM_PROMPT,
    user_message: buildVerifyMessage({
      title: $input.item.json.title || '',
      content: $input.item.json.content || '',
      today: new Date().toISOString().slice(0, 10),
      officialDocs: $('Fetch Official Docs').item.json.official_docs_text || '',
    }),
    _llm_purpose: 'verification',
  }
};
