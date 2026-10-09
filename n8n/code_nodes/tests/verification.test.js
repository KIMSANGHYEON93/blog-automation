// 검증 파서 회귀 테스트 — 누락·잘못된 타입·범위 밖 점수를 통과로 처리하지 않는다
// 실행: node --test "n8n/code_nodes/tests/*.test.js"
const test = require('node:test');
const assert = require('node:assert/strict');

const tistory = require('../parse_verification.js');
const naver = require('../naver/parse_verification_naver.js');

const TISTORY_ALL_TRUE = {
  is_accurate: true, is_logical: true, is_complete: true, is_useful: true, is_in_depth: true,
  quality_score: 85, reason: 'ok',
};
const NAVER_OK_CTX = { structurePassed: true, structureIssues: [], searchOk: true };
const NAVER_ALL_TRUE = {
  ...TISTORY_ALL_TRUE,
  no_fabricated_experience: true, natural_keyword_use: true, has_unique_info: true, mobile_readable: true,
};

test('티스토리: 모든 항목이 명시적 true이고 점수가 70 이상이면 통과', () => {
  const v = tistory.judgeVerification(TISTORY_ALL_TRUE);
  assert.equal(v.passed, true);
  assert.equal(v.quality_score, 85);
});

test('티스토리: 신규 항목 누락을 true로 채우지 않는다 (is_accurate·is_logical·quality_score만 있는 응답)', () => {
  const v = tistory.judgeVerification({ is_accurate: true, is_logical: true, quality_score: 80 });
  assert.equal(v.passed, false);
  assert.equal(v.is_complete, null);
  assert.equal(v.is_useful, null);
  assert.equal(v.is_in_depth, null);
  assert.match(v.reason, /is_complete/);
  assert.match(v.reason, /누락/);
});

test('티스토리: 문자열 "true"는 boolean이 아니다', () => {
  const v = tistory.judgeVerification({ ...TISTORY_ALL_TRUE, is_useful: 'true' });
  assert.equal(v.passed, false);
  assert.equal(v.is_useful, null);
  assert.match(v.reason, /is_useful/);
});

for (const score of [150, -1, 85.5, '85', null, undefined, NaN]) {
  test(`티스토리: 비정상 점수 ${String(score)}는 검수필요`, () => {
    const v = tistory.judgeVerification({ ...TISTORY_ALL_TRUE, quality_score: score });
    assert.equal(v.passed, false);
    assert.match(v.reason, /quality_score/);
  });
}

test('티스토리: 명시적 false 항목은 미통과 사유에 남는다', () => {
  const v = tistory.judgeVerification({ ...TISTORY_ALL_TRUE, is_in_depth: false });
  assert.equal(v.passed, false);
  assert.equal(v.is_in_depth, false);
  assert.match(v.reason, /is_in_depth/);
});

test('티스토리: 70점 미만은 미통과', () => {
  const v = tistory.judgeVerification({ ...TISTORY_ALL_TRUE, quality_score: 69 });
  assert.equal(v.passed, false);
});

test('티스토리: LLM JSON 파서는 후행 쉼표를 복구한다', () => {
  const r = tistory.parseLlmJson('결과:\n{"quality_score": 80, "reason": "ok",}\n끝');
  assert.equal(r.quality_score, 80);
});

test('스키마: 네이버 기본 항목은 티스토리 필수 항목과 같다', () => {
  assert.deepEqual(naver.BASE_CHECKS, tistory.REQUIRED_CHECKS);
});

test('네이버: 범위 밖 점수(150)는 통과하지 못한다', () => {
  const v = naver.judgeNaver({ ...NAVER_ALL_TRUE, quality_score: 150 }, NAVER_OK_CTX);
  assert.equal(v.passed, false);
  assert.match(v.reason, /quality_score/);
});

test('네이버: 문자열 점수·소수 점수는 통과하지 못한다', () => {
  for (const score of ['90', 90.5]) {
    const v = naver.judgeNaver({ ...NAVER_ALL_TRUE, quality_score: score }, NAVER_OK_CTX);
    assert.equal(v.passed, false, String(score));
  }
});

test('네이버: 누락·잘못된 타입 항목은 null로 남기고 사유에 형식 오류를 적는다', () => {
  const { mobile_readable: _omit, ...missing } = NAVER_ALL_TRUE;
  const v = naver.judgeNaver({ ...missing, has_unique_info: 'yes' }, NAVER_OK_CTX);
  assert.equal(v.passed, false);
  assert.equal(v.mobile_readable, null);
  assert.equal(v.has_unique_info, null);
  assert.match(v.reason, /누락/);
  assert.match(v.reason, /mobile_readable/);
});

test('네이버: 모두 정상이면 통과', () => {
  const v = naver.judgeNaver(NAVER_ALL_TRUE, NAVER_OK_CTX);
  assert.equal(v.passed, true);
  assert.equal(v.mobile_readable, true);
});
