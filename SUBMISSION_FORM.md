# Boss: submission form fields

## Project name
Boss

## One-sentence description
Boss is a personal agent for shoppers that runs a team of buying agents: they search the live web and compete for your order, Boss picks the best real offer against your rules, explains why, and keeps every step on the record.

## Project description
Every shopping agent works for a platform. Boss works for you.

You type one request and your rules. Boss briefs three buying agents, each with its own strategy (one modelled on how Meta's Muse shops, one on Instinct, one on the open web). Each searches the live web and returns one real product, price, seller and link. Boss reranks the bids, rejects any that break your rules, picks a winner, and gives a reason and score for every agent.

You make the final call. Approve, and Boss re-checks the live price and stock, then opens the real product page. It never pays for you. Overrule, and your reason becomes a lesson every agent hears next time, and that agent's trust drops.

How we used the tools:
- **SingleStore** keeps the audit trail. The scoreboard and analytics are SQL over it.
- **Cognee** remembers lessons and approved orders and briefs the agents before each run.
- **Superlinked SIE** reranks every bid against the request.
- **Amplitude** records every step of every run as an event.
- **Firedrill** drills Boss against price jumps, wrong sizes, sold-out sellers and vague requests.

Next: Boss sends the same request to the real Muse and Instinct and makes them compete too.

## Team size
1 (or add teammates)

## Tools and tech partners used
Click these event partners:
- Cognee
- Amplitude + Statsig
- Superlinked
- Firedrill
- SingleStore

Add your own:
- Claude (Anthropic)
- Meshy
- ElevenLabs

## Working project URL
Leave blank (runs locally; not deployed)

## Demo video URL
(paste your uploaded video link)

## GitHub repository
https://github.com/techadnank9/boss
