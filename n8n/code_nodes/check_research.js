/**
 * Check Research — Research 응답의 검색 횟수를 세고 재시도 요청을 정한다
 * Mode: runOnceForEachItem
 * 입력: Research Request(HTTP) 응답. 원본 항목은 $('Build Research Request')에서 가져온다
 * 출력: 원본 항목 + _research_retry, _research_retry_url, _research_retry_body
 *
 * 재시도는 IF로 가르지 않는다. 두 갈래를 같은 노드로 다시 모으면 n8n(v1)이 그 노드를
 * 갈래마다 한 번씩 실행해 뒤 노드가 두 번 돈다(Build Verify Request 사례).
 * 대신 Research Request (Retry)가 모든 항목에 대해 한 번 실행되고,
 * 검색한 항목은 생성 없이 과금되지 않는 countTokens로만 지나간다.
 */

function countSearchQueries(response) {
  const queries = response?.candidates?.[0]?.groundingMetadata?.webSearchQueries;
  return Array.isArray(queries) ? queries.length : 0;
}

function retryTarget(needsRetry, url, body) {
  if (needsRetry) return { url, body };
  return { url: url.replace(/:generateContent$/, ':countTokens'), body: { contents: body.contents } };
}

if (typeof $input === 'undefined') {
  module.exports = { countSearchQueries, retryTarget };
  return;
}

const base = $('Build Research Request').item.json;
const needsRetry = countSearchQueries($input.item.json) === 0;
const target = retryTarget(needsRetry, base._research_url, base._research_body);

return {
  json: {
    ...base,
    _research_retry: needsRetry,
    _research_retry_url: target.url,
    _research_retry_body: target.body,
  },
};
