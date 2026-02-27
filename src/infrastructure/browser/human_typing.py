"""human_type — Bot detection evasion via simulated human typing."""
import random
import time


def human_type(sb, selector: str, text: str,
               min_delay: float = 0.05, max_delay: float = 0.15) -> None:
    """봇 탐지 회피를 위한 인간형 타이핑 시뮬레이션."""
    sb.click(selector)
    for char in text:
        sb.type(selector, char)
        time.sleep(random.uniform(min_delay, max_delay))
