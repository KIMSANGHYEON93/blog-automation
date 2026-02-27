/**
 * Node 7b: 코드 블록 기초 포맷 검사
 * 언어 태그 존재 여부, 닫히지 않은 블록 감지
 */

const content = $input.first().json.content;

const issues = [];

// 1. 코드 블록 추출 (열기/닫기 쌍)
const openBlocks = (content.match(/```/g) || []).length;
if (openBlocks % 2 !== 0) {
  issues.push("닫히지 않은 코드 블록 존재");
}

// 2. 언어 태그 없는 코드 블록 감지
const codeBlockRegex = /```(\w*)\n/g;
let match;
let blockCount = 0;
let noTagCount = 0;

while ((match = codeBlockRegex.exec(content)) !== null) {
  blockCount++;
  if (!match[1]) {
    noTagCount++;
  }
}

if (noTagCount > 0) {
  issues.push(`언어 태그 없는 코드 블록: ${noTagCount}/${blockCount}건`);
}

// 3. 허용 언어 태그 검증
const allowedLangs = [
  "powershell", "bash", "cmd", "python", "json", "xml", "yaml",
  "csharp", "javascript", "html", "sql", "text", "plaintext",
  "shell", "ps1", "bat",
];
const langRegex = /```(\w+)/g;
let langMatch;
while ((langMatch = langRegex.exec(content)) !== null) {
  const lang = langMatch[1].toLowerCase();
  if (!allowedLangs.includes(lang)) {
    issues.push(`비표준 언어 태그: ${langMatch[1]}`);
  }
}

const passed = issues.length === 0;

return [{
  json: {
    ...$input.first().json,
    code_lint: {
      passed,
      block_count: blockCount,
      issues,
    }
  }
}];
