"""Config — Environment-based settings with fail-fast validation."""
import os
from dataclasses import dataclass


@dataclass
class Config:
    kakao_id: str
    kakao_pw: str
    tistory_blog: str
    google_creds: str
    sheet_name: str
    max_posts: int
    headless: bool
    min_delay: int
    max_delay: int
    contact_email: str
    owner_name: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            kakao_id=os.getenv("KAKAO_ID", ""),
            kakao_pw=os.getenv("KAKAO_PW", ""),
            tistory_blog=os.getenv("TISTORY_BLOG", ""),
            google_creds=os.getenv("GOOGLE_CREDS", "credentials.json"),
            sheet_name=os.getenv("SHEET_NAME", "keyword_calendar_v2"),
            max_posts=int(os.getenv("MAX_POSTS", "5")),
            headless=os.getenv("HEADLESS", "true").lower() == "true",
            min_delay=int(os.getenv("MIN_DELAY", "300")),
            max_delay=int(os.getenv("MAX_DELAY", "900")),
            contact_email=os.getenv("CONTACT_EMAIL", ""),
            owner_name=os.getenv("OWNER_NAME", ""),
        )

    def validate(self) -> None:
        """필수 환경 변수 누락 시 즉시 중단 (Fail-fast)."""
        missing = []
        if not self.kakao_id:
            missing.append("KAKAO_ID")
        if not self.kakao_pw:
            missing.append("KAKAO_PW")
        if not self.tistory_blog:
            missing.append("TISTORY_BLOG")
        if not os.path.exists(self.google_creds):
            missing.append(f"GOOGLE_CREDS (파일 없음: {self.google_creds})")
        if missing:
            raise OSError(f"필수 환경 변수 누락: {', '.join(missing)}")

    def validate_pages(self) -> None:
        """--publish-pages 전용 검증. GOOGLE_CREDS 불필요."""
        missing = []
        if not self.kakao_id:
            missing.append("KAKAO_ID")
        if not self.kakao_pw:
            missing.append("KAKAO_PW")
        if not self.tistory_blog:
            missing.append("TISTORY_BLOG")
        if not self.contact_email:
            missing.append("CONTACT_EMAIL")
        if not self.owner_name:
            missing.append("OWNER_NAME")
        if missing:
            raise OSError(
                f"--publish-pages 필수 환경 변수 누락: {', '.join(missing)}"
            )
