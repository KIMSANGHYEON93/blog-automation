## 제로 트러스트란?

제로 트러스트(Zero Trust)는 '아무도 신뢰하지 않는다'는 원칙을 기반으로 한 보안 모델입니다. 기존의 경계 기반 보안(Perimeter Security)과 달리, 네트워크 내부/외부를 구분하지 않고 모든 접근을 검증합니다.

### 핵심 원칙

| 원칙 | 설명 |
|------|------|
| 최소 권한 (Least Privilege) | 업무에 필요한 최소한의 접근 권한만 부여 |
| 지속 검증 (Continuous Verification) | 한 번 인증으로 끝나지 않고 지속적으로 검증 |
| 마이크로 세그멘테이션 | 네트워크를 작은 구역으로 나누어 피해 범위 최소화 |

### 기업 환경 적용 예시

```powershell
# Azure AD 조건부 액세스 정책 확인
Get-AzureADMSConditionalAccessPolicy | Format-Table DisplayName, State

# 특정 사용자의 로그인 이벤트 조회
Get-AzureADAuditSignInLogs -Filter "userPrincipalName eq 'admin@contoso.com'"
```

<!-- IMAGE_PLACEHOLDER: 제로 트러스트 아키텍처 다이어그램 -->

### FAQ

**Q: 제로 트러스트와 VPN의 차이점은?**
A: VPN은 네트워크 경계를 신뢰하는 반면, 제로 트러스트는 경계 없이 모든 접근을 매번 검증합니다.

**Q: 중소기업도 도입할 수 있나요?**
A: 네, Azure AD 조건부 액세스, Google Workspace 보안 설정 등 클라우드 도구로 단계적 도입이 가능합니다.
