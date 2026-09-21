# twin

[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![JavaScript](https://img.shields.io/badge/javascript-vanilla-f7df1e)](static/script.js)
[![HTML](https://img.shields.io/badge/html-5-e34c26)](static/index.html)
[![CSS](https://img.shields.io/badge/css-3-264de4)](static/styles.css)
[![OpenAI API](https://img.shields.io/badge/OpenAI-API-412991)](https://platform.openai.com/docs)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**twin** is my personal digital twin: a small FastAPI app that lets visitors to my website chat with an AI that knows my background, skills, and experience, and answers as me. It's powered entirely by the OpenAI API, streamed token-by-token to a chat UI I built from scratch, with no framework in between.

## Why

I wanted a chat widget on my personal site that could answer "so what do you actually do?" without me being online, and that stays on topic instead of turning into a general-purpose chatbot. The core idea, and the original code this project is built on, come from Ed Donner's [`agents`](https://github.com/ed-donner/agents) course, specifically the [`1_foundations/twin`](https://github.com/ed-donner/agents/tree/main/1_foundations/twin) example. **Big credit to Ed Donner** for the original concept, prompt structure, and tool-calling pattern.

I took that starting point and rebuilt the serving layer, the frontend, and the guardrails around it to get it ready for a public-facing personal site, rather than a local demo. See [What I changed](#what-i-changed-from-the-original) below for the full list.

## Try it

No setup needed, it's live: **[twin-828z.onrender.com](https://twin-828z.onrender.com/)**

It's hosted on Render's free tier, so if it hasn't had a visitor in a while, the first message might take a bit to get a reply while the server spins back up. Worth the wait!

## Design decisions

- **Streamed, tool calls and all.** Replies stream token-by-token from the OpenAI API over a raw `StreamingResponse`, including through tool-call loops. Streaming plus function calling means tool-call fragments arrive as deltas, so `app.py` accumulates them by index before dispatching, rather than waiting for one complete response like a non-streaming call would.
- **Built for a public, unauthenticated endpoint.** Since anyone can hit `/api/chat` with no login, the app enforces per-IP-per-minute, per-IP-per-day, and site-wide daily rate limits, plus caps on message length, history length, and tool-call loops, all tunable via environment variables without a redeploy.
- **The visitor's history is never trusted.** The client sends its own chat history with every request, so the backend re-validates its shape, strips anything that isn't a plain user or assistant text turn, and truncates both message length and history length before it ever reaches the model.
- **Never leaks the represented person's own email.** Every email address found in the background data (LinkedIn export, summary, fun facts) is extracted at startup, and the `record_user_details` tool refuses to record any of them as if it were a visitor's, so the model can't accidentally "notify" the owner about themselves.
- **Getting in touch doesn't require an email.** A visitor can express interest without leaving contact details. The tool still fires, just without an email, so no genuine interest goes unrecorded.
- **Personal data lives in files, not code.** The LinkedIn export, summary, and fun facts are separate, git-ignored files, loaded at runtime. In production, they're read from Render's Secret Files mount instead, so no personal data ever touches the git history.
- **A custom frontend, not a demo UI.** The original project's Gradio `ChatInterface` is swapped for a hand-built HTML/CSS/JS chat panel: streamed markdown rendering sanitised with DOMPurify, an auto-resizing input, cycling placeholder prompts, and clickable suggestion and "fun fact" chips.
- **One consistent voice.** The system prompt tells the twin never to use em dashes and to use the Oxford comma in lists, so replies read the way I'd actually write, not the way a generic LLM defaults to.

## What I changed from the original

Starting from Ed Donner's [`1_foundations/twin`](https://github.com/ed-donner/agents/tree/main/1_foundations/twin), here's what's different in this version:

- **Streaming, not blocking.** Swapped the synchronous `OpenAI` client and single blocking `chat()` call for an `AsyncOpenAI` client that streams tokens through FastAPI's `StreamingResponse`, with manual accumulation of streamed tool-call deltas (streaming breaks the simple "read `tool_calls` off the response" pattern the original relies on).
- **A custom frontend, not Gradio.** Replaced `gr.ChatInterface` entirely with a hand-built FastAPI static site (`static/index.html`, `styles.css`, `script.js`): a typing indicator, sanitised streamed markdown rendering, an auto-resizing textarea, cycling placeholder text, and clickable suggestion/fun-fact chips.
- **Rate limiting and abuse guardrails.** The original had none, being a local Gradio demo. This version adds per-IP and global request limits, message and history size caps, and a tool-loop cap, all env-configurable, since this runs as a public unauthenticated endpoint.
- **Visitor history is sanitised server-side.** The original trusted Gradio's own history format completely. This version re-validates every incoming history item's shape and truncates it before it reaches the model.
- **The twin can't leak its own owner's email.** Added `OWNER_EMAILS`, extracted from the background data at startup, and a check in `record_user_details` that refuses to record any of those addresses as a visitor's.
- **Getting in touch no longer requires an email.** The original's `record_user_details` required one. This version records interest either way, so a visitor who doesn't want to share an email still gets noted.
- **Personal data files support a production secrets mount.** Added a fallback to Render's `/etc/secrets/` path, so the same code works locally (files in the project root) and in production (files uploaded as secrets), with a clear error if a file is missing from both.
- **Added `fun_facts.txt`** as an optional, separate data source for lighter trivia questions, feeding its own section of the system prompt.
- **Consistent voice.** The system prompt now explicitly forbids em dashes and calls for the Oxford comma, so the twin's writing style matches how I actually write.

## Known limitations

- Rate limiting is in-memory, so it resets on restart and isn't shared across multiple instances. That's a deliberate trade-off for a low-traffic personal site, not a security boundary.
- The twin only knows what's in `summary.txt`, `linkedin.pdf`, and `fun_facts.txt`. Anything outside those files gets recorded as an unknown question rather than guessed at.
- `MAX_REPLY_TOKENS` can cut a long answer off mid-stream if set too low; the default of `800` is generous enough for typical chat-length replies.

## Acknowledgments

Built on top of Ed Donner's [`agents`](https://github.com/ed-donner/agents) course, specifically the [`1_foundations/twin`](https://github.com/ed-donner/agents/tree/main/1_foundations/twin) example, which supplied the original digital-twin concept, system prompt structure, and OpenAI function-calling pattern this project extends. This project uses the plain [OpenAI API](https://platform.openai.com/docs/api-reference) (Chat Completions with function calling) directly, not the separate OpenAI Agents SDK.

Source for this project: [github.com/havl-code/twin](https://github.com/havl-code/twin)

## Licence

Released under the MIT Licence, see [LICENSE](LICENSE).
