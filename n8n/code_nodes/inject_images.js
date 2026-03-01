/**
 * Inject Images — Unsplash 이미지 자동 삽입
 * Mode: runOnceForEachItem
 * Parse JSON Response와 Validate Structure 사이에 배치
 * 입력: 파싱된 JSON (content 필드 포함)
 * 출력: 이미지가 삽입된 content + thumbnail_url + image_injection 메타데이터
 */

const content = $input.item.json.content || '';
const UNSPLASH_KEY = $env.UNSPLASH_ACCESS_KEY;
const helpers = this.helpers;

/**
 * Unsplash API에서 이미지 검색 (n8n Code Node용 — this.helpers.httpRequest 사용)
 * @param {string} keyword - 검색 키워드
 * @returns {Promise<{url: string, alt: string, attribution: string}|null>}
 */
async function searchUnsplash(keyword) {
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

    // 랜덤하게 상위 4개 중 1개 선택
    const idx = Math.floor(Math.random() * Math.min(data.results.length, 4));
    const photo = data.results[idx];

    return {
      url: photo.urls.regular,
      alt: photo.alt_description || keyword,
      attribution: `Photo by [${photo.user.name}](${photo.user.links.html}?utm_source=blog_automation&utm_medium=referral) on [Unsplash](https://unsplash.com/?utm_source=blog_automation&utm_medium=referral)`,
      thumb: photo.urls.small,
    };
  } catch (e) {
    return null;
  }
}

// === Step 1: IMAGE 마커 탐색 ===
const markerRegex = /<!-- IMAGE:\s*(.+?)\s*-->/g;
const markers = [];
let match;

while ((match = markerRegex.exec(content)) !== null) {
  markers.push({
    full: match[0],
    keyword: match[1],
    index: match.index,
  });
}

let updatedContent = content;
let injectedCount = 0;
let thumbnailUrl = '';
const usedKeywords = [];

if (markers.length > 0) {
  // === Step 2: 마커 기반 이미지 삽입 ===
  // 역순으로 처리 (인덱스 밀림 방지)
  for (let i = markers.length - 1; i >= 0; i--) {
    const marker = markers[i];
    const image = await searchUnsplash(marker.keyword);

    if (image) {
      const imageBlock = `\n![${image.alt}](${image.url})\n\n*${image.attribution}*\n`;
      updatedContent =
        updatedContent.substring(0, marker.index) +
        imageBlock +
        updatedContent.substring(marker.index + marker.full.length);
      injectedCount++;
      usedKeywords.push(marker.keyword);

      if (!thumbnailUrl) {
        thumbnailUrl = image.thumb || image.url;
      }
    } else {
      // API 실패 시 마커만 제거 (graceful degradation)
      updatedContent =
        updatedContent.substring(0, marker.index) +
        updatedContent.substring(marker.index + marker.full.length);
    }
  }
} else {
  // === Step 3: H2 기반 fallback ===
  const h2Regex = /^## .+$/gm;
  const h2Matches = [];
  let h2Match;

  while ((h2Match = h2Regex.exec(content)) !== null) {
    // FAQ 섹션 제외
    if (/FAQ/i.test(h2Match[0]) || /자주\s*묻는/i.test(h2Match[0])) continue;
    h2Matches.push({
      text: h2Match[0],
      index: h2Match.index,
      length: h2Match[0].length,
    });
  }

  // 상위 4개 H2만 처리
  const targetH2s = h2Matches.slice(0, 4);

  // 역순 처리
  for (let i = targetH2s.length - 1; i >= 0; i--) {
    const h2 = targetH2s[i];
    // H2 텍스트에서 키워드 추출 (## 제거)
    const keyword = h2.text.replace(/^##\s*/, '').trim();
    const image = await searchUnsplash(keyword);

    if (image) {
      // H2 뒤 첫 문단 이후에 삽입
      const afterH2 = h2.index + h2.length;
      // 다음 빈 줄(문단 구분) 찾기
      const nextParagraphEnd = updatedContent.indexOf('\n\n', afterH2);
      const insertPos =
        nextParagraphEnd !== -1
          ? nextParagraphEnd + 2
          : afterH2 + 1;

      const imageBlock = `\n![${image.alt}](${image.url})\n\n*${image.attribution}*\n`;
      updatedContent =
        updatedContent.substring(0, insertPos) +
        imageBlock +
        updatedContent.substring(insertPos);
      injectedCount++;
      usedKeywords.push(keyword);

      if (!thumbnailUrl) {
        thumbnailUrl = image.thumb || image.url;
      }
    }
  }
}

return {
  json: {
    ...$input.item.json,
    content: updatedContent,
    thumbnail_url: thumbnailUrl,
    image_injection: {
      method: markers.length > 0 ? 'marker' : 'h2_fallback',
      markers_found: markers.length,
      images_injected: injectedCount,
      keywords: usedKeywords,
      has_unsplash_key: !!UNSPLASH_KEY,
    },
  },
};
