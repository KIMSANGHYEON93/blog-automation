/**
 * Inject Images — Unsplash 이미지 자동 삽입
 * Mode: runOnceForEachItem
 * Parse JSON Response와 Validate Structure 사이에 배치
 * 입력: 파싱된 JSON (content 필드 포함)
 * 출력: 이미지가 삽입된 content + thumbnail_url + image_injection 메타데이터
 */

const content = $input.item.json.content || '';
const title = $input.item.json.title || '';
const UNSPLASH_KEY = $env.UNSPLASH_ACCESS_KEY;
const helpers = this.helpers;

/**
 * IT 기술 키워드 → Unsplash 검색 친화 키워드 매핑
 * Terraform, Jenkins 등 특정 기술 이름은 Unsplash에서 0건이므로
 * 시각적으로 관련 있는 일반 키워드로 변환
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
 * H2 텍스트에서 Unsplash 검색용 키워드 후보 배열을 반환
 * 1순위: 추출된 영문 키워드
 * 2순위: broadening 매핑 적용 키워드
 * 3순위: 제목에서 추출한 영문
 * 4순위: 범용 IT 이미지 키워드
 */
function extractSearchKeywords(h2Text) {
  const candidates = [];

  // H2에서 영문 단어 추출
  const engWords = h2Text.match(/[A-Za-z0-9][\w./-]*/g) || [];
  if (engWords.length > 0) {
    candidates.push(engWords.join(' '));
  }

  // broadening 매핑 적용 (추출된 영문 단어 중 매핑이 있으면 추가)
  const lowerText = h2Text.toLowerCase();
  for (const [tech, broad] of Object.entries(KEYWORD_BROADENING)) {
    if (lowerText.includes(tech)) {
      candidates.push(broad);
      break;
    }
  }

  // 제목에서 영문 + broadening
  const titleEng = title.match(/[A-Za-z0-9][\w./-]*/g) || [];
  if (titleEng.length > 0) {
    const titleKeyword = titleEng.join(' ');
    if (!candidates.includes(titleKeyword)) {
      candidates.push(titleKeyword);
    }
    const lowerTitle = title.toLowerCase();
    for (const [tech, broad] of Object.entries(KEYWORD_BROADENING)) {
      if (lowerTitle.includes(tech) && !candidates.includes(broad)) {
        candidates.push(broad);
        break;
      }
    }
  }

  // 최후 fallback: 범용 IT 이미지
  candidates.push('technology software development');

  return candidates;
}

/**
 * Unsplash API에서 이미지 검색 (단일 키워드)
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
      url: photo.urls.regular,
      alt: photo.alt_description || keyword,
      attribution: `Photo by [${photo.user.name}](${photo.user.links.html}?utm_source=blog_automation&utm_medium=referral) on [Unsplash](https://unsplash.com/?utm_source=blog_automation&utm_medium=referral)`,
      thumb: photo.urls.small,
    };
  } catch (e) {
    return null;
  }
}

/**
 * 키워드 후보 배열을 순서대로 시도하여 첫 번째 성공 결과 반환
 */
async function searchUnsplashWithFallback(keywords) {
  for (const kw of keywords) {
    const result = await searchUnsplashSingle(kw);
    if (result) return { ...result, usedKeyword: kw };
  }
  return null;
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
    // 마커 키워드 + broadening 후보로 검색
    const markerCandidates = [marker.keyword];
    const lk = marker.keyword.toLowerCase();
    for (const [tech, broad] of Object.entries(KEYWORD_BROADENING)) {
      if (lk.includes(tech)) { markerCandidates.push(broad); break; }
    }
    markerCandidates.push('technology software development');
    const image = await searchUnsplashWithFallback(markerCandidates);

    if (image) {
      const imageBlock = `\n![${image.alt}](${image.url})\n\n*${image.attribution}*\n`;
      updatedContent =
        updatedContent.substring(0, marker.index) +
        imageBlock +
        updatedContent.substring(marker.index + marker.full.length);
      injectedCount++;
      usedKeywords.push(image.usedKeyword);

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
    // H2 텍스트에서 영문 키워드 추출 (Unsplash는 영문 검색이 결과가 좋음)
    const rawText = h2.text.replace(/^##\s*/, '').trim();
    const keywords = extractSearchKeywords(rawText);
    const image = await searchUnsplashWithFallback(keywords);

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
      usedKeywords.push(image.usedKeyword);

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
