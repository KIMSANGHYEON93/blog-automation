/**
 * Validate Structure (네이버판) — 네이버 규칙을 코드로 검사
 * Mode: runOnceForEachItem
 * 입력: Parse JSON Response 출력 (title, content, tags)
 * 출력: 입력 + structure_validation { passed, issues, stats }
 * 여기서 실패하면 Parse Verification Result가 LLM 점수와 무관하게 검수필요로 보낸다.
 */

const LIMITS = {
  minLength: 3000,
  minH2: 3,
  minKeywordCount: 1,
  maxKeywordCount: 6,
  maxExternalLinks: 3,
  maxParagraphChars: 300,
  maxCodeBlocks: 1,
  minTags: 5,
  maxTags: 15,
};

// 제목·표·목록·인용·코드는 문단 길이 검사에서 뺀다
const NON_PARAGRAPH = /^(#|\||-|\*|>|```|\d+\.\s)/;

function countOccurrences(text, word) {
  const needle = String(word || '').trim().toLowerCase();
  if (!needle) return 0;
  return String(text || '').toLowerCase().split(needle).length - 1;
}

function longParagraphs(content, maxChars) {
  return String(content || '')
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter((block) => block && !NON_PARAGRAPH.test(block))
    .filter((block) => block.length > maxChars);
}

function titleHasKeyword(title, keyword) {
  const squash = (s) => String(s || '').replace(/\s+/g, '').toLowerCase();
  const t = squash(title);
  if (t.includes(squash(keyword))) return true;
  const tokens = String(keyword || '').toLowerCase().split(/\s+/).filter(Boolean);
  return tokens.length > 0 && tokens.every((tok) => t.includes(tok));
}

function validateNaverStructure({ title, content, keyword, tags }) {
  const text = String(content || '');
  const issues = [];
  const h2 = (text.match(/^## /gm) || []).length;
  const keywordCount = countOccurrences(text, keyword);
  const externalLinks = (text.match(/\]\(https?:\/\/[^)]+\)/g) || []).length;
  const codeBlocks = Math.floor((text.match(/^```/gm) || []).length / 2);
  const longOnes = longParagraphs(text, LIMITS.maxParagraphChars);
  const tagCount = Array.isArray(tags) ? tags.length : 0;

  if (text.length < LIMITS.minLength) issues.push(`본문 길이 부족: ${text.length}자 (최소 ${LIMITS.minLength}자)`);
  if (h2 < LIMITS.minH2) issues.push(`소제목(H2) 부족: ${h2}개 (최소 ${LIMITS.minH2}개)`);
  if (!titleHasKeyword(title, keyword)) issues.push('제목에 키워드 없음');
  if (keywordCount < LIMITS.minKeywordCount) issues.push('본문에 키워드 없음');
  if (keywordCount > LIMITS.maxKeywordCount) issues.push(`키워드 반복 과다: ${keywordCount}회 (최대 ${LIMITS.maxKeywordCount}회)`);
  if (externalLinks > LIMITS.maxExternalLinks) issues.push(`외부 링크 과다: ${externalLinks}개 (최대 ${LIMITS.maxExternalLinks}개)`);
  if (codeBlocks > LIMITS.maxCodeBlocks) issues.push(`코드 블록 과다: ${codeBlocks}개 (최대 ${LIMITS.maxCodeBlocks}개)`);
  if (longOnes.length > 0) issues.push(`긴 문단 ${longOnes.length}개 (문단당 최대 ${LIMITS.maxParagraphChars}자)`);
  if (tagCount < LIMITS.minTags || tagCount > LIMITS.maxTags) issues.push(`태그 수 ${tagCount}개 (${LIMITS.minTags}~${LIMITS.maxTags}개)`);

  return {
    passed: issues.length === 0,
    issues,
    stats: {
      length: text.length, h2, keyword_count: keywordCount, external_links: externalLinks,
      code_blocks: codeBlocks, long_paragraphs: longOnes.length, tags: tagCount,
    },
  };
}

if (typeof $input === 'undefined') {
  module.exports = { LIMITS, countOccurrences, longParagraphs, titleHasKeyword, validateNaverStructure };
  return;
}

const item = $input.item.json;
return {
  json: {
    ...item,
    structure_validation: validateNaverStructure({
      title: item.title,
      content: item.content,
      keyword: $('Route Prompt (A/B/C)').item.json.keyword || '',
      tags: item.tags,
    }),
  },
};
