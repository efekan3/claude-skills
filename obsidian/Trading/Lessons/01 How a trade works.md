---
tags: [trading/lesson]
lesson: 1
status: todo
---
# 1. How a trade works

*Before strategy comes mechanics: what you actually pay, and why the price on screen isn't always the price you get.*

### Bid, ask and spread

Every market has buyers (the **bid**, the highest price someone will pay) and sellers (the **ask**, the lowest price someone will sell for). The gap is the **spread**. Open the Chart tab: the order book shows asks in red above and bids in green below.

### Market vs. limit orders

- **Market order**: buy or sell right now at the best available price. Fast, but you pay the spread and accept whatever the price is.
- **Limit order**: “only buy at €X or lower” (or sell at €X or higher). You control the price, but it may never fill.

### Fees

Exchanges charge a fee on every trade, typically 0.1–0.25% per side. A buy and a sell together cost about 0.5%. That sounds small, but 50 round trips cost about 25% of the money you trade.

> [!example]
> Example: you buy €1,000 of BTC with a 0.25% fee. You get €997.50 worth of BTC. The price has to rise about 0.5% before selling breaks even.

> [!todo] Try it in Koersdesk
> In Practice, place one market buy of €200 and one limit buy 2% below the current price. Watch which one fills.

## Check yourself

**You want to buy ETH only if it drops to €2,000. Which order?**
- Market order
- Limit order at €2,000
- Stop-loss at €2,000

> [!success]- Answer
> Limit order at €2,000. A limit buy waits until the price reaches your level or lower.

**Why does trading very often hurt results even with a 50% win rate?**
- The spread and fees are paid on every trade
- Exchanges block frequent traders
- Charts are less accurate

> [!success]- Answer
> The spread and fees are paid on every trade. Costs are certain; edge is not. Each trade starts slightly negative.

## My notes

-

---
Related terms: [[Spread (bid and ask)]], [[Limit order]], [[Market order]], [[Fees]], [[Market cap]], [[Stablecoin]]
Next → [[02 Risk first position size]]  ·  [[Trading Dashboard]]
