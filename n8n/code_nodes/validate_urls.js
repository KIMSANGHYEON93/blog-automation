/**
 * Node 7a: URL 정규식 + 형식 검증
 * 본문 내 URL이 유효한 형식인지 검사 (실제 HTTP 요청 없이 정규식만)
 * DNS 조회는 n8n에서 불가 → 정규식 + 도메인 패턴 검증
 */

const content = $input.first().json.content;

// URL 추출
const urlRegex = /https?:\/\/[^\s\)\]"'<>]+/g;
const urls = content.match(urlRegex) || [];

const issues = [];

for (const url of urls) {
  // 1. 깨진 URL 패턴 감지
  if (url.includes("...") || url.includes(" ")) {
    issues.push(`깨진 URL: ${url}`);
    continue;
  }

  // 2. 플레이스홀더 URL 감지 (허용 — contoso.com 마스킹)
  if (url.includes("contoso.com") || url.includes("example.com")) {
    continue; // 마스킹 URL은 OK
  }

  // 3. 유효하지 않은 TLD 감지
  try {
    const domain = new URL(url).hostname;
    if (!domain.includes(".")) {
      issues.push(`유효하지 않은 도메인: ${url}`);
    }
  } catch (e) {
    issues.push(`URL 파싱 실패: ${url}`);
  }
}

const passed = issues.length === 0;

return [{
  json: {
    ...$input.first().json,
    url_validation: {
      passed,
      total_urls: urls.length,
      issues,
    }
  }
}];
