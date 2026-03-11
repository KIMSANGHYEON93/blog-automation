/**
 * Inject Images — Mermaid 다이어그램 → kroki.io URL + Unsplash Hero/섹션 이미지 + 썸네일
 * Mode: runOnceForEachItem
 * Parse JSON Response와 Validate Structure 사이에 배치
 * 입력: 파싱된 JSON (content 필드 포함)
 * 출력: [MERMAID]→kroki.io <img> URL 변환된 content + <!-- IMAGE: -->→Unsplash <figure>
 *       + Hero 이미지 + thumbnail_url + image_injection 메타데이터
 *
 * LLM은 [MERMAID]...[/MERMAID] 커스텀 마커로 다이어그램을 생성한다.
 * (JSON 안의 ```가 fence 탐지를 깨뜨리고 Gemini 응답 truncation을 유발하는 것을 방지)
 * SVG를 직접 삽입하지 않고 kroki.io GET URL을 사용하여 Google Sheets 50K 셀 제한을 회피한다.
 * 다이어그램당 URL ~200자 vs 인라인 SVG ~10,000자+
 *
 * <!-- IMAGE: keyword --> 마커는 LLM이 콘텐츠 맥락에 맞게 생성하며,
 * Unsplash API로 검색하여 <figure> 태그로 치환한다.
 */

const zlib = require('zlib');

const content = $input.item.json.content || '';
const title = $input.item.json.title || '';
const UNSPLASH_KEY = $env.UNSPLASH_ACCESS_KEY;
const helpers = this.helpers;

const MAX_SECTION_IMAGES = 2;

/**
 * IT 기술 키워드 → Unsplash 검색 친화 키워드 매핑
 * thumbnail/hero 검색용으로 유지
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
 * Unsplash API에서 이미지 검색
 * @param {string} keyword - 검색 키워드
 * @param {Set<string>} usedIds - 같은 글 내 사진 중복 방지용 ID Set
 * @returns {object|null} { id, thumb, url, photographer, photographerUrl }
 */
async function searchUnsplash(keyword, usedIds) {
  if (!UNSPLASH_KEY) return null;

  try {
    const data = await helpers.httpRequest({
      method: 'GET',
      url: 'https://api.unsplash.com/search/photos',
      qs: {
        query: keyword,
        orientation: 'landscape',
        per_page: '10',
        client_id: UNSPLASH_KEY,
      },
    });
    if (!data.results || data.results.length === 0) return null;

    // usedIds에 없는 사진 중 랜덤 선택
    const available = data.results.filter(p => !usedIds.has(p.id));
    if (available.length === 0) return null;

    const idx = Math.floor(Math.random() * Math.min(available.length, 6));
    const photo = available[idx];

    return {
      id: photo.id,
      thumb: photo.urls.small,
      url: photo.urls.regular,
      photographer: photo.user.name || 'Unknown',
      photographerUrl: photo.user.links?.html || 'https://unsplash.com',
    };
  } catch (e) {
    return null;
  }
}

/**
 * Unsplash 이미지를 <figure> 태그로 생성
 * @param {object} photo - searchUnsplash 반환값
 * @param {string} altText - alt 속성 텍스트
 * @param {boolean} isHero - Hero 이미지 여부 (fetchpriority="high")
 * @returns {string} <figure> HTML
 */
function unsplashFigureTag(photo, altText, isHero) {
  const safeAlt = altText.replace(/"/g, '&quot;');
  const priority = isHero ? ' fetchpriority="high"' : ' loading="lazy"';
  const imgUrl = isHero ? photo.url : photo.url;
  return (
    `<figure style="max-width:100%;border-radius:8px;margin:24px 0;">` +
    `<img src="${imgUrl}" alt="${safeAlt}"${priority} decoding="async" ` +
    `style="max-width:100%;height:auto;border-radius:8px;" />` +
    `<!-- Photo by ${photo.photographer} on Unsplash -->` +
    `</figure>`
  );
}

/**
 * 제목에서 Unsplash 검색용 키워드 후보 배열 생성 (hero/thumbnail용)
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
 * Mermaid 코드를 kroki.io GET URL로 변환
 * deflate 압축 + base64url 인코딩 → https://kroki.io/mermaid/svg/{encoded}
 * Google Sheets 50K 제한 회피를 위해 SVG 임베딩 대신 URL 참조 사용
 * @param {string} code - Mermaid 코드 (``` 제외)
 * @returns {string|null} kroki.io URL 또는 null
 */
function mermaidToKrokiUrl(code) {
  try {
    const deflated = zlib.deflateSync(Buffer.from(code, 'utf-8'));
    const encoded = deflated.toString('base64url');
    return `https://kroki.io/mermaid/svg/${encoded}`;
  } catch (e) {
    return null;
  }
}

/**
 * Mermaid 코드를 <img> 태그로 변환 (kroki.io GET URL 참조)
 * @param {string} code - Mermaid 코드
 * @param {string} altText - alt 속성 텍스트
 * @returns {string|null} <img> 태그 또는 null
 */
function mermaidToImgTag(code, altText) {
  const url = mermaidToKrokiUrl(code);
  if (!url) return null;
  const safeAlt = altText.replace(/"/g, '&quot;');
  return `<img src="${url}" alt="${safeAlt}" width="800" height="auto" style="max-width:100%;height:auto;margin:16px 0;" />`;
}

// 글 내 Unsplash 이미지 중복 방지용 Set
const usedPhotoIds = new Set();
let unsplashApiCalls = 0;

// === Step 1: [MERMAID]...[/MERMAID] 마커 추출 ===
// LLM이 JSON 안에서 ```mermaid 대신 [MERMAID]...[/MERMAID] 마커를 사용하도록 지시됨
// (JSON fence 충돌 및 Gemini 응답 truncation 방지)
const mermaidRegex = /\[MERMAID\]([\s\S]*?)\[\/MERMAID\]/g;
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

// === Step 2: 각 [MERMAID] 블록 → kroki.io URL <img> 태그 (역순 치환) ===
for (let i = blocks.length - 1; i >= 0; i--) {
  const block = blocks[i];
  const firstLine = block.code.split('\n')[0].trim();
  const altText = `Mermaid diagram: ${firstLine}`;
  const imgTag = mermaidToImgTag(block.code, altText);

  if (imgTag) {
    updatedContent =
      updatedContent.substring(0, block.index) +
      '\n' + imgTag + '\n' +
      updatedContent.substring(block.index + block.full.length);
    renderedCount++;
  } else {
    // URL 생성 실패 시 원본 코드블록 유지 (graceful degradation)
    failedCount++;
  }
}

// === Step 3: <!-- IMAGE: keyword --> 마커 → Unsplash <figure> (역순 치환) ===
const imageMarkerRegex = /<!-- IMAGE:\s*(.+?)\s*-->/g;
const imageMarkers = [];

while ((match = imageMarkerRegex.exec(updatedContent)) !== null) {
  imageMarkers.push({
    full: match[0],
    keyword: match[1].trim(),
    index: match.index,
  });
}

let sectionImagesInjected = 0;

for (let i = imageMarkers.length - 1; i >= 0; i--) {
  const marker = imageMarkers[i];

  if (sectionImagesInjected >= MAX_SECTION_IMAGES) {
    // 초과분은 마커만 제거
    updatedContent =
      updatedContent.substring(0, marker.index) +
      updatedContent.substring(marker.index + marker.full.length);
    continue;
  }

  unsplashApiCalls++;
  const photo = await searchUnsplash(marker.keyword, usedPhotoIds);

  if (photo) {
    usedPhotoIds.add(photo.id);
    const figureTag = unsplashFigureTag(photo, marker.keyword, false);
    updatedContent =
      updatedContent.substring(0, marker.index) +
      '\n' + figureTag + '\n' +
      updatedContent.substring(marker.index + marker.full.length);
    sectionImagesInjected++;
  } else {
    // 실패 시 마커 제거 (graceful degradation)
    updatedContent =
      updatedContent.substring(0, marker.index) +
      updatedContent.substring(marker.index + marker.full.length);
  }
}

// === Step 4: Hero 이미지 + thumbnail_url — Unsplash 검색 ===
let thumbnailUrl = '';
let hasHeroImage = false;

if (UNSPLASH_KEY) {
  const keywords = extractThumbnailKeywords();
  for (const kw of keywords) {
    unsplashApiCalls++;
    const result = await searchUnsplash(kw, usedPhotoIds);
    if (result) {
      usedPhotoIds.add(result.id);

      // Hero: 첫 H2 앞에 <figure> 삽입
      const firstH2 = updatedContent.match(/^## /m);
      if (firstH2) {
        const h2Index = updatedContent.indexOf(firstH2[0]);
        const heroFigure = unsplashFigureTag(result, title, true);
        updatedContent =
          updatedContent.substring(0, h2Index) +
          heroFigure + '\n\n' +
          updatedContent.substring(h2Index);
        hasHeroImage = true;
      }

      // Thumbnail: small URL (OG 이미지)
      thumbnailUrl = result.thumb;
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
      method: 'hybrid_mermaid_unsplash',
      mermaid_found: blocks.length,
      mermaid_rendered: renderedCount,
      mermaid_failed: failedCount,
      section_images_injected: sectionImagesInjected,
      has_hero_image: hasHeroImage,
      unsplash_api_calls: unsplashApiCalls,
      has_unsplash_key: !!UNSPLASH_KEY,
    },
  },
};
