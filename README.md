# Etsy Listing Optimizer

Lean FastAPI MVP for extracting public Etsy listing copy and improving it with an OpenAI-compatible local LLM endpoint through OpenClaw.

## Features

- Single-page UI for Etsy URL input, extraction review, and SEO analysis
- Multi-strategy extraction with direct requests, optional browser fallback, and URL-slug inference
- Extraction confidence scoring with automatic manual fallback
- Local LLM integration behind a swappable service module
- Strict JSON parsing and Pydantic validation for model output
- Mock mode when no LLM is configured
- Health check endpoint and basic logging
- Copy buttons for optimized title, description, and tags

## Project Structure

```text
app/
  main.py
  config.py
  routes/
  schemas/
  services/
  templates/
  static/
requirements.txt
.env.example
README.md
```

## Run Locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the example environment file and update it:

PowerShell:

```powershell
Copy-Item .env.example .env
```

Bash:

```bash
cp .env.example .env
```

4. Start the app:

```bash
uvicorn app.main:app --reload
```

5. Open `http://127.0.0.1:8000`

## GitHub Pages Landing Page

A simple public landing page for app registration is included in `docs/`.

To publish it with GitHub Pages:

1. Push this repo to GitHub.
2. Open the repository on GitHub.
3. Go to `Settings` -> `Pages`.
4. Under `Build and deployment`, choose `Deploy from a branch`.
5. Select your main branch and the `/docs` folder.
6. Save and wait for GitHub Pages to publish.

Your public URL will look like:

```text
https://yourusername.github.io/your-repo-name/
```

Before submitting it to Etsy, replace the placeholder contact email in `docs/index.html`.

## Environment Variables

- `LLM_BASE_URL`: Base URL for an OpenAI-compatible chat completions API
- `LLM_API_KEY`: Optional bearer token
- `LLM_MODEL`: Model name exposed by your local LLM endpoint
- `LLM_REQUEST_TIMEOUT`: Timeout in seconds for the LLM request
- `LLM_MOCK_MODE`: Set to `true` to bypass the LLM and use deterministic mock output
- `BROWSER_EXTRACTION_ENABLED`: Enable browser fallback for blocked Etsy pages
- `BROWSER_EXTRACTION_TIMEOUT`: Timeout in seconds for the browser fallback
- `ETSY_API_KEY`: Optional Etsy Open API key for direct listing lookup by `listing_id`

If `LLM_BASE_URL` or `LLM_MODEL` is missing, the app automatically falls back to mock mode.

## API

### `GET /health`

Returns:

```json
{"status":"ok"}
```

### `POST /extract`

```json
{
  "url": "https://www.etsy.com/listing/123456789/example-product"
}
```

### `POST /analyze`

```json
{
  "title": "Custom Family Name Sign",
  "description": "Handmade sign for home decor...",
  "category": "Home Decor",
  "target_keyword": "custom family sign"
}
```

## Sample `curl`

```bash
curl -X POST http://127.0.0.1:8000/extract \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://www.etsy.com/listing/123456789/example-product\"}"
```

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Custom Family Name Sign\",\"description\":\"Handmade sign for home decor...\",\"category\":\"Home Decor\",\"target_keyword\":\"custom family sign\"}"
```

## Notes

- If you add `ETSY_API_KEY`, the extractor will first try Etsy’s official listing endpoint using the `listing_id` parsed from the URL. This is the most reliable URL-only path when available.
- Etsy can block automated requests with an anti-bot challenge. This app now detects that case explicitly, tries a browser fallback, and still pre-fills the title from the URL slug when a full fetch is blocked.
- The LLM integration assumes an OpenAI-compatible `/chat/completions` endpoint.
- The service layer is separated so Stripe, auth, persistence, or queued jobs can be added later without reworking the core flow.
