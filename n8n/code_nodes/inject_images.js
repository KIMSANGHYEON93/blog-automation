/**
 * Inject Images — Mermaid 다이어그램 렌더링 + Unsplash 썸네일
 * Mode: runOnceForEachItem
 * Parse JSON Response와 Validate Structure 사이에 배치
 * 입력: 파싱된 JSON (content 필드 포함)
 * 출력: Mermaid→SVG 변환된 content + thumbnail_url + image_injection 메타데이터
 */

const content = $input.item.json.content || '';
const title = $input.item.json.title || '';
const UNSPLASH_KEY = $env.UNSPLASH_ACCESS_KEY;
const helpers = this.helpers;

/**
 * IT 기술 키워드 → Unsplash 검색 친화 키워드 매핑
 * thumbnail 검색용으로 유지
 */
const KEYWORD_BROADENING = {
  terraform: 'cloud infrastructure automation',
  ansible: 'server automation terminal',
  jenkins: 'software development pipeline',
  kubernetes: 'cloud container technology',
  docker: 'container technology server',
  'ci/cd': 'software deployment automation',
  cicd: 'software deployment automation',
  ssl: 'cybersecurity encryption lock',
  tls: 'cybersecurity encryption lock',
  siem: 'cybersecurity monitoring dashboard',
  splunk: 'data analytics dashboard',
  elk: 'data analytics search',
  prometheus: 'server monitoring dashboard',
  grafana: 'monitoring dashboard visualization',
  dns: 'network technology server',
  vpn: 'network security connection',
  saml: 'authentication security login',
  oauth: 'authentication security login',
  iam: 'identity access management security',
  mfa: 'two factor authentication security',
  'sd-wan': 'network infrastructure',
  microservice: 'software architecture diagram',
  'zero trust': 'cybersecurity network',
  iac: 'infrastructure as code automation',
};

/**
 * Unsplash API에서 이미지 1장 검색 (thumbnail용)
 * @param {string} keyword - 검색 키워드
 */
async function searchUnsplashSingle(keyword) {
  if (!UNSPLASH_KEY) return null;

  try {
    const data = await helpers.httpRequest({
      method: 'GET',
      url: 'https://api.unsplash.com/search/photos',
      qs: {
        query: keyword,
        orientation: 'landscape',
        per_page: '4',
        client_id: UNSPLASH_KEY,
      },
    });
    if (!data.results || data.results.length === 0) return null;

    const idx = Math.floor(Math.random() * Math.min(data.results.length, 4));
    const photo = data.results[idx];

    return {
      thumb: photo.urls.small,
      url: photo.urls.regular,
    };
  } catch (e) {
    return null;
  }
}

/**
 * 제목에서 Unsplash 검색용 키워드 후보 배열 생성 (thumbnail용)
 */
function extractThumbnailKeywords() {
  const candidates = [];

  const titleEng = title.match(/[A-Za-z0-9][\w./-]*/g) || [];
  if (titleEng.length > 0) {
    candidates.push(titleEng.join(' '));
  }

  const lowerTitle = title.toLowerCase();
  for (const [tech, broad] of Object.entries(KEYWORD_BROADENING)) {
    if (lowerTitle.includes(tech)) {
      candidates.push(broad);
      break;
    }
  }

  candidates.push('technology software development');
  return candidates;
}

/**
 * Mermaid 코드를 kroki.io API로 SVG 렌더링
 * Primary: POST https://kroki.io/mermaid/svg (가장 단순)
 * 실패 시: null 반환 (graceful degradation)
 * @param {string} code - Mermaid 코드 (``` 제외)
 * @returns {string|null} SVG 문자열 또는 null
 */
async function renderMermaidToSvg(code) {
  try {
    const svg = await helpers.httpRequest({
      method: 'POST',
      url: 'https://kroki.io/mermaid/svg',
      body: code,
      headers: { 'Content-Type': 'text/plain' },
      returnFullResponse: false,
    });
    // SVG 응답 유효성 간단 확인
    if (typeof svg === 'string' && svg.includes('<svg')) {
      return svg;
    }
    return null;
  } catch (e) {
    return null;
  }
}

/**
 * SVG 문자열을 base64 data URI <img> 태그로 변환
 * @param {string} svg - SVG 문자열
 * @param {string} altText - alt 속성 텍스트
 * @returns {string} <img> 태그 HTML
 */
function svgToImgTag(svg, altText) {
  const b64 = Buffer.from(svg).toString('base64');
  const safeAlt = altText.replace(/"/g, '&quot;');
  return `<img src="data:image/svg+xml;base64,${b64}" alt="${safeAlt}" style="max-width:100%;height:auto;" />`;
}

// === Step 1: Mermaid 코드블록 추출 ===
const mermaidRegex = /```mermaid\n([\s\S]*?)```/g;
const blocks = [];
let match;

while ((match = mermaidRegex.exec(content)) !== null) {
  blocks.push({
    full: match[0],
    code: match[1].trim(),
    index: match.index,
  });
}

let updatedContent = content;
let renderedCount = 0;
let failedCount = 0;

// === Step 2: 각 Mermaid 블록 → kroki.io SVG 렌더링 (역순 치환) ===
for (let i = blocks.length - 1; i >= 0; i--) {
  const block = blocks[i];
  const svg = await renderMermaidToSvg(block.code);

  if (svg) {
    // Mermaid 코드 첫 줄에서 alt 텍스트 추출 (예: "graph TD" → "diagram")
    const firstLine = block.code.split('\n')[0].trim();
    const altText = `Mermaid diagram: ${firstLine}`;
    const imgTag = svgToImgTag(svg, altText);

    updatedContent =
      updatedContent.substring(0, block.index) +
      '\n' + imgTag + '\n' +
      updatedContent.substring(block.index + block.full.length);
    renderedCount++;
  } else {
    // 렌더링 실패 시 원본 코드블록 유지 (graceful degradation)
    failedCount++;
  }
}

// === Step 3: thumbnail_url — Unsplash 1장 검색 (OG 이미지용) ===
let thumbnailUrl = '';

if (UNSPLASH_KEY) {
  const keywords = extractThumbnailKeywords();
  for (const kw of keywords) {
    const result = await searchUnsplashSingle(kw);
    if (result) {
      thumbnailUrl = result.thumb || result.url;
      break;
    }
  }
}

return {
  json: {
    ...$input.item.json,
    content: updatedContent,
    thumbnail_url: thumbnailUrl,
    image_injection: {
      method: 'mermaid_kroki',
      mermaid_found: blocks.length,
      mermaid_rendered: renderedCount,
      mermaid_failed: failedCount,
      has_unsplash_key: !!UNSPLASH_KEY,
    },
  },
};
