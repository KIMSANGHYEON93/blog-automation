"""Credentials — Value Object for authentication info."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Credentials:
    kakao_id: str
    kakao_pw: str
    tistory_blog: str

    def is_complete(self) -> bool:
        return bool(self.kakao_id and self.kakao_pw and self.tistory_blog)
