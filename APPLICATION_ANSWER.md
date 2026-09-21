My favorite project is RiskLens, an explainable transaction security-risk engine I built in Python. It scores synthetic transactions from 0 to 100 and returns an allow, review, or block decision, along with a plain-English list of exactly which signals fired.

I built it because I wanted to understand how a financial platform turns security signals into consistent operational decisions. Instead of training a black-box model, I wrote transparent controls that an analyst could challenge and tune: transaction velocity, unusual amounts compared to a user's own history, new devices, new countries, IP reputation, and impossible travel, plus a few context signals.

The most useful lesson was how much of risk work is trade-offs. A weak signal alone shouldn't block a customer, but being too cautious lets real anomalies through, and my own results showed both. I also saw why auditability matters when a decision affects a person.

It uses Python, pandas, NumPy, Matplotlib, pytest, and GitHub Actions, with 39 tests and entirely synthetic data.

GitHub: [PASTE_REPOSITORY_URL]
