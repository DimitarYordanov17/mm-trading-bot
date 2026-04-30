# XAUUSD Trading Signal MVP

A rapidly built algorithmic trading signal prototype for XAUUSD, developed and deployed in one day from idea to live monitoring.

The system connects to MetaTrader 5, processes live 1-minute market data, generates experimental trading signals using technical indicators, and publishes signal updates to a Telegram channel.

> This is an experimental MVP, not financial advice and not a proven profitable trading strategy.

## What It Does

- Connects to MetaTrader 5
- Monitors XAUUSD on the 1-minute timeframe
- Calculates EMA and RSI-based indicators
- Uses 15-minute higher-timeframe bias filtering
- Generates BUY/SELL signals during active session hours
- Tracks virtual TP/SL levels
- Sends live updates to Telegram
- Runs continuously on a cloud instance

## Why This Project Matters

This project was built to demonstrate rapid end-to-end execution:

- idea → working prototype
- prototype → deployed cloud process
- live market data → signal logic
- signal logic → Telegram notification system
- local script → continuously running MVP

The main focus is not the strategy itself, but the ability to build, deploy, monitor, and iterate on a live automation system quickly.

## Architecture

```text
MetaTrader 5
    ↓
Live XAUUSD M1 candles
    ↓
Indicator Engine
EMA / RSI / 15M Bias
    ↓
Signal Engine
BUY / SELL / No Trade
    ↓
Position Tracker
Virtual TP / SL monitoring
    ↓
Telegram Bot
Live alerts channel
```

## Example Output

Below is a sample of how signals and updates are delivered in the Telegram channel:

![Telegram Signal Demo](demo.png)

This demonstrates:

- Clean LONG/SHORT signal formatting
- Trade ID and entry tracking
- Real-time TP/SL update replies
- Minimal, readable structure for fast decision-making
