/**
 * Validate Structure — 마크다운 구조 자동 검증
 * Mode: runOnceForEachItem
 * Parse JSON과 Gemini Verification 사이에 배치
 * 입력: 파싱된 JSON (content 필드 포함)
 * 출력: 구조 검증 결과 추가
 */

const content = $input.item.json.content || '';
const promptType = $('Route Prompt (A/B/C)').item.json.prompt_type || 'A';

const issues = [];

// 1. H2 헤딩 카운트
const h2Matches = content.match(/^## /gm) || [];
const h2Count = h2Matches.length;

const MIN_H2 = { 'A': 4, 'B': 5, 'C': 4 };
const minH2 = MIN_H2[promptType] || 4;

if (h2Count < minH2) {
  issues.push(`H2 헤딩 부족: ${h2Count}개 (최소 ${minH2}개)`);
}

// 2. H3 헤딩 카운트
const h3Matches = content.match(/^### /gm) || [];
const h3Count = h3Matches.length;

// 3. 마크다운 테이블 행 수
const tableRows = content.match(/^\|.*\|$/gm) || [];
const tableSeparators = content.match(/^\|[\s\-:|]+\|$/gm) || [];
const tableDataRows = tableRows.length - tableSeparators.length;

if (promptType === 'A' || promptType === 'B') {
  if (tableDataRows < 1) {
    issues.push('마크다운 테이블 없음 (최소 1개 필요)');
  }
  if (promptType === 'B' && tableDataRows < 7) {
    issues.push(`비교표 행 부족: ${tableDataRows}행 (최소 7행)`);
  }
}

// 4. 코드블록 수
const codeBlocks = content.match(/```\w*/g) || [];
const codeBlockCount = Math.floor(codeBlocks.length / 2);

if (promptType === 'C' && codeBlockCount < 3) {
  issues.push(`코드블록 부족: ${codeBlockCount}개 (최소 3개)`);
}

// 5. FAQ 섹션 존재 여부
const hasFAQ = /##\s*FAQ/i.test(content) || /##.*자주\s*묻는/i.test(content);
if (!hasFAQ) {
  issues.push('FAQ 섹션 없음');
}

// 6. faq_schema 검증
const faqSchema = $input.item.json.faq_schema || [];
if (faqSchema.length < 3) {
  issues.push(`FAQ 항목 부족: ${faqSchema.length}개 (최소 3개)`);
}
const shortAnswers = faqSchema.filter(f => f.answer && f.answer.length < 80);
if (shortAnswers.length > 0) {
  issues.push(`FAQ 답변 80자 미만: ${shortAnswers.length}건`);
}

// 7. IMAGE 마커 잔류 검사 (inject_images.js 이후이므로 잔류하면 안됨)
const imageMarkers = content.match(/<!-- IMAGE:\s*.+?\s*-->/g) || [];
if (imageMarkers.length > 0) {
  issues.push(`미처리 IMAGE 마커 ${imageMarkers.length}개 잔류`);
}

// 8. 이미지 개수 (정보 제공, 실패 아님)
const imageCount = (content.match(/!\[.*?\]\(.*?\)/g) || []).length;

// 9. Mermaid 코드블록 잔류 감지 (WARNING only — hard fail 아님)
// mermaid 잔류 > 0이면 inject_images.js가 렌더링 실패한 것
// 콘텐츠 자체는 유효하므로 warning only
const mermaidResidues = content.match(/```mermaid/g) || [];
const mermaidWarning = mermaidResidues.length > 0
  ? `Mermaid 코드블록 ${mermaidResidues.length}개 미렌더링 (경고)`
  : null;

const passed = issues.length === 0;

return {
  json: {
    ...$input.item.json,
    structure_validation: {
      passed,
      h2_count: h2Count,
      h3_count: h3Count,
      table_rows: tableDataRows,
      code_block_count: codeBlockCount,
      has_faq_section: hasFAQ,
      faq_count: faqSchema.length,
      image_count: imageCount,
      mermaid_residue: mermaidResidues.length,
      mermaid_warning: mermaidWarning,
      issues,
    }
  }
};
