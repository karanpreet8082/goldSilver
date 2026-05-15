# 🥇 Gold Silver Platinum — Bullion Dashboard

A **fully automated** precious metals analysis dashboard that tracks **gold, silver and platinum** bullion prices, analyses market conditions (technical + AI), and provides **BUY / SELL / HOLD** recommendations.

> **Bullion rates only** — no jewellery making charges, no GST.

## ✨ Features

| Feature | Details |
|---------|---------|
| **Live Prices** | Gold (₹/10g), Silver (₹/kg), Platinum (₹/g) — Indian & International |
| **Currency Rates** | USD, EUR, GBP, JPY, CHF, AUD, CAD, SGD against INR |
| **AI Recommendations** | BUY / SELL / HOLD with confidence scores for each metal |
| **Technical Analysis** | Moving averages, support/resistance, trend detection |
| **News Aggregation** | Metals, geopolitics, central bank, currency, inflation news |
| **Portfolio Tracker** | Add gold/silver/platinum holdings + cash — stored in browser |
| **100% Free** | All data sources free-tier, hosted on GitHub Pages |

## 📅 Schedule

Runs **4× daily** via GitHub Actions:
- 🕘 9:00 AM IST
- 🕛 12:00 PM IST
- 🕒 3:00 PM IST
- 🕕 6:00 PM IST

## 🚀 Quick Setup

1. **Fork** this repository
2. Go to **Settings → Secrets and variables → Actions** and add:
   - `GEMINI_API_KEY` — [Get free key](https://aistudio.google.com/apikey)
   - `GOLDAPI_KEY` — [Get free key](https://www.goldapi.io/)
   - `NEWSAPI_KEY` — [Get free key](https://newsapi.org/register)
   - `EXCHANGERATE_API_KEY` — [Get free key](https://www.exchangerate-api.com/)
3. Go to **Settings → Pages** → set Source to **GitHub Actions**
4. **Trigger** the workflow manually (Actions → Gold Silver Platinum Analysis → Run workflow)
5. Visit `https://<username>.github.io/goldSilver/`

## 🏗️ Architecture

```
goldSilver/
├── .github/workflows/     ← GitHub Actions (4× daily)
├── src/
│   ├── main.py            ← Entry point
│   ├── config.py          ← Settings & API keys
│   ├── data_fetcher/      ← Price, news, currency fetchers
│   ├── analysis/          ← Technical + AI analysis
│   └── reporting/         ← HTML dashboard generator
├── data/                  ← Cached JSON data
└── reports/               ← Generated HTML (deployed to Pages)
```

## 📊 Data Sources

| Source | What | Free Tier |
|--------|------|-----------|
| [metals.live](https://metals.live) | Gold/Silver/Platinum spot | Unlimited, no key |
| [GoldAPI.io](https://goldapi.io) | Metal prices + change % | 300 req/month |
| [ExchangeRate-API](https://exchangerate-api.com) | Currency rates | 1500 req/month |
| [NewsAPI](https://newsapi.org) | Financial news | 100 req/day |
| RSS Feeds | ET, Moneycontrol, Google News | Unlimited |
| [Google Gemini](https://aistudio.google.com) | AI analysis | 1500 req/day |

## 💼 Portfolio

Your portfolio is stored **entirely in your browser** (localStorage) — nothing is sent to any server.

- Track gold, silver, platinum holdings in grams
- Record buy price and date
- Sell portions and track realised P&L
- Maintain cash balance for investment planning
- Import/Export portfolio as JSON backup

## ⚠️ Disclaimer

This dashboard is for **informational purposes only**. It does not constitute financial advice. Always do your own research before making investment decisions. Past performance does not guarantee future results.

## 📜 Licence

MIT
