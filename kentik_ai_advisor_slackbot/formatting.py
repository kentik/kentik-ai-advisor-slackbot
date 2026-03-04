"""Markdown-to-Slack formatting conversion utilities."""

import re

from .config import KENTIK_API_URL


def format_markdown_for_slack(markdown: str) -> str:
    """Convert AI Advisor markdown to Slack mrkdwn format.

    Args:
        markdown: Markdown text from AI Advisor

    Returns:
        Slack-formatted text
    """
    text = markdown

    # Convert double-star bold to single-star bold (**text** → *text*)
    # Slack uses single stars for bold, markdown uses double stars
    # This is not needed for Slack Assistant apps
    # text = re.sub(r"\*\*(.*?)\*\*", r"*\1*", text)

    # Convert headers to bold
    text = re.sub(r"^#### (.*?)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.*?)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.*?)$", r"*\1*", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.*?)$", r"*\1*", text, flags=re.MULTILINE)

    # NOW convert markdown links to Slack format (after tables are processed)
    text = _convert_links_to_slack_format(text)

    return text


def _convert_links_to_slack_format(text: str) -> str:
    """Convert markdown links to Slack format.

    Args:
        text: Text containing markdown links

    Returns:
        Text with Slack-formatted links
    """
    portal_url = get_portal_url()

    def replace_link(match: re.Match[str]) -> str:
        link_text = match.group(1)
        link_path = match.group(2)
        # Add portal URL if path starts with /v4/
        if link_path.startswith("/v4/"):
            full_url = f"{portal_url}{link_path}"
            return f"<{full_url}|{link_text}>"
        # For other paths, use as-is
        elif link_path.startswith("http"):
            return f"<{link_path}|{link_text}>"
        else:
            # Relative path, add portal URL
            full_url = f"{portal_url}{link_path}"
            return f"<{full_url}|{link_text}>"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, text)


def get_portal_url() -> str:
    """Get Kentik portal URL based on API URL.

    Returns:
        Portal URL (US or EU cluster)
    """
    api_url = KENTIK_API_URL.lower()
    if "kentik.eu" in api_url or ".eu" in api_url:
        return "https://portal.kentik.eu"
    return "https://portal.kentik.com"
