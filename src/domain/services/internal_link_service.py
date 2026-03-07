"""InternalLinkService — Hub-spoke internal link selection domain service."""
from __future__ import annotations

from collections import Counter

from src.domain.entities.post import Post


class InternalLinkService:
    """Selects internal links using hub-spoke model with keyword overlap."""

    MAX_LINKS = 5
    MAX_HUBS = 3

    def identify_hubs(self, published_posts: list[Post]) -> list[Post]:
        """Find top 3 hub posts — most referenced by other posts' keywords.

        A post is a hub candidate if its keyword appears in other posts'
        internal_link_keywords lists. Posts with the highest mention count
        are selected as hubs.
        """
        if not published_posts:
            return []

        mention_count: Counter[int] = Counter()
        for post in published_posts:
            for kw in post.internal_link_keywords:
                for candidate in published_posts:
                    if candidate.row_index == post.row_index:
                        continue
                    if not candidate.published_url:
                        continue
                    if kw.lower() in candidate.keyword.lower():
                        mention_count[candidate.row_index] += 1

        if not mention_count:
            return []

        hub_row_indices = [
            row_idx for row_idx, _ in mention_count.most_common(self.MAX_HUBS)
        ]
        hub_map = {p.row_index: p for p in published_posts}
        return [hub_map[idx] for idx in hub_row_indices if idx in hub_map]

    def select_links(
        self,
        target: Post,
        published_posts: list[Post],
        hubs: list[Post],
    ) -> list[Post]:
        """Select up to 5 related posts for the target using priority scoring.

        Priority:
        1. Hub-to-hub: if target is a hub, other hubs get bonus
        2. Hub link: if target's keywords overlap with hub's keyword
        3. Keyword overlap: Jaccard similarity scoring
        4. Category fallback: same category > different category
        """
        candidates = [
            p for p in published_posts
            if p.row_index != target.row_index and p.published_url
        ]
        if not candidates:
            return []

        hub_indices = {h.row_index for h in hubs}
        target_is_hub = target.row_index in hub_indices
        target_kws = {k.lower() for k in target.internal_link_keywords}

        scored: list[tuple[float, int, Post]] = []
        for idx, cand in enumerate(candidates):
            score = 0.0

            # Priority 1: Hub-to-hub bonus
            if target_is_hub and cand.row_index in hub_indices:
                score += 100.0

            # Priority 2: Hub link — target's keywords mention a hub
            if cand.row_index in hub_indices and target_kws:
                cand_kw_lower = cand.keyword.lower()
                if any(kw in cand_kw_lower or cand_kw_lower in kw for kw in target_kws):
                    score += 50.0

            # Priority 3: Keyword overlap (Jaccard similarity)
            cand_kws = {k.lower() for k in cand.internal_link_keywords}
            if target_kws and cand_kws:
                intersection = target_kws & cand_kws
                union = target_kws | cand_kws
                jaccard = len(intersection) / len(union) if union else 0.0
                score += jaccard * 30.0

            # Priority 4: Category fallback
            if cand.category and target.category:
                if cand.category == target.category:
                    score += 10.0
                else:
                    score += 5.0

            scored.append((score, idx, cand))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [cand for _, _, cand in scored[:self.MAX_LINKS]]
