# RiskLens Interview Guide

How to talk about this project honestly and confidently. You are a student who built a thoughtful learning project, not a fraud engineer. That is a strength if you frame it correctly: you can explain every line, you know the limits, and you chose transparency on purpose.

**Numbers from the default run** (verify with `python main.py` before an interview): 663 synthetic transactions, 614 ALLOW / 27 REVIEW / 22 BLOCK, 9 controls, 55 tests.

---

## 30-second explanation

> "RiskLens is a Python project I built to understand how a financial platform turns security signals into decisions. It generates synthetic transactions, scores each one from 0 to 100 using nine transparent controls, like new device, new country, unusual amount, and impossible travel, and returns allow, review, or block with an explanation of exactly which signals fired. I deliberately avoided a black-box model because I wanted every decision to be something an analyst could understand and challenge."

## 60-second explanation

> "I wanted to learn how security-risk teams make consistent decisions at scale, so I built RiskLens. It generates about 660 synthetic transactions for 55 fake users, mostly normal behavior plus injected anomalies like account takeover, card testing bursts, and impossible travel.
>
> Each transaction is checked against nine controls. Some compare against the user's own history, like a new device or an amount far above their median. Others look at context, like IP reputation, failed logins, or how fast someone would have to travel between two locations. Every control adds a documented number of points, the total is capped at 100, and thresholds turn it into allow, review, or block.
>
> The part I care most about is the explanation. Each decision lists the triggered controls and points, so the score is like a receipt. I also wrote 55 tests and set up CI. And I was careful about the limits: the data is synthetic and the weights are illustrative, so I treat it as a learning tool and a baseline, not a production system."

---

## Why did you build this?

> "I was interested in security risk, and I realized I didn't understand how the signals actually become a decision. I could describe fraud in the abstract, but not how you'd weigh a new device against a risky IP, or what you'd show an analyst. Building it forced me to make those choices concretely, and to see where they get hard, like false positives and cold-start users."

## Why use rules instead of machine learning?

Good answer, in your own words:

- **Explainability:** an analyst can see exactly why something was flagged. A customer-facing decision often needs a reason.
- **Auditability:** rules are versionable and reviewable. A compliance or risk team can inspect a change to a weight.
- **Fast to implement:** I had no labeled fraud data. ML needs labels; rules only need domain reasoning.
- **Easier threshold tuning:** if REVIEW volume is too high, I change one number and see the effect.
- **A useful baseline:** any future ML model should have to beat a simple rule set to justify its complexity.
- **Real systems combine both:** rules for known, high-confidence patterns and hard policy limits, ML for subtler patterns. Rules are not "worse", they do a different job.

> "With synthetic data I'd only be teaching a model my own assumptions, so rules were the honest choice. I see ML as a next step, compared against this baseline."

## How does impossible travel work?

Keep it simple:

> "For each user I remember where their last trusted transaction happened and when. For a new transaction I compute the distance between the two locations with the haversine formula, which is great-circle distance on a sphere, and divide by the elapsed time to get an implied speed. If that speed is faster than a commercial flight, around 900 km/h, it's impossible travel. If it's above about 500 km/h it's only implausible and scores less. I ignore anything under 300 km so normal city-to-city movement doesn't count."

Example from the repo: 7,084 km in 1.1 hours is about 6,160 km/h. Nobody flies that fast, so the account is probably being used from two places.

Follow-up you should know: VPNs and mobile networks can make locations unreliable, so this signal is strong but not proof.

## How did you choose the weights?

> "They're illustrative risk weights, not statistically calibrated. I ranked signals by how strongly they suggest compromise and how hard they are to trigger innocently. Impossible travel is the heaviest because it's rarely innocent. New device is lighter because people buy new phones. I also set a design rule that no single weak signal can block, so a new device alone gets 15 points and can't cross the 30-point review line. With real labeled outcomes, I would fit or tune these weights against precision and recall instead of my judgment."

Never say the weights are "optimal" or "accurate". They are documented and defensible, not validated.

## What is the biggest limitation?

> "The data is synthetic, and I have no labeled production outcomes. I wrote both the scenarios and the rules, so when the rules catch the scenarios it only shows the logic works as designed. It says nothing about real-world accuracy. That's why I framed my results table as 'controls behave as designed', not 'detection rate'."

## How would you improve it?

- **Labeled datasets** with confirmed fraud and confirmed legitimate outcomes.
- **Precision and recall** to measure how many flags are correct and how much fraud is missed.
- **Analyst feedback loop** so review outcomes adjust weights.
- **Configurable thresholds** from a config file rather than code.
- **Streaming / real-time processing** instead of batch scoring.
- **Anomaly detection** to catch patterns no hand-written rule covers.
- **ML alongside rules**, compared against this baseline.
- **Graph features** like many accounts sharing one device or IP.

## False positives

> "A false positive is a legitimate transaction that gets flagged. It matters operationally because every REVIEW costs analyst time and every wrongly blocked customer has a bad experience and might lose trust. A false negative is fraud that gets through, which costs money and harms customers. You are always trading these off, so thresholds are a business decision, not just a technical one."

Repo example: a customer traveling abroad gets a new-country signal. It's a plausible false positive, which is why new country alone (20 points) is kept below the review threshold.

## Explainability

> "If a transaction is blocked or sent to review, the analyst needs to know exactly why, both to verify it quickly and to challenge the system if it's wrong. It also matters for customers who ask why something was declined, for audits, and for improving the rules. In RiskLens the score is literally the sum of listed control points, so nothing is hidden."

---

## 10 likely technical questions

**1. Walk me through what happens to one transaction.**
It's converted to a `Transaction` object. Every control function runs against that user's history and returns a signal (with points and a detail string) or nothing. Points are summed and capped at 100, thresholds pick the decision, an explanation string is built, and then the user's history is updated.

**2. What is "no look-ahead" and why does it matter?**
Transactions are sorted by time and each one is scored using only earlier events. If a rule could see future data, results would look better than any real-time system could achieve.

**3. What is the cold-start problem, and how do you handle it?**
A brand-new user has no history, so "new device" would be true for every first transaction. Baseline controls stay silent until a user has 3 trusted transactions. The new-account control still applies, since it doesn't need history.

**4. Why don't blocked transactions update the user's baseline?**
If they did, an attacker's first blocked attempt would add their device and country to the "normal" list, and the second attempt would look normal. Blocked events still count as attempts, so velocity sees them.

**5. Why compare amounts to the median instead of the average?**
The median is robust to outliers. One past large purchase would inflate a mean and hide future unusual amounts.

**6. How do you know the tests are meaningful?**
They test each control's tiers and boundaries (for example 29 vs 30 vs 60 for the thresholds), the 100 cap, cold start, and the baseline poisoning rule. Each behavior I claim in the README has a test behind it.

**7. Why is the scoring additive?**
It keeps explanations honest: the listed points sum to the score. The downside is it ignores interactions between signals, which a real system might model.

**8. What would happen with real data?**
The pipeline structure would carry over, but weights and thresholds would need recalibration, and I'd need to handle messy data, missing fields, shared devices, and VPNs. I'd measure precision and recall first.

**9. How would you reduce false positives without missing fraud?**
Look at which controls drive false positives, tune those weights or tiers, add allowlisting or trust signals, and use analyst review outcomes as feedback. Measure the change before and after.

**10. Why did the amount-spike and velocity scenarios get only partial detection?**
That's a designed trade-off and a real finding. Velocity only triggers after enough attempts accumulate, so the first few pass. Amount spikes below the top tier score under 30 alone. Catching more would raise false positives, so it's a tuning decision, not a bug.

---

## Things to avoid saying

- Don't claim it detects fraud "accurately", "with X% accuracy", or that it's production-ready.
- Don't say it uses or resembles any company's real system or data.
- Don't imply professional fraud experience. Say "learning project" and "student project".
- If you don't know something, say what you would check. That is a good answer in a risk role.
