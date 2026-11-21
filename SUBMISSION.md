# Boss: submission

**Repo:** https://github.com/techadnank9/boss

## What we built

Every shopping agent works for a platform. Boss works for you.

Boss is a personal agent that runs other shopping agents. You type one request and your rules. Boss briefs three
buying agents, each with its own strategy (Muse-style: web, Meta catalog, Marketplace; Instinct-style: Shopify
stores with Shop Pay; Open web: major retailers, lowest price). Each agent searches the live web and comes back with
one real product, price, seller and link. Boss reranks the bids, rejects any that break your rules, picks a winner,
and gives a reason and score for every agent.

You make the final call. Approve, and Boss re-checks the live price and stock, then opens the real product page. It
never pays for you. Overrule, and your reason becomes a lesson every agent hears next time, and that agent's trust
score drops.

Every search, bid, verdict, approval and overrule is written to an audit trail you can open in the app, filtered by
agent, with the full payload of each step.

Pages: landing (`/`), how it works as a flowchart (`/how-it-works`), the app (`/app`).

## Sponsor tools we used

- **SingleStore:** the audit trail. Every step is a row in `events`; the agent scoreboard, lessons and the
  analytics panel (average time and price per agent, price gap between winners and losers, rejection reasons,
  approve vs overrule) are SQL over that table.
- **Superlinked SIE Serverless:** reranks every bid against the request and rules with `Qwen/Qwen3-Reranker-0.6B`
  before Boss judges, logged as `bids_reranked`.
- **Cognee (Cognee Cloud):** long-term memory. Overrule lessons and approved orders are remembered; each new request
  recalls matching memories for the agents and the judge, logged as `memory_recalled`.
- **Amplitude:** every audit step is sent as a `trail_<step>` event with agent, price, latency and scores, plus
  decision events (`bid_won`, `bid_rejected`, `user_rejected`, `order_approved`).
- **Firedrill:** drills that try to fool Boss before it touches money: a $30 price jump at checkout, a wrong size,
  the cheapest seller going out of stock, and a vague request (`drills.py`), with the Firedrill CLI and MCP
  connected to our workspace.

Also used: Claude with live web search for the buying agents and the judge, and Meshy for the 3D Boss character.

`python check_sponsors.py` calls each sponsor with the app's own config and regenerates `sponsors.html` from the
live results.
