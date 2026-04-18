from __future__ import annotations

from typing import Optional, Tuple

from store import InMemoryStore


class RateLimiter:
    def __init__(self, store: InMemoryStore):
        self.store = store

    async def can_submit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """Check if user can submit. Returns (allowed, denial_message)."""
        allowed = await self.store.check_submission_rate(user_id)
        if not allowed:
            return False, (
                "We love the energy! You've hit your submission cap for today "
                "(3 per 24 hours). Save this link and drop it tomorrow!"
            )
        return True, None

    async def can_earn_submission_points(
        self, user_id: str, proposed: int
    ) -> Tuple[bool, int]:
        """Check weekly point cap. Returns (allowed, points_to_award).
        If partially over cap, returns reduced amount."""
        allowed = await self.store.check_weekly_points(user_id, proposed)
        if allowed:
            return True, proposed
        # Calculate remaining room
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        iso_week = now.isocalendar()[1]
        current = self.store._user_weekly_points[user_id][iso_week]
        remaining = max(0, 50 - current)
        if remaining > 0:
            return True, remaining
        return False, 0

    async def can_earn_reaction_points(self, user_id: str) -> bool:
        """Check if user can earn points for reacting (5/day cap)."""
        return await self.store.check_daily_reaction_earnings(user_id)
