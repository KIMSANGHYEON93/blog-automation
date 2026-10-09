/**
 * Build Verify Request — 검증용 system_prompt/user_message 생성
 * 입력: 파싱된 콘텐츠 (title, content 등)
 * 출력: system_prompt, user_message, _llm_purpose + 원본 데이터 패스스루
 */

const title = $input.item.json.title || '';
const content = $input.item.json.content || '';

return {
  json: {
    ...$input.item.json,
    system_prompt: '당신은 B2B IT 기술 콘텐츠 품질 검증 AI입니다. 아래 블로그 글을 검토하고, 정확히 다섯 항목을 평가하세요. 반드시 JSON 형식으로만 응답: {"is_accurate": true/false, "is_logical": true/false, "is_complete": true/false, "is_useful": true/false, "is_in_depth": true/false, "quality_score": 0-100, "reason": "사유 100자 이내"}',
    user_message: `제목: ${title}\n본문:\n${content}`,
    _llm_purpose: 'verification',
  }
};
