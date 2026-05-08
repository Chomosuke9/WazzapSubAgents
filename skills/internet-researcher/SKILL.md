# Brave Search API Skills

This file enables AI agents to discover and use Brave Search API skills.

| Skill | Description |
|--|--|
| [images-search](skills/images-search) | Image search. Returns images with title, source URL, thumbnail. Supports SafeSearch filter. Up to 200 results. |
| [llm-context](skills/llm-context) | RAG/LLM grounding. Returns pre-extracted web content (text, tables, code) optimized for LLMs. GET + POST. Adjust max_tokens/count based on complexity. |
| [news-search](skills/news-search) | News search. Returns news articles with title, URL, description, age, thumbnail. Supports freshness and date range filtering, SafeSearch filter and Goggles for custom ranking. |
| [videos-search](skills/videos-search) | Video search. Returns videos with title, URL, thumbnail, duration, view count, creator. Supports freshness filters, SafeSearch, pagination. |
| [web-search](skills/web-search) | Web search. Returns ranked results with snippets, URLs, thumbnails. Supports freshness filters, SafeSearch, Goggles for custom ranking, pagination. Primary search endpoint. |

## Secret
- You got `BRAVE_SEARCH_API_KEY` injected to your enviroment already.
- reference it as `${BRAVE_SEARCH_API_KEY}` in curl commands.

## Usage

Read the SKILL.md file from `skills/<name>/SKILL.md` for full instructions on any skill.
