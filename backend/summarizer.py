from __future__ import annotations

import re
from typing import List, Optional

import anthropic
import httpx
from bs4 import BeautifulSoup


def extract_url(text: str) -> Optional[str]:
    """Extract the first URL from Slack message text.
    Slack wraps URLs as <https://example.com> or <https://example.com|display text>."""
    # Slack-formatted URLs
    match = re.search(r"<(https?://[^|>]+)(?:\|[^>]*)?>", text)
    if match:
        return match.group(1)
    # Plain URLs
    match = re.search(r"(https?://\S+)", text)
    if match:
        return match.group(1)
    return None


class URLSummarizer:
    def __init__(self, api_key: str):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def fetch_url_content(self, url: str) -> Optional[str]:
        """Fetch URL and extract readable text from HTML."""
        try:
            async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=True
            ) as http:
                resp = await http.get(url, headers={"User-Agent": "MammothBot/1.0"})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # Remove script/style tags
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                # Collapse whitespace
                text = re.sub(r"\n{3,}", "\n\n", text)
                return text[:10000]  # Truncate to stay within limits
        except Exception as e:
            print(f"[Summarizer] Failed to fetch {url}: {e}")
            return None

    async def summarize(self, url: str) -> List[str]:
        """Fetch URL content and generate 3-bullet ESG-focused summary."""
        content = await self.fetch_url_content(url)
        if not content:
            return ["Could not fetch article content. The URL may be inaccessible."]

        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize this article in exactly 3 concise bullet points "
                            "focused on ESG/sustainability relevance. Each bullet should "
                            "be one sentence. Return ONLY the 3 bullets, one per line, "
                            "prefixed with a bullet character.\n\n"
                            f"Article content:\n{content}"
                        ),
                    }
                ],
            )
            raw = response.content[0].text.strip()
            # Parse bullets - strip common prefix characters and take first 3 non-empty lines
            lines = [
                line.strip().lstrip("•-*0123456789.) ").strip()
                for line in raw.split("\n")
                if line.strip()
            ]
            bullets = [l for l in lines if l][:3]
            return bullets if bullets else ["Summary could not be parsed."]
        except Exception as e:
            print(f"[Summarizer] Claude API error: {e}")
            return ["AI summary temporarily unavailable."]
