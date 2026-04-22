# iHunters Germany — AI-Powered Export Lead Platform

An AI-powered lead generation platform that helps Chinese exporters find, contact, and manage B2B/B2C buyers in Germany.

## Features

- **Product Management** — Create and manage products you're exporting from China
- **AI Market Analysis** — Get targeted sectors, top German cities, and buyer personas powered by Groq LLM
- **Lead Generation** — Auto-generate B2B (retailers, wholesalers, distributors) and B2C (Amazon sellers, boutiques) leads
- **Email Discovery** — Scrape company websites for contact emails with Hunter.io as fallback
- **Email Verification** — Validate lead emails via DNS/SMTP checks
- **Outreach Generation** — AI-written bilingual (German + English) cold emails tailored to each lead
- **Real Company Import** — Import verified companies one by one or in bulk (pipe-separated text)
- **Stats Dashboard** — Live counts for leads, contacts, outreaches, and more

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.11+ |
| AI | Groq (LLaMA 3) |
| Database | SQLite via `aiosqlite` |
| Email finder | Web scraper + Hunter.io API |
| Frontend | Vanilla HTML / CSS / JS |

## Getting Started

### Prerequisites

- Python 3.11+
- A [Groq API key](https://console.groq.com/) (free tier available)
- _(Optional)_ A [Hunter.io API key](https://hunter.io/) for email discovery fallback

### Setup

1. **Clone the repo**

   ```bash
   git clone https://github.com/<your-username>/iHunter.git
   cd iHunter
   ```

2. **Create a `.env` file** in the project root:

   ```env
   GROQ_API_KEY=your_groq_api_key_here
   HUNTER_API_KEY=your_hunter_api_key_here   # optional
   ```

3. **Run the app**

   ```bash
   chmod +x start.sh
   ./start.sh
   ```

   The script creates a virtual environment, installs dependencies, and starts the server.

4. **Open** [http://localhost:8000](http://localhost:8000) in your browser.

## Usage

1. **Add a product** — enter its name, category, description, price range, and MOQ.
2. **Analyze the market** — the AI identifies target sectors and German cities for your product.
3. **Generate leads** — specify how many B2B and B2C leads you want and which cities to target.
4. **Find emails** — run email discovery on individual leads or import real companies with auto email scraping.
5. **Write outreach** — generate bilingual cold emails with one click per lead.
6. **Track progress** — update lead status (new → contacted → qualified → closed) and add notes.

## Bulk Import Format

Use the **Bulk Import** feature to paste a list of companies (one per line):

```
Company Name | website.de | City | Industry | Description | Size
Mustermann GmbH | mustermann.de | Berlin | Retail | Online shop for kitchenware | 50
```

All fields after the company name are optional.

## Project Structure

```
iHunter/
├── backend/
│   ├── main.py            # FastAPI routes
│   ├── database.py        # SQLite schema & helpers
│   ├── requirements.txt
│   └── agents/
│       ├── market_analyst.py
│       ├── lead_finder.py
│       ├── outreach_agent.py
│       ├── email_verifier.py
│       ├── web_scraper.py
│       ├── hunter.py
│       └── company_suggester.py
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── start.sh
└── README.md
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key for LLM inference |
| `HUNTER_API_KEY` | No | Hunter.io key for email lookup fallback |

## License

MIT
