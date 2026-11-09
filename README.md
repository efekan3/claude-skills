# Claude skills

154 skills for Claude Code, adapted from [Hermes Agent](https://github.com/NousResearch/hermes-agent)
by Nous Research (MIT licence, see `LICENSE-hermes-agent`).

Start a Claude Code session from this repo and everything in `.claude/skills/` loads automatically.
On your own computer, copy the folders into `~/.claude/skills/`.

Left out: 27 skills that depend on Hermes-only features, 2 empty catalog stubs (archify, impeccable),
and 2 that jailbreak or strip safety training from AI models.

## 1-ready-to-use — 42 skills

Work in Claude straight away — no installs, no keys.

| Skill | What it does |
|---|---|
| **one-three-one-rule** ⭐ | 1-3-1 decision briefs: problem, three options, one pick. |
| **anatomy** | Explain an idea as an interactive isometric machine figure. |
| ~~archify~~ | Validated interactive HTML diagrams, upstream-maintained. |
| **architecture-diagram** | Dark-themed SVG architecture/cloud/infra diagrams as HTML. |
| **claude-design** | Design one-off HTML artifacts (landing, deck, prototype). |
| **concept-diagrams** | Generate flat, minimal educational SVG visuals as HTML. |
| **creative-ideation** ⭐ | Generate ideas via named methods from creative practice. |
| **design-md** | Author/validate/export Google's DESIGN.md token spec files. |
| **excalidraw** ⭐ | Hand-drawn Excalidraw JSON diagrams (arch, flow, seq). |
| **humanizer** ⭐ | Humanize text: strip AI-isms and add real voice. |
| **p5js** | p5.js sketches: gen art, shaders, interactive, 3D. |
| **popular-web-designs** | 54 real design systems (Stripe, Linear, Vercel) as HTML/CSS. |
| **pretext** | Build creative browser demos with DOM-free text layout. |
| **simple-english** ⭐ | Rewrite text to ASD-STE100 Simplified Technical English. |
| **sketch** | Throwaway HTML mockups: 2-3 design variants to compare. |
| **songwriting-and-ai-music** | Songwriting craft and Suno AI music prompts. |
| **system-atlas** | Build explorable isometric architecture atlases as HTML. |
| **setup-wizard-generator** | Generate a bash wizard guiding a human through manual setup. |
| **adversarial-ux-test** | Roleplay a hostile user to find and triage UX pain points. |
| **email-inbox-triage** | Triage an inbox: prioritize threads, draft replies safely. |
| **polymarket** | Query Polymarket: markets, prices, orderbooks, history. |
| **youtube-content** ⭐ | YouTube transcripts to summaries, threads, blogs. |
| **obsidian** ⭐ | Read, search, create, and edit notes in the Obsidian vault. |
| **decision-questionnaire** ⭐ | Turn an unanswerable decision into a questionnaire doc. |
| **document-to-action-items** ⭐ | Extract cited obligations, deadlines, tasks from documents. |
| **maps** | Geocode, POIs, routes, timezones via OpenStreetMap/OSRM. |
| **meeting-action-items** ⭐ | Turn meeting notes into cited decisions, owners, tickets. |
| **weekly-review-planning** ⭐ | Weekly reset: commitments, stalled work, next-week plan. |
| **arxiv** ⭐ | Search arXiv papers by keyword, author, category, or ID. |
| **competitor-news-monitor** | Watch named companies for material news; cited digests. |
| **domain-intel** | Passive recon of subdomains, SSL certs, WHOIS, and DNS. |
| **grounded-citations** ⭐ | Ground answers and documents in cited, verifiable sources. |
| **llm-wiki** ⭐ | Karpathy's LLM Wiki: build/query interlinked markdown KB. |
| **code-wiki** | Generate wiki docs + Mermaid diagrams for any codebase. |
| **grill-me** | Adversarial plan interview before implementation. |
| **pr-lens** | Draw code changes as animated architecture/data-flow SVGs. |
| **simplify-code** | Parallel 4-agent cleanup of recent code changes. |
| **spike** | Throwaway experiments to validate an idea before build. |
| **systematic-debugging** | 4-phase root cause debugging: understand bugs before fixing. |
| **test-driven-development** | TDD: enforce RED-GREEN-REFACTOR, tests before code. |
| **blocked-page-recovery** | Use when a fetch fails: 403/429, paywall, WAF, bot wall. |


## 2-needs-setup — 88 skills

Work in Claude Code once you install a program or add an API key (see 'Needs').

| Skill | What it does | Needs |
|---|---|---|
| **antigravity-cli** | Operate the Antigravity CLI (agy): plugins, auth, sandbox. | Python packages / CLI tools it names |
| **blackbox** | Delegate coding tasks to the Blackbox AI multi-model CLI. | Python packages / CLI tools it names |
| **claude-code** | Delegate coding to Claude Code CLI (features, PRs). | key: ANTHROPIC_API_KEY |
| **codex** | Delegate coding to OpenAI Codex CLI (features, PRs). | key: OPENAI_API_KEY |
| **grok** | Delegate coding to xAI Grok Build CLI (features, PRs). | key: XAI_API_KEY |
| **opencode** | Delegate coding to OpenCode CLI (features, PR review). | key: OPENROUTER_API_KEY |
| **openhands** | Delegate coding to OpenHands CLI (model-agnostic, LiteLLM). | key: LLM_API_KEY, OPENROUTER_API_KEY |
| **evm** | Read-only EVM client: wallets, tokens, gas across 8 chains. | Python packages / CLI tools it names |
| **hyperliquid** | Hyperliquid market data, account history, trade review. | Python packages / CLI tools it names |
| **solana** | Query Solana wallets, tokens, txs, and NFTs in USD. | Python packages / CLI tools it names |
| **ascii-art** | ASCII art: pyfiglet, cowsay, boxes, image-to-ascii. | Python packages / CLI tools it names |
| **ascii-video** | ASCII video: convert video/audio to colored ASCII MP4/GIF. | Python packages / CLI tools it names |
| **brag** | Project launch video via Hyperframes, upstream-maintained. | key: GITHUB_TOKEN |
| **brag-slim** | Launch video from a project or URL, upstream-maintained. | Python packages / CLI tools it names |
| **comfyui** | Generate images, video, and audio via diffusion workflows. | install ["python"] |
| **draw-your-font** | Turn a handwriting photo into an installable TTF font. | Python packages / CLI tools it names |
| **heartmula** | HeartMuLa: Suno-like song generation from lyrics + tags. | Python packages / CLI tools it names |
| **hyperframes** | Render MP4/WebM videos from HTML compositions. | install [node, ffmpeg, npx] |
| **manim-video** | Manim CE animations: 3Blue1Brown math/algo videos. | Python packages / CLI tools it names |
| **pixel-art** | Pixel art w/ era palettes (NES, Game Boy, PICO-8). | Python packages / CLI tools it names |
| **tldraw-offline** | Drive and script tldraw offline canvases with an agent. | Python packages / CLI tools it names |
| **unreal-mcp** | Automate Unreal Engine editor scenes, actors, and renders. | Python packages / CLI tools it names |
| **jupyter-notebook** | Iterative Python via live Jupyter kernel (hamelnb). | Python packages / CLI tools it names |
| **docker-management** | Manage Docker containers, images, volumes, and Compose. | Python packages / CLI tools it names |
| **inference-sh-cli** | Run 150+ AI apps (image, video, LLM) via inference.sh CLI. | key: INFSH_API_KEY |
| **pinggy-tunnel** | Zero-install localhost tunnels over SSH via Pinggy. | key: PINGGY_TOKEN |
| **watchers** | Poll RSS, JSON APIs, and GitHub with watermark dedup. | key: GITHUB_TOKEN |
| **agentmail** | Use when an agent needs AgentMail CLI email inboxes. | install [agentmail] |
| **himalaya** | Himalaya CLI: IMAP/SMTP email from terminal. | install [himalaya] |
| **3-statement-model** | Build integrated IS/BS/CF financial workbooks in Excel. | Python packages / CLI tools it names |
| **comps-analysis** | Build comparable-company valuation workbooks in Excel. | Python packages / CLI tools it names |
| **dcf-model** | Build discounted cash flow valuation workbooks in Excel. | Python packages / CLI tools it names |
| **excel-author** | Build auditable financial workbooks headless via openpyxl. | Python packages / CLI tools it names |
| **lbo-model** | Build leveraged buyout workbooks with IRR/MOIC in Excel. | Python packages / CLI tools it names |
| **merger-model** | Build M&A accretion/dilution workbooks in Excel. | Python packages / CLI tools it names |
| **pptx-author** | Build PowerPoint decks headless with python-pptx. | Python packages / CLI tools it names |
| **stocks** | Stock quotes, history, search, compare, crypto via Yahoo. | key: ALPHA_VANTAGE_KEY |
| **minecraft-modpack-server** | Host modded Minecraft servers (CurseForge, Modrinth). | Python packages / CLI tools it names |
| **pokemon-player** | Play Pokemon via headless emulator + RAM reads. | Python packages / CLI tools it names |
| **fitness-nutrition** | Workout planning, macros, and body metrics via wger/USDA. | key: USDA_API_KEY |
| **neuroskill-bci** | Use live BCI cognitive and mood state from NeuroSkill. | Python packages / CLI tools it names |
| **fastmcp** | Build, test, and deploy Python MCP servers. | install [python] |
| **mcporter** | List, auth, and call MCP servers/tools from the terminal. | install [npx] |
| **gif-search** | Search/download GIFs from Tenor via curl + jq. | keys [TENOR_API_KEY] install [curl, jq] |
| **songsee** | Audio spectrograms/features (mel, chroma, MFCC) via CLI. | install [songsee] |
| **stripe-link-cli** | Agent payments via Stripe Link — cards, SPT, approvals. | Python packages / CLI tools it names |
| **stripe-projects** | Provision SaaS services + sync creds via Stripe Projects. | Python packages / CLI tools it names |
| **box** | Box manages cloud files, sharing, search, and metadata. | install [box] |
| **canvas** | Fetch Canvas LMS courses and assignments via API token. | keys [CANVAS_API_TOKEN, CANVAS_BASE_URL] |
| **google-workspace** | Gmail, Calendar, Drive, Docs, Sheets via gws CLI or Python. | Python packages / CLI tools it names |
| **here-now** | Publish sites to {slug}.here.now and store files in Drives. | install [curl, file, jq] |
| **live-dashboard** | Build self-updating dashboards from live sources. | scheduling part needs Hermes |
| **memento-flashcards** ⭐ | Spaced-repetition flashcards: create, review, quiz, export. | Python packages / CLI tools it names |
| **microsoft-office** | Create, read, and edit Word, PowerPoint, and Excel files. | Python packages / CLI tools it names |
| **pdf** | PDF files: create, read, merge, fill, OCR, edit text. | Python packages / CLI tools it names |
| **product-price-monitor** | Watch product, flight, or listing prices; alert on target. | scheduling part needs Hermes |
| **shop** | Shop catalog search, checkout, order tracking, returns. | install [curl, node] |
| **siyuan** | Query and edit a SiYuan knowledge base via its API. | keys [SIYUAN_TOKEN] install [curl, jq] |
| **telephony** | Provision Twilio numbers, SMS/MMS, and AI outbound calls. | key: BLAND_API_KEY, TWILIO_AUTH_TOKEN, VAPI_API_KEY |
| **bioinformatics** | Gateway to 400+ genomics and computational biology skills. | Python packages / CLI tools it names |
| **blogwatcher** | Monitor blogs and RSS/Atom feeds via blogwatcher-cli tool. | install [blogwatcher-cli]; scheduling part needs Hermes |
| **darwinian-evolver** | Evolve prompts/regex/SQL/code with Imbue's evolution loop. | key: ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY |
| **drug-discovery** | Drug discovery: ChEMBL search, drug-likeness, interactions. | install [curl, python] |
| **gitnexus-explorer** | Serve an interactive codebase knowledge graph web UI. | Python packages / CLI tools it names |
| **osint-investigation** | Follow the money via public records and sanctions data. | key: COURTLISTENER_TOKEN, OPENCORPORATES_API_TOKEN, SENATE_LDA_TOKEN |
| **parallel-cli** | Agent-native web search, deep research, and enrichment. | key: PARALLEL_API_KEY |
| **qmd** ⭐ | Hybrid local search over notes, docs, and transcripts. | Python packages / CLI tools it names |
| **rss-feeds** | Read RSS, Atom, JSON feeds; discover feeds behind a page. | scheduling part needs Hermes |
| **scrapling** | Scrape sites with stealth browsing and Cloudflare bypass. | install [scrapling, python] |
| **1password** | Set up op CLI, sign in, and read or inject secrets. | key: OP_CONNECT_TOKEN, OP_SERVICE_ACCOUNT_TOKEN |
| **oss-forensics** | GitHub supply-chain forensics: recovery, IOCs, reporting. | key: GITHUB_TOKEN |
| **sherlock** | Find accounts for a username across 400+ platforms. | install [sherlock] |
| **unbroker** | Remove your info from data-broker sites, by name or phone. | install [python]; scheduling part needs Hermes |
| **web-pentest** | Authorized web pentest: recon, proof-based exploits, report. | Python packages / CLI tools it names |
| **openhue** | Control Philips Hue lights, scenes, rooms via OpenHue CLI. | install [openhue] |
| **reddit-reading** | Read Reddit: subreddits, search, threads, users. No browser. | key: REDDIT_CLIENT_SECRET |
| **xurl** | X/Twitter via xurl CLI: raw post search, posting, DM, media. | install [xurl] |
| **ast-grep** | AST-aware structural code search and rewrite via ast-grep. | Python packages / CLI tools it names |
| **codebase-inspection** | Inspect codebases w/ pygount: LOC, languages, ratios. | install [pygount] |
| **dogfood** | Exploratory QA of web apps: find bugs, evidence, reports. | Python packages / CLI tools it names |
| **github** | GitHub via gh CLI: PRs, issues, reviews, repos, auth. | Python packages / CLI tools it names |
| **node-inspect-debugger** | Debug Node.js via --inspect + Chrome DevTools Protocol CLI. | Python packages / CLI tools it names |
| **python-debugpy** | Debug Python: pdb REPL + debugpy remote (DAP). | Python packages / CLI tools it names |
| **rest-graphql-debug** | Debug REST/GraphQL APIs: status codes, auth, schemas, repro. | key: API_TOKEN |
| **cloudflare-temporary-deploy** | Deploy a Worker live, no account, via wrangler --temporary. | key: CLOUDFLARE_API_KEY, CLOUDFLARE_API_TOKEN |
| **har-derived-api-client** | Record a site's XHR into a HAR, derive an HTTP client. | Python packages / CLI tools it names |
| **page-agent** | Embed an in-page natural-language GUI copilot in web apps. | key: LLM_API_KEY |
| **publish-site** | Versioned site deploys to GitHub/Cloudflare/Netlify Pages. | key: CLOUDFLARE_API_TOKEN |


## 3-mac-only — 4 skills

Only work on a Mac, through Claude Code on that Mac.

| Skill | What it does | Needs |
|---|---|---|
| **apple-notes** | Manage Apple Notes via memo CLI: create, search, edit. | install [memo] |
| **apple-reminders** | Apple Reminders via remindctl: add, list, complete. | install [remindctl] |
| **findmy** | Track Apple devices/AirTags via FindMy.app on macOS. | macOS |
| **imessage** | Send and receive iMessages/SMS via the imsg CLI on macOS. | install [imsg] |


## 5-ml-engineering — 22 skills

Machine-learning engineering: training/serving models, mostly needs a GPU.

| Skill | What it does | Needs |
|---|---|---|
| **accelerate** | Run PyTorch training across GPUs with minimal changes. | GPU / Python ML libraries |
| **axolotl** | Axolotl: YAML LLM fine-tuning (LoRA, DPO, GRPO). | GPU / Python ML libraries |
| **chroma** | Embedding database for RAG and semantic search. | GPU / Python ML libraries |
| **dspy** | DSPy: declarative LM programs, auto-optimize prompts, RAG. | GPU / Python ML libraries |
| **evaluating-llms-harness** | lm-eval-harness: benchmark LLMs (MMLU, GSM8K, etc.). | GPU / Python ML libraries |
| **faiss** | Fast vector similarity search at billion scale. | GPU / Python ML libraries |
| **flash-attention** | Speed up long-sequence transformer training and inference. | GPU / Python ML libraries |
| **lambda-labs** | On-demand GPU cloud instances for ML training. | GPU / Python ML libraries |
| **llama-cpp** | llama.cpp local GGUF inference + HF Hub model discovery. | GPU / Python ML libraries |
| **modal** | Serverless GPU cloud for ML jobs and model APIs. | GPU / Python ML libraries |
| **nemo-curator** | Curate LLM training data: dedupe, filter, PII redaction. | GPU / Python ML libraries |
| **peft** | Fine-tune large LLMs with LoRA on limited GPU memory. | GPU / Python ML libraries |
| **pytorch-fsdp** | Fully sharded data-parallel training for large models. | GPU / Python ML libraries |
| **pytorch-lightning** | Clean training loops with built-in distributed support. | GPU / Python ML libraries |
| **saelens** | Train sparse autoencoders to interpret model features. | GPU / Python ML libraries |
| **segment-anything-model** | SAM: zero-shot image segmentation via points, boxes, masks. | GPU / Python ML libraries |
| **serving-llms-vllm** | vLLM: high-throughput LLM serving, OpenAI API, quantization. | GPU / Python ML libraries |
| **simpo** | Reference-free preference alignment, simpler than DPO. | GPU / Python ML libraries |
| **slime** | RL post-training for LLMs with Megatron and SGLang. | GPU / Python ML libraries |
| **tensorrt-llm** | High-throughput LLM inference on NVIDIA GPUs. | GPU / Python ML libraries |
| **torchtitan** | Pretrain LLMs at scale with PyTorch 4D parallelism. | GPU / Python ML libraries |
| **unsloth** | Unsloth: 2-5x faster LoRA/QLoRA fine-tuning, less VRAM. | GPU / Python ML libraries |

