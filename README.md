# The Brief — Daily Market Intelligence

A static finance newsletter website, auto-published every weekday morning via GitHub Actions and hosted on Cloudflare Pages.

---

## What this is

**The Brief** is a daily market intelligence newsletter for finance students and early-career professionals, with a Wealth Management and Private Banking focus. Every weekday at 8:30 AM ET, a GitHub Action calls the Anthropic API, generates a new issue as HTML, updates the homepage and archive, and commits everything — Cloudflare Pages then auto-deploys in under 30 seconds.

---

## First-time setup

### Step 1 — Push to GitHub

1. Create a new GitHub repository (public or private).
2. In your terminal, from this folder:

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

---

### Step 2 — Add your Anthropic API key as a GitHub Secret

The script reads `ANTHROPIC_API_KEY` from environment variables. Never put the key in code.

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `ANTHROPIC_API_KEY`
4. Value: your Anthropic API key (starts with `sk-ant-...`)
5. Click **Add secret**

Get your key at: https://console.anthropic.com/

---

### Step 3 — Connect Cloudflare Pages

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Go to **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**
3. Authorize GitHub and select your repository
4. Configure the build:
   - **Build command:** *(leave empty — this is a pure static site, no build step)*
   - **Build output directory:** `/` (root)
   - **Branch:** `main`
5. Click **Save and Deploy**

Cloudflare will deploy immediately and on every future push to `main`.

Your site will be live at `YOUR_PROJECT.pages.dev`. You can add a custom domain in **Pages → Custom domains**.

---

### Step 4 — Set up the subscribe form (optional)

The subscribe form uses [Formspree](https://formspree.io/) — free for up to 50 submissions/month.

1. Create a free account at formspree.io
2. Create a new form, copy your form ID (looks like `xrgvabcd`)
3. In `index.html` and `subscribe.html`, replace `YOUR_FORM_ID` with your actual form ID:
   ```
   action="https://formspree.io/f/YOUR_FORM_ID"
   ```
4. In `subscribe.html`, update the `_next` redirect URL to your actual site URL.

---

### Step 5 — Update share links

In `index.html` and `subscribe.html`, replace the placeholder URL:
```
https://thebrieffinance.com
```
with your actual Cloudflare Pages URL (e.g., `https://the-brief.pages.dev`).

---

## How the automation works

Every weekday at 8:30 AM ET, GitHub Actions runs `.github/workflows/daily-brief.yml`:

1. **Checks out** the repository
2. **Installs** the `anthropic` Python package
3. **Runs** `scripts/generate_brief.py`, which:
   - Loads `prompts/system_prompt.txt`
   - Calls Claude (claude-sonnet-4-6) with web search enabled
   - Gets real market data for the day
   - Generates a JSON brief
   - Validates the data (exits with error if data looks fabricated)
   - Renders `briefs/YYYY-MM-DD.html`
   - Updates the Latest Issue block in `index.html`
   - Prepends a new row to `archive.html`
   - Saves LinkedIn copy to `linkedin/YYYY-MM-DD.txt`
4. **Commits and pushes** all new files
5. **Cloudflare Pages** detects the push and deploys in ~30 seconds

### What happens if it fails?

The script exits with a non-zero code if:
- `ANTHROPIC_API_KEY` is not set
- The API call fails
- The response isn't valid JSON
- Required fields are missing
- Ticker data looks like a placeholder

GitHub Actions marks the run as failed and sends you an email notification. No broken or fake content is ever committed.

---

## Running it manually

To generate today's brief on your local machine:

```bash
# Install dependencies
pip install anthropic

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Run
python scripts/generate_brief.py
```

You can also trigger it manually from GitHub:
**Actions** → **Generate Daily Brief** → **Run workflow**

---

## File structure

```
the-brief-website/
├── index.html                    Homepage
├── archive.html                  All issues
├── about.html                    About the newsletter
├── subscribe.html                Subscribe page
├── styles.css                    Shared site styles
├── briefs/                       One HTML file per issue
│   └── YYYY-MM-DD.html
├── linkedin/                     Auto-generated LinkedIn copy
│   └── YYYY-MM-DD.txt
├── prompts/
│   └── system_prompt.txt         Editorial instructions for Claude
├── scripts/
│   └── generate_brief.py         The generation script
├── .github/
│   └── workflows/
│       └── daily-brief.yml       GitHub Actions workflow
└── README.md
```

---

## Customizing the editorial style

Edit `prompts/system_prompt.txt` to change how The Brief is written:
- Adjust the tone, length, or section structure
- Add or remove sections
- Change the career focus (e.g., more ER, less IB)
- Update sourcing guidelines

The system prompt is loaded fresh on every run, so changes take effect the next day without touching any code.

---

## Costs

- **Anthropic API:** Claude Sonnet with web search. Each run uses roughly 4,000–8,000 output tokens plus search tool calls. Estimate: ~$0.05–$0.15 per issue at current pricing. Check [anthropic.com/pricing](https://anthropic.com/pricing) for current rates.
- **GitHub Actions:** Free tier (2,000 minutes/month) covers ~20 weekday runs with margin.
- **Cloudflare Pages:** Free tier (unlimited bandwidth, 500 builds/month) covers this comfortably.

Total cost: approximately $1–3/month for daily publishing.

---

## License

Educational use. Not investment advice.
