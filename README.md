<div align="center">
  <img src="https://github.com/noahtheprogrammer/soltrade/assets/81941019/aee060e2-d254-447e-b2ec-746367e06483" alt="soltrade_logo">
</div>

# Soltrade (Forked & Enhanced)

This is a **radically enhanced private fork** of the original [Soltrade](https://github.com/noahtheprogrammer/soltrade) project by [noahtheprogrammer](https://github.com/noahtheprogrammer). Credit to the original author for building a clean, open-source starter bot that we've extended into a smarter, more configurable trading platform.

---

## 🚀 What's New in This Fork?

- **Dynamic Strategy Switching** between `retail` (safe) and `degen` (aggressive) modes.
- **Customizable Trading Logic** via `.env` (no code changes required to tune behavior).
- **Smarter Buy/Sell Filters**: Combines EMA, RSI, Bollinger Bands, and trend biasing.
- **Trailing Stop Integration**: Protect gains and reduce premature exits.
- **Verbose Logging**: Human-readable decision logs for every trade cycle.
- **Error-Resilient Runtime**: Gracefully handles empty markets or data gaps.
- **Run from Script or Container** with single-step setup.

---

## ⚙️ Setup & Configuration

Before running the bot, create a `.env` file in the root directory:

```env
API_KEY=your_cryptocompare_api_key
WALLET_PRIVATE_KEY=your_phantom_wallet_private_key
SECONDARY_MINT=your_token_address

# Trading Mode: 'degen' for aggressive, 'retail' for safer entries
TRADING_MODE=degen

# RSI Thresholds
DEGEN_RSI_BUY_THRESHOLD=45
DEGEN_RSI_SELL_THRESHOLD=60

# Stoploss/TP for degen mode (as decimal multipliers)
DEGEN_STOPLOSS_PERCENT=0.89
DEGEN_TAKEPROFIT_PERCENT=1.2

# Trailing Stop
TRAILING_STOP_PERCENT=0.04

# Optional General Settings
PRIMARY_MINT_SYMBOL=USD
PRIMARY_MINT=EPjF... (USDC)
PRICE_UPDATE_SECONDS=60
TRADING_INTERVALS_MINUTE=1
SLIPPAGE=50
```

---

## 🧠 Strategy Overview

### 🟢 Buy Logic
- **Retail Mode**: Requires both an EMA crossover **and** low RSI (oversold) condition.
- **Degen Mode**: Requires an uptrend + price below lower BB **and** RSI below threshold.
- Configurable thresholds make strategy tuning easy.

### 🔴 Sell Logic
- **Stop Loss**: Activated if price drops below configured SL multiplier.
- **Take Profit**: Takes partial or full profit once target is hit.
- **Trailing Stop**: Follows gains upward, exits only if price drops from peak.
- **Momentum Exit**: Uses RSI + Bollinger Band + EMA reversal to confirm top exits.

---

## 🛠 Installation

Install dependencies:
```bash
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Or with Poetry:
```bash
pip install poetry
poetry install
```

---

## 🧪 Running the Bot

Run locally with:
```bash
python3 soltrade.py
```

Or via Docker:
```bash
docker build -t soltrade_bot .
docker run -d --name soltrade_bot \
  -e API_KEY=your_api \
  -e WALLET_PRIVATE_KEY=your_wallet \
  -e SECONDARY_MINT=your_token \
  soltrade_bot
```

---

## 📦 Market Requirements

- You must hold at least **1 of the PRIMARY_MINT token** (e.g. USDC).
- Keep at least **0.1 SOL** in your wallet to cover transaction fees.
- Bot relies on [Jupiter Aggregator](https://jup.ag) for swap execution.

---

## 📜 License & Credits

This fork is based on [Soltrade by noahtheprogrammer](https://github.com/noahtheprogrammer/soltrade), used and modified with credit to the original author.

This version is maintained as a **private project** and not intended for general distribution at this time.
