/**
 * Get Access Token — Service Account JWT → Google OAuth2 Access Token 교환
 * Mode: runOnceForEachItem
 * 위치: Batch Keywords → [Get Access Token] → Google Ads API
 * 입력: 배치 키워드 데이터
 * 출력: accessToken 필드가 추가된 아이템
 *
 * 인증 우선순위:
 * 1. GOOGLE_SERVICE_ACCOUNT_EMAIL + GOOGLE_PRIVATE_KEY (서비스 계정 JWT, 권장)
 * 2. GOOGLE_ADS_ACCESS_TOKEN (정적 토큰, 테스트/개발용만)
 */

const crypto = require('crypto');

const SCOPES = 'https://www.googleapis.com/auth/adwords';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';

// 환경변수에서 서비스 계정 정보 읽기
const serviceAccountEmail = $env.GOOGLE_SERVICE_ACCOUNT_EMAIL || '';
const privateKey = ($env.GOOGLE_PRIVATE_KEY || '').replace(/\\n/g, '\n');

if (!serviceAccountEmail || !privateKey) {
  // Fallback: 정적 access token (테스트/개발용)
  const accessToken = $env.GOOGLE_ADS_ACCESS_TOKEN || '';
  if (!accessToken) {
    throw new Error(
      'Google Ads 인증 실패: GOOGLE_SERVICE_ACCOUNT_EMAIL/GOOGLE_PRIVATE_KEY ' +
      '또는 GOOGLE_ADS_ACCESS_TOKEN 환경변수를 설정하세요.'
    );
  }
  return { json: { ...$json, accessToken } };
}

// JWT Header
const header = Buffer.from(JSON.stringify({
  alg: 'RS256',
  typ: 'JWT'
})).toString('base64url');

// JWT Claim Set
const now = Math.floor(Date.now() / 1000);
const claimSet = Buffer.from(JSON.stringify({
  iss: serviceAccountEmail,
  scope: SCOPES,
  aud: TOKEN_URL,
  iat: now,
  exp: now + 3600
})).toString('base64url');

// Sign
const signInput = `${header}.${claimSet}`;
const signer = crypto.createSign('RSA-SHA256');
signer.update(signInput);
const signature = signer.sign(privateKey, 'base64url');

const jwt = `${signInput}.${signature}`;

// Token 교환
const response = await this.helpers.httpRequest({
  method: 'POST',
  url: TOKEN_URL,
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`,
  returnFullResponse: true,
  json: false
});

const tokenData = JSON.parse(response.body);
if (!tokenData.access_token) {
  const errCode = tokenData.error || 'unknown';
  throw new Error(
    `Access token 발급 실패 (error=${errCode}). ` +
    '환경변수 GOOGLE_SERVICE_ACCOUNT_EMAIL/GOOGLE_PRIVATE_KEY를 확인하세요.'
  );
}

return { json: { ...$json, accessToken: tokenData.access_token } };
