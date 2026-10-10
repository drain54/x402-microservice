import re
from typing import Optional
from bs4 import BeautifulSoup, Comment
from pydantic import BaseModel, Field

class ExtractRequest(BaseModel):
    url: Optional[str] = Field(None, description="External webpage URL to fetch and convert")
    html: Optional[str] = Field(None, description="Raw HTML string if provided directly")
    include_links: bool = Field(True, description="Whether to preserve Markdown links [text](url)")

class ExtractResponse(BaseModel):
    title: str = Field(..., description="Extracted document title")
    markdown: str = Field(..., description="Clean sanitized markdown text")
    content_length: int = Field(..., description="Character count of extracted markdown")
    source_url: Optional[str] = Field(None, description="Source URL processed")
    tables_found: int = Field(0, description="Empirical count of tables extracted")
    links_found: int = Field(0, description="Empirical count of links extracted")

def html_to_clean_markdown(raw_html: str, base_url: Optional[str] = None, include_links: bool = True) -> tuple[str, str, int, int]:
    """
    Transforms HTML into clean, deterministic LLM-friendly Markdown.
    Removes boilerplate, scripts, styles, adverts, and comments.
    Returns: (title, markdown, tables_count, links_count)
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    # Extract title
    title_tag = soup.find("title")
    title = title_tag.get_text().strip() if title_tag else "Untitled"

    # Remove non-content elements
    for el in soup(["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]):
        el.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Target main content if standard semantic tags exist
    main_el = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"content|article|post|body", re.I)) or soup.body or soup

    tables_count = len(main_el.find_all("table"))
    links_count = len(main_el.find_all("a"))

    def node_to_md(node) -> str:
        if isinstance(node, str):
            return node

        name = getattr(node, "name", None)
        if not name:
            return ""

        # Headings
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(name[1])
            text = "".join(node_to_md(c) for c in node.children).strip()
            return f"\n\n{'#' * level} {text}\n\n"

        # Paragraphs & divs
        if name in ("p", "div", "section"):
            inner = "".join(node_to_md(c) for c in node.children).strip()
            return f"\n\n{inner}\n\n" if inner else ""

        # Line breaks
        if name == "br":
            return "\n"

        # Emphasis
        if name in ("b", "strong"):
            inner = "".join(node_to_md(c) for c in node.children).strip()
            return f"**{inner}**" if inner else ""
        if name in ("i", "em"):
            inner = "".join(node_to_md(c) for c in node.children).strip()
            return f"*{inner}*" if inner else ""

        # Code & Pre
        if name == "code":
            inner = "".join(node_to_md(c) for c in node.children)
            return f"`{inner}`"
        if name == "pre":
            inner = "".join(node_to_md(c) for c in node.children).strip()
            return f"\n\n```\n{inner}\n```\n\n"

        # Blockquote
        if name == "blockquote":
            inner = "".join(node_to_md(c) for c in node.children).strip()
            return f"\n\n> {inner}\n\n"

        # Lists
        if name == "ul":
            items = []
            for li in node.find_all("li", recursive=False):
                li_text = "".join(node_to_md(c) for c in li.children).strip()
                if li_text:
                    items.append(f"- {li_text}")
            return "\n\n" + "\n".join(items) + "\n\n"

        if name == "ol":
            items = []
            for idx, li in enumerate(node.find_all("li", recursive=False), 1):
                li_text = "".join(node_to_md(c) for c in li.children).strip()
                if li_text:
                    items.append(f"{idx}. {li_text}")
            return "\n\n" + "\n".join(items) + "\n\n"

        # Links
        if name == "a":
            text = "".join(node_to_md(c) for c in node.children).strip()
            href = node.get("href", "").strip()
            if include_links and href and text:
                return f"[{text}]({href})"
            return text

        # Tables
        if name == "table":
            rows = node.find_all("tr")
            if not rows:
                return ""
            table_md = []
            headers = [th.get_text().strip() for th in rows[0].find_all(["th", "td"])]
            if headers:
                table_md.append("| " + " | ".join(headers) + " |")
                table_md.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for r in rows[1:]:
                    cells = [td.get_text().strip() for td in r.find_all("td")]
                    if cells:
                        while len(cells) < len(headers):
                            cells.append("")
                        table_md.append("| " + " | ".join(cells[:len(headers)]) + " |")
            return "\n\n" + "\n".join(table_md) + "\n\n"

        # Default: walk children
        return "".join(node_to_md(c) for c in node.children)

    raw_md = node_to_md(main_el)

    # Clean redundant whitespace and multi-newlines
    clean_md = re.sub(r"\n{3,}", "\n\n", raw_md).strip()
    return title, clean_md, tables_count, links_count
