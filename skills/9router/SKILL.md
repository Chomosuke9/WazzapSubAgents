---
name: 9router
description: Entry point for 9Router — local/remote AI gateway with OpenAI-compatible REST for chat, image, TTS, embeddings, web search, web fetch. Use when the user mentions 9Router, NINEROUTER_URL, or wants AI without writing provider boilerplate. This skill covers setup and indexes the locally installed capability skills.
---

# 9Router

Local/remote AI gateway exposing OpenAI-compatible REST. One key, many providers, auto-fallback.

## Runtime configuration

`NINEROUTER_URL` and `NINEROUTER_KEY` are injected into the executor environment. Use them as opaque values; never print, echo, or write the key. Do not replace the URL with `localhost` from inside the executor container. 

All requests: `${NINEROUTER_URL}/v1/...` with header `Authorization: Bearer ${NINEROUTER_KEY}` (omit if auth disabled).

Verify: `curl $NINEROUTER_URL/api/health` → `{"ok":true}`

## Discover models

```bash
curl "$NINEROUTER_URL/v1/models" -H "Authorization: Bearer $NINEROUTER_KEY"            # chat/LLM
curl "$NINEROUTER_URL/v1/models/image" -H "Authorization: Bearer $NINEROUTER_KEY"      # image-gen
curl "$NINEROUTER_URL/v1/models/tts" -H "Authorization: Bearer $NINEROUTER_KEY"        # text-to-speech
curl "$NINEROUTER_URL/v1/models/embedding" -H "Authorization: Bearer $NINEROUTER_KEY"  # embeddings
curl "$NINEROUTER_URL/v1/models/web" -H "Authorization: Bearer $NINEROUTER_KEY"        # web search/fetch
curl "$NINEROUTER_URL/v1/models/stt" -H "Authorization: Bearer $NINEROUTER_KEY"        # speech-to-text
curl "$NINEROUTER_URL/v1/models/image-to-text" -H "Authorization: Bearer $NINEROUTER_KEY" # vision
```

Use `data[].id` as `model` field in requests. Combos appear with `owned_by:"combo"`.
To prevent error, we recommend to use "combo" models when available, as they are more reliable than individual models.

Response shape:
```json
{ "object": "list", "data": [
  { "id": "openai/gpt-5", "object": "model", "owned_by": "openai", "created": 1735000000 },
  { "id": "tavily/search", "object": "model", "kind": "webSearch", "owned_by": "tavily", "created": 1735000000 }
]}
```

## Capability skills

When the user needs a specific capability, read its local `SKILL.md`:

| Capability | Local path |
|---|---|
| Chat / code-gen | `/skills/9router/9router-chat/SKILL.md` |
| Image generation | `/skills/9router/9router-image/SKILL.md` |
| Video generation | `/skills/9router/9router-video/SKILL.md` |
| Text-to-speech | `/skills/9router/9router-tts/SKILL.md` |
| Speech-to-text | `/skills/9router/9router-stt/SKILL.md` |
| Embeddings | `/skills/9router/9router-embeddings/SKILL.md` |
| Web search | `/skills/9router/9router-web-search/SKILL.md` |
| Web fetch (URL → markdown) | `/skills/9router/9router-web-fetch/SKILL.md` |

## Errors

- 401 → set/refresh `NINEROUTER_KEY` (Dashboard → Keys)
- 400 `Invalid model format` → check `model` exists in `/v1/models/<kind>`
- 503 `All accounts unavailable` → wait `retry-after` or add another provider account
