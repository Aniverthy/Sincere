# Project Sincère — Dating App Project Summary

## Core Concept
An equal-playing-field dating app addressing the well-known gender imbalance in dating apps (typically ~70% men / 30% women). The core differentiator: **enforced 1:1 active gender ratio** via a male waitlist system, rather than letting the platform skew naturally.

---

## 1. Gender Ratio & Waitlist System

**Problem:** Standard signup-based admission creates permanent skew, and churn (e.g., women leaving) breaks a naive 1:1 admission rule.

**Decisions made:**
- **Geographic scope — SUPERSEDED, revised (DECIDED):** admission queues (free/paid/auction) no longer run at the state level. Instead, each queue instance is scoped to a **fixed, deterministic spatial partition using H3** (Uber's hexagonal hierarchical spatial index) — chosen over Census-defined metro areas (CBSAs, US-specific and inapplicable here) and over India's own Urban Agglomeration (UA) boundaries, since UA only covers the 475 named urban spreads identified in the 2011 Census and leaves everyone outside them (most of rural/small-town India) with no defined region at all. H3 tiles the entire country with no gaps, at whatever resolution is chosen. A learned/clustering approach (e.g., k-means) was explicitly rejected: it has no principled way to pick cluster count, and cluster boundaries drift as new users sign up, which would destabilize the active_men/active_women denominators the ratio system depends on. **State is retained only as the payment/tax/legal jurisdiction layer (see Section 6) — fully decoupled from the admission-queue boundary**, confirmed a non-issue for the India launch (see Section 6). Each hex queue is its own self-contained instance of the three-tier queue system with its own active men:women ratio, waitlist, and auction.
- **Hex resolution — single resolution, DECIDED not to vary by density.** Considered and rejected a density-tiered variable resolution (finer hexes in cities, coarser in rural areas) — technically sound with H3 specifically (unlike k-means, parent/child hex hierarchy is exact and never drifts), but adds real ongoing complexity (a density-threshold rule, reclassification logic, heterogeneous per-region statistics) for a benefit already delivered by user-selected candidate-pool radius (see below), which handles density variation at query time independent of hex boundaries. **Also decided against re-resolving the grid when future census data updates**: changing H3 resolution re-derives an entirely new set of hex IDs from scratch — it isn't a clean split/merge of existing regions, so it would silently reset every queue's active_men/active_women counts and erase waitlist region-context. Treat any future resolution change as a rare, deliberate migration project (akin to database resharding), never a routine recalibration. **Numeric value DECIDED: H3 resolution 6** (~36 km² per hex, nearest discrete H3 level to a ~50 km² pragmatic target), a starting point to be validated against real soft-launch data (see below).
- **Candidate-pool radius — SUPERSEDED, corrected (DECIDED): H3/hex scoping applies ONLY to the admission-queue system (free/paid/auction, ratio balancing), not to matching itself.** Once a user is admitted, their day-to-day candidate pool is based purely on their **own location + a radius they select themselves, capped at a 100km maximum** (raised from an initial 50km cap to reduce thin/empty pools in sparsely populated regions — applied uniformly, not just in sparse areas, for simplicity). This replaces the earlier "platform-set, non-adjustable, density-tiered adaptive radius" concept entirely — that mechanism is dropped. Two clearly separate systems now: (1) H3 hex region → which queue/ratio instance a user's admission is governed by; (2) user-chosen radius (≤100km) from their own location → who actually shows up in their daily 15 matches. A user's radius choice has no bearing on their queue/admission treatment (consistent with the earlier decoupling principle, just with "fixed radius" replaced by "user's own choice, capped").

- **Resolution calibration method (DECIDED):** since a survey-based "% interested" estimate was considered and rejected (self-reported interest is a weak, geographically-inconsistent proxy for actual sustained usage — bias runs in different directions in different regions, and "interested" is several funnel stages away from the app's own 30-day-active definition), the approach is instead: (1) use Census UA population + area figures to get real population density per target city; (2) apply a starting active-user-adoption percentage benchmarked against existing Indian dating app market data (e.g., dating app active users are roughly 3-4% of India's smartphone base nationally, concentrated in the 18-35 age band and in major metros) rather than a survey guess; (3) compute expected active users per hex at candidate resolutions using H3's published average-area-per-resolution table, and pick the resolution that keeps expected active-user counts per hex above a statistical stability floor even in the least-dense target launch city; (4) treat this as a starting estimate only — validate and correct it against real 30-day-active data from the first city's soft launch (Section 5) before finalizing for full national rollout, since real usage data is unambiguously better ground truth than any market-benchmark estimate.
- **State-level skew tradeoff — RESOLVED by the above.** The prior tradeoff (a state's overall ratio looking healthy while a specific dense sub-area is skewed) was a direct consequence of state being both the admission unit and larger than the actual matching radius. With admission now scoped to hex regions that better reflect real population clusters, this mismatch is substantially reduced (though not fully eliminated — see open items below).
- Track **active users** (e.g., logged in within last 14–30 days), not cumulative signups, as the ratio basis.
- **Active-user definition (DECIDED):** active = logged in within the last 30 days **AND** performed at least one swipe/like in that window (login alone doesn't count, to avoid phantom "active" accounts inflating the ratio). Chosen to align with the existing 30-day account-deletion grace period for consistency.
- Use a **tolerance band with hysteresis (DECIDED default):** stop admitting men at active_men ≤ active_women × 1.05, resume only once active_women recovers past × 0.95. Prevents constant on/off "flapping." Can be tightened later once real churn volatility data exists.
- **Never evict existing men** when ratio dips — only freeze new admissions from the waitlist.
- Maintain a **conservative admission buffer** (admit men up to ~90–95% of active women count) so normal churn doesn't require reactive action.
- Balance ratio **per metro/hex region** — each region runs its own independent queue/ratio instance (admission ceiling, hysteresis, buffer), rather than one global national ratio or per-user-radius segmentation. A global 1:1 could otherwise mask badly skewed individual regions.
- Use **churn prediction** (declining sessions, no matches, fewer messages, **and now — since chat is in MVP scope — declining message frequency and growing response latency per match**, see Section 2) to flag at-risk women proactively, rather than reacting after they quit.
- Admit from the waitlist prioritized by **engagement quality**, not just FIFO or payment.

**Open decision needed:**
- Exact tolerance % and buffer % — needs real usage data or a launch-time judgment call.
- What defines "active" precisely (days threshold, minimum action like a swipe/message vs just app open).
- Whether waitlist priority should factor in profile completeness/verification status in addition to engagement.
- **User-selectable radius — UI and implementation mechanism (DECIDED):** UI is a **slider, range 1–100km** (confirmed — the earlier "1–50km" was an error; 100km remains the locked max cap with its original reasoning: majority of users won't travel further than that to meet a partner). Location mechanism: the app records the user's location **every time the app is opened**, storing it as `last_recorded_location` — this stored value (not a continuous background GPS stream) is what candidate-pool filtering runs against, refreshed on each app open rather than tracked live.
- **Multi-state metro handling (RESOLVED for India launch):** confirmed not a concern for the initial India launch — GST is a single nationally uniform rate (not state-varying like US sales tax) and payment aggregators are regulated centrally by the RBI, not state-by-state, so a queue region spanning multiple states creates no payment/tax/licensing conflict. The only related detail is that GST invoices require a "place of supply" (state) field to split CGST/SGST correctly — a backend invoicing detail derived from billing address, with zero effect on queue assignment or matching. **Revisit only if/when expanding to a country with state-level tax or payment-licensing variance** (e.g., the US), where this reconciliation becomes a real architectural question again.

---

## 2. Matching Algorithm

**DECIDED: Hybrid model, 15 matches delivered per day.**
Combines curated batch-style delivery (stable-matching principles) with enough daily volume to feel like a full dating app, rather than one match/day (too low) or unlimited infinite swipe. This locks the core UX shape: users get a fresh curated set of 15 profiles daily rather than an endless feed.

**Compatibility scoring components (steady state, post cold-start):**
- Stated preference similarity (interests, lifestyle, cosine similarity)
- **Reciprocity prediction** (will they like me back — flagged as the most important and most commonly under-built signal)
- Collaborative filtering (behavioral similarity to other users)
- **Engagement/responsiveness score — refined (DECIDED), now powered by chat data:** recency-weighted response behavior at the individual-match level, computed from **chat message count and response latency** now that in-app chat is in MVP scope (Section 8). A match going stagnant (one side consistently ignoring messages / slow-to-respond / leaving matches unopened) temporarily lowers that match's priority in the active stack — same underlying idea as the platform-wide churn-prediction in Section 1, applied per-match. The same chat-activity data (declining message frequency, growing response latency) also feeds the **churn-risk flag** in Section 1 — identifying users likely to go inactive soon, before they actually stop using the app.
- Freshness boost for new users
- Personalized visual pattern similarity — **weight decided (DECIDED, revised): fixed at 0.05**, a low-priority input from launch rather than shipping at weight = 0 pending an A/B test. Still capped/discounted at very high similarity (>0.95, per Section 3's sibling-resemblance mitigation) and defaulted to neutral for cold-start users with little like-history — those safeguards remain, only the "off until proven" gating is removed.

**"We Met" real-world feedback loop (DECIDED, unblocked by chat — see Section 8):**
- Adapted from Hinge's approach: an optional, periodic post-match prompt asking whether the two people actually met in person and whether it was a good real-world fit.
- Purpose: closes the gap between "swiped/matched" (a weak proxy — only shows profile appeal) and genuine compatibility (ground-truth signal from a real interaction). Used to recalibrate the reciprocity-prediction and collaborative-filtering models against real-world outcomes, not just in-app swipe/chat behavior.
- **No longer categorically deferred to v2** — chat being in MVP removes the technical blocker. Rollout timing still depends on accumulating a large enough base of real conversations to survey meaningfully, so it may launch shortly after MVP rather than on day one, but it's no longer gated on a v2 chat build.
- **Trigger rule (DECIDED, fully specified):** prompt fires once a matched pair reaches a **minimum total message count across a 3-day window** (no per-day minimum — total volume across the 3 days is what counts, not activity spread evenly across each day). **Threshold (DECIDED): 20–30 messages** — chosen as a moderate bar representing meaningful conversation depth, over a low threshold (10–15, catches matches too early/shallowly) or a high one (40+, only the most engaged conversations, missing many genuine matches).
- **Re-ask logic (DECIDED):** if the first response is "not yet met," the prompt **re-fires periodically (e.g., every 1–2 weeks)** until the pair either confirms they've met or unmatches. This addresses the earlier concern about a single-shot prompt undercounting slow-burn matches that meet later than day 3.
- **Model-retraining feedback mechanism (DECIDED): periodic batch retraining** (e.g., weekly or monthly) using accumulated "We Met" responses, rather than a real-time per-response feature update. Chosen for simplicity and stability — batch retraining is easier to validate before deployment (check the new model against a holdout set before it goes live) and avoids the operational complexity of continuously retraining on a low, irregular trickle of survey responses. Exact cadence (weekly vs. monthly) not yet set — likely determined by how quickly meaningful response volume accumulates once live.

**Variable reference table — every variable used across cold-start and post-graduation scoring:**

| Variable | How it's calculated | What it represents |
|---|---|---|
| `preference_similarity` | Cosine similarity between two users' stated-interest/tag vectors (e.g., hobbies, lifestyle tags) | How much two people's declared interests overlap |
| `demographic_fit` | Function of age-gap and distance between two users, normalized to a 0–1 score | Basic compatibility on hard demographic dimensions |
| `prompt_text_similarity` | Text-similarity score (e.g., embedding cosine similarity) between two users' onboarding prompt answers | Thematic overlap in freeform written answers — a stand-in signal before real behavior exists |
| `reciprocity_prediction` | Output of a **gradient-boosted trees model (XGBoost/LightGBM, DECIDED)** predicting P(candidate likes user back), using features like shared interests, distance, activity level | Predicted likelihood the *other* person would also swipe right — the most heavily weighted post-graduation signal |
| `collaborative_filtering` | Output of a **matrix factorization model (SVD/ALS, DECIDED)** run over the platform's swipe history | "People with swipe patterns like yours also liked this profile" — behavioral similarity signal |
| `engagement_score` | Recency-weighted, computed per-match from **chat message count and response latency** (chat now in MVP scope) rather than a lifetime average | How actively engaged a specific match currently is — a stagnant/slow-responding match's score decays; same underlying data also feeds churn-risk flagging (Section 1) |
| `freshness_boost` | Decay function of days since signup (highest right after joining, tapering over time) | Temporary visibility boost so new users aren't buried under established profiles |
| `visual_pattern_similarity` | Cosine similarity between a candidate's face embedding and the embeddings of profiles the user has previously liked (FaceNet embeddings) | Resemblance to the user's past likes — **fixed low-priority weight (0.05), ships from launch** (no longer gated behind an A/B test); still capped/discounted above 0.95 similarity and neutral for low like-history, per Section 3 |
| `confidence` | **Diminishing-returns (logarithmic) curve (DECIDED)** — rises fast in early swipes right after graduation, then levels off toward 1.0 | How much weight to give the learned model vs. the cold-start heuristic for a given user at a given point in time |
| `cold_start_score` | `0.45 × preference_similarity + 0.30 × demographic_fit + 0.25 × prompt_text_similarity` | The full pre-graduation heuristic score (no behavioral data involved) |
| `final_score` (post-graduation) | `0.35 × reciprocity_prediction + 0.25 × collaborative_filtering + 0.20 × preference_similarity + 0.10 × engagement_score + 0.05 × freshness_boost + 0.05 × visual_pattern_similarity` (visual_pattern weight now fixed/decided; other weights remain illustrative, not yet tuned) | The ranking score used to select and order each user's daily 15 |
| `blended_score` | `confidence × final_score + (1 − confidence) × cold_start_score` | The actual score used during the transition window between graduation and full model maturity |
| `exploration_rate` | Fixed percentage of the daily 15 chosen outside pure top-ranked order — ~40% pre-graduation, ~15% post-graduation | Controls how much intentional variety/randomness is injected, both for early data collection and to avoid winner-take-all visibility later |
| `candidate_pool_radius` | **User-selected via slider, range 1–100km** (confirmed — see Section 1), filtered against `last_recorded_location`, captured on each app open | Defines the geographic pool a user is matched within; entirely separate from and has no effect on their H3-based admission/queue treatment |
| `last_recorded_location` (NEW) | Captured fresh **every time the app is opened** (not continuous background tracking) | The location value candidate-pool radius filtering runs against; also the location basis for Section 7's "current/last-known location only" retention policy |
| `swipe_ratio` (anti-spam, feeds warning/ban track, not matching score) | % of right-swipes where profile view time was under 10 seconds (both figures illustrative), over a rolling window | Detects indiscriminate/low-intent swiping; above ~70% triggers a warning (3 warnings across separate occasions, then ban) rather than a matching-score penalty |

**Model and transition method choices (DECIDED):**
- **Reciprocity-prediction method: gradient-boosted trees (XGBoost/LightGBM).** Chosen over logistic regression (too simplistic for non-linear feature interactions), factorization machines, two-tower neural networks, and Deep & Cross Networks — the latter three offer more power but need more data volume/scale to outperform simpler methods, which doesn't fit a pre-launch app. Best complexity-to-value ratio at this stage.
- **Collaborative-filtering method: matrix factorization (SVD/ALS).** Chosen over nearest-neighbor (scales poorly as user base grows), neural collaborative filtering, and graph neural networks — same rationale, these become worth the added complexity once the platform has enough scale that simpler methods start plateauing, not before.
- **Blend-confidence curve shape: diminishing-returns curve** (e.g., logarithmic) — confidence rises fast in the early swipes right after graduation, then levels off as it approaches 1.0. Chosen over a linear ramp or step function on the reasoning that early swipes carry more new information than later ones, so the model should lean into the learned score quickly rather than waiting out a fixed linear window.

**Open decision needed:**
- Exact scoring weights — illustrative starting points only (except `visual_pattern_similarity`, now fixed at 0.05), need tuning once real data exists.
- Whether the 15 are delivered all at once (e.g., at midnight) or trickled through the day — affects notification design and engagement patterns.
- "We Met" prompt cadence, response-rate expectations, and exact mechanism for feeding survey responses back into model retraining — timing unblocked by chat, but detailed design still pending (see below for the proposed 3-day-consistent-interaction trigger).

---

## 3. Face-Based Matching — Final Legal/Ethical Direction

**Rejected approach:** Attractiveness/beauty scoring (face + optional body), visible to users, retestable every 3 days.

**Why rejected:**
- Legal exposure: facial-geometry-derived scoring is treated as biometric data processing under BIPA (Illinois), GDPR/UK GDPR (special category data), and India's DPDP Act — carries major fines/statutory damages precedent (Clearview AI, Facebook BIPA settlements).
- Extracting *named, categorized* features (jawline, bone structure, etc.) is legally worse than similarity-only embeddings — closer to literal statutory language on "facial geometry."
- Using any face-derived data for **marketing** requires fully separate, explicit consent flows in every relevant jurisdiction — significant added legal surface for limited benefit.
- Wellbeing risk: a visible, periodically-refreshed appearance score is a known harmful pattern (linked to body image/disordered self-perception harms), independent of legality.
- Product research: **no major current app (Tinder, Bumble, Hinge) publishes a visible attractiveness score anymore** — Tinder's old Elo-style score was phased out of public visibility; Hinge's leadership has explicitly distanced from "gamified beauty score" models. Confirmed via research, not assumption.
- Doesn't actually improve match quality — two people with similar scores aren't more compatible with each other.

**Approved approach — "visual pattern matching" (personalized, not universal):**
- Use an **open-source face embedding model** (DeepFace, FaceNet, InsightFace, or VGGFace2) to generate a numeric vector representation of a face.
- Compare embeddings via **cosine similarity only** — no decomposition into named/labeled features (no "jawline width," no "cheekbone score").
- Use case: compare a candidate's embedding against the embeddings of people a *specific user* has previously liked, to produce a personalized "does this resemble your pattern" signal — analogous to Netflix recommending based on watch history, not a universal beauty rating.
- Score is **per-user-relative**, not global — same candidate gets different scores for different viewers.
- Discard raw images/embeddings after comparison where possible (data minimization) — reduces breach risk and biometric-data storage exposure.
- **Not connected to marketing use** in any form.
- Same embedding pipeline doubles as the **bot/duplicate detection system** (Section 4) — one model, two legitimate uses.

**Identified risk — relatives/siblings matching due to facial resemblance:**
Raw embedding similarity captures genetic/structural resemblance (bone structure, facial geometry) alongside stylistic resemblance, which is exactly what makes relatives appear similar. Mitigation:
1. **Dedicated hard-exclusion filter — DECIDED AGAINST, not deferred, dropped entirely.** A dedicated data-source-driven sibling/relative exclusion mechanism (contact/surname/address cross-checking) was considered and is **not going to be built** — judged unnecessary overhead relative to the actual risk, not merely postponed for MVP. The residual risk is accepted as a permanent tradeoff, not a temporary gap.
2. **Keep the visual-pattern signal's weight small** (fixed at 0.05, see Section 2), cap/discount very high similarity scores (>0.95 cosine, more likely a structural/duplicate match than real preference), and default to neutral (0.5) for users with little like-history rather than extrapolating from 1–2 likes. This is now the **sole, permanent safeguard** for this risk, not an interim measure pending a future hard filter.

**Face embedding model (DECIDED): FaceNet**, used via the DeepFace library (DeepFace acts as a wrapper — same integration code, swappable backend model by config string, similar in spirit to how LiteLLM abstracts multiple LLM providers). Rationale:
- Licensing: FaceNet (the standard `davidsandberg/facenet` implementation DeepFace wraps) ships under an MIT-style permissive license with no non-commercial restriction — safe to deploy commercially today with no vendor/licensing step required.
- By contrast, the other candidates all carried caveats: **VGG-Face**'s original weights are licensed Creative Commons Attribution-NonCommercial (research use only); **VGGFace2**-trained models (ResNet50/SENet50) are legally ambiguous for commercial use (dataset license doesn't explicitly cover the trained weights); **InsightFace/ArcFace** — despite MIT-licensed code — restricts its popular pretrained packages (buffalo_l, antelopev2) to non-commercial research only, requiring a separate paid commercial license from InsightFace to use in production.
- Accuracy tradeoff accepted knowingly: ArcFace/InsightFace is the current state-of-the-art in speed/accuracy, but founder confirmed general-vicinity similarity accuracy is sufficient for this use case (personalized visual-pattern signal + duplicate detection), not requiring best-in-class precision. FaceNet remains swappable later via DeepFace's abstraction if InsightFace is licensed down the line.

**Vector DB decision (DECIDED): MongoDB Atlas Vector Search.** Confirmed by founder — core backend is MongoDB, so Atlas keeps the embedding-similarity search inside the existing database (no separate system to run, no sync pipeline between operational and vector data). Revisit Qdrant later only if embedding search volume/filtering complexity becomes a genuine bottleneck post-launch (Qdrant offers better native ANN performance and cheaper self-hosted cost at larger scale, per current benchmarks) — not a launch-time concern.

**Open decision needed:**
- Confirm with a privacy lawyer, per target launch jurisdiction, whether even similarity-only embeddings require explicit biometric-processing consent language at signup (likely yes, at minimum for BIPA/GDPR markets) — this document does not substitute for that legal review.
- Decide data retention: fully discard embeddings after each comparison (safest) vs. retain temporarily for performance (needs justification if retained).

---

## 4. Bot & Duplicate Account Detection

**Decisions made — full pipeline outlined:**
- **Liveness detection** at signup: short in-app selfie/video capture with randomized prompts (blink, head turn) — stops static/stolen photo reuse and deepfakes. Prioritized over simple uploaded-photo verification.
- **Face embedding duplicate check**: new user's face embedding compared against existing user embeddings (vector similarity search) to catch the same person creating multiple accounts.
- **Profile-photo-to-verification-selfie match**: ensures uploaded profile photos match the live-verified person (stops the "verify with real face, then swap in stolen attractive photos" scam).
- **Behavioral/device signals**: device fingerprint reuse, IP clustering, inhuman/uniform swipe timing, signup velocity from a given referral source, spam-template bio text matching.
- **Indiscriminate swipe-ratio throttle — refined (DECIDED — adapted from Bumble's approach, now dwell-time based rather than pure right-swipe ratio):** detection is based on **time spent viewing a profile before swiping right**, not just the raw right-swipe percentage. If a user spends **under 10 seconds** on a profile before swiping right, and this pattern occurs on **more than 70%** of their right-swipes, it's flagged as low-intent/bot-like swiping. **Escalation policy (DECIDED):** first three occurrences trigger **in-app warnings** (on three separate occasions, not three strikes in one sitting); if the behavior continues after the third warning, the account is **banned**. This is a graduated response, not an immediate penalty — distinct from the composite bot-risk score's auto-approve/auto-reject/human-review routing, since this specific behavior (fast indiscriminate swiping) gets its own warning-then-ban track rather than going straight to human review. **Exact figures (10 seconds, 70%, 3 warnings) locked as launch defaults for now (DECIDED) — not derived from real usage data yet; flagged for refinement post-launch, see Section 9 (Future Improvements).**
- **Composite bot-risk score** combining the above signals.
- **Flag for manual review, don't auto-ban** — false positives (e.g., identical twins, poor lighting) are common enough that auto-rejection risks real users, especially pre-launch when thresholds are unvalidated.

**Manual review operations — automation strategy (DECIDED approach):**
- **Tiered auto-decision, not "review everything flagged."** Composite bot-risk score routes accounts into three bands: auto-approve (clearly fine), auto-reject/freeze (clearly bot/fraud), and human-review (the genuinely ambiguous middle only). This is expected to route only a small fraction (illustratively 5–15%) of flagged accounts to a human, not the full flagged set.
- **Liveness/duplicate-check pipeline runs fully automated end-to-end** — a human is only pulled in when the automated pipeline itself reports low confidence (e.g., borderline similarity score, poor-quality capture), not as a default step for every signup.
- **Staffing model — REVERSED (DECIDED): in-house review for launch.** Founder will handle the ambiguous-tier review queue directly at MVP/launch stage, rather than an on-demand third-party vendor. Planned transition to a third-party moderation vendor as signup volume grows past what one person can handle — logged as a scale-triggered change, see Section 9 (Future Improvements). The tiered auto-approve/auto-reject/human-review routing itself is unchanged — only who sits in the "human" seat of that routing has changed.
- **Feedback loop**: every human review decision logs whether it agreed with the automated score, and periodically retunes the auto-approve/auto-reject thresholds — the ambiguous middle band (and thus the human workload) is expected to shrink over time as thresholds get validated against real outcomes.

**Open decision needed:**
- ~~Exact similarity threshold for "duplicate person"~~ — **DECIDED: >90% cosine similarity flags for human review** (not auto-ban — routes into the tiered review system below, consistent with the "flag, don't auto-reject" principle). Still worth validating this exact cutoff against a proper validation set once real signup volume exists, since 90% was set as a working starting point rather than derived from a measured false-match rate — but the threshold itself is no longer an open design question, just a candidate for future tuning.
- Exact auto-approve/auto-reject score cutoffs (illustrative bands only so far) — needs tuning once real signup data exists.
- ~~Staffing model~~ — **DECIDED: in-house at launch** (see above). Third-party vendor selection deferred to a future scale-triggered transition, see Section 9 (Future Improvements).
- ~~Which specific vector DB / infra for embedding similarity search at scale~~ — **DECIDED: MongoDB Atlas Vector Search** (see Section 3).

---

## 5. Cold Start Strategy (Pre-Data Launch Phase)

**Decisions made:**
- Cold start requires substituting **explicit data** for the behavioral data that doesn't exist yet: rich onboarding (prompts, tags, lifestyle fields) matters more here than in a mature app.
- Use **heuristic scoring weights** at launch (preference similarity, demographic fit, prompt-text similarity) instead of learned weights — explicitly acknowledged as a starting guess, not a tuned model.
- Substitute reciprocity prediction with **coarse population-level priors** (age-range overlap, distance decay) until real reciprocity data accumulates.
- Consider **manual/concierge curation** of the first cohort (profile quality review, possibly human-assisted early matching) — standard practice for two-sided marketplace bootstrapping (Airbnb/early Uber precedent referenced). **Automation-first approach (DECIDED):** automated gates (photo-quality checks, bio-completeness checks, spam-template text detection — same checks as Section 4's bot pipeline) run first and reject/flag obvious cases automatically; humans only review what passes those automated gates, so early concierge reviewer time goes to genuinely borderline judgment calls rather than obvious spam.
- Use **higher exploration** in early delivery (~40% vs. ~15% steady-state) since early data collection matters more than early precision.
- Define an explicit **graduation threshold (DECIDED): 20+ swipes AND 3+ matches** to shift a user from cold-start scoring to blended, then full learned-model scoring — interpolated, not a hard switch. Chosen as the balanced default (vs. a faster 10-swipe/1-match option or slower 40-swipe/5-match option) to get enough real signal without leaving users in a long "rough" early experience.
- Cold start resets **per metro/hex region** independently at launch (region governs the admission-queue unit only — see Section 1), not just per-user globally. Candidate pools for matching itself are based on the user's **own location (`last_recorded_location`) + their self-selected slider radius (1–100km)**, not tied to the hex region at all — so cold-start maturity is scoped to a user's admission region for ratio purposes, but their actual candidate pool depends purely on their personal radius choice.

**Open decision needed:**
- Blend-confidence curve (how quickly weight shifts from cold-start heuristic to learned model between the graduation threshold and "fully learned" status) — not yet specified, only the graduation threshold itself is decided.
- ~~Whether manual/concierge curation is feasible given team size/budget~~ — **DECIDED: yes, founder handles this in-house at launch** (consistent with the in-house manual-review staffing decision in Section 4).
- Launch city sequencing strategy (single city deep launch vs. multi-city) — not discussed yet, but directly affects cold-start planning and the ratio-waitlist system's early viability (need critical mass in one place first).

---

## 6. Monetization — Three-Tier Admission Queue + Premium Subscription

**Core principle (decided):** all three admission tiers draw from the **same underlying ratio-based ceiling** (tied to active women count) — paid/auction tiers control *priority within* that ceiling, not additional total capacity beyond it. This preserves the core "equal playing field" promise while still allowing monetization of queue position. **Queue scoping note (updated):** the ceiling and all three tiers are now scoped per **metro/hex region** rather than per state (see Section 1); state is retained purely for GST invoicing (place-of-supply field), which is a backend bookkeeping detail with no bearing on queue membership — confirmed non-issue for the India-first launch since GST is a nationally uniform rate and payment aggregators are centrally RBI-regulated, not state-licensed.

**Three queues:**
1. **Free queue** — standard waitlist, FIFO/engagement-weighted admission, as originally designed. **Slot allocation (DECIDED): 60%** of daily admission slots.
2. **Paid queue** — **fixed price** (explicitly decided: no dynamic/surge pricing here), smaller allocation, faster movement than free. **Slot allocation (DECIDED): 25%** of daily admission slots. Exact price not yet set (see open items).
3. **Auction queue** — a genuine **live, ascending-bid auction** (eBay-style), for a fixed number of daily slots. Price is not fixed; it moves with live bidding. **Slot allocation (DECIDED): 15%** of daily admission slots. **Cadence (DECIDED): once daily, fixed window** (e.g., a set time each day where that day's auction opens and closes, and the batch of slots goes to the top bidders at close) — chosen over multiple-windows-per-day or continuous rolling for simplicity and to create a predictable, marketable daily event.

**Auction entrants — score parity (decided):** men entering via auction receive **no compatibility-score advantage** — same blended scoring treatment as free/paid entrants. This was explicitly reconsidered and confirmed: inflating scores for paid entrants would mean intentionally showing women lower-compatibility matches, spending down the platform's scarcest resource (women's trust/experience) to monetize the least scarce one (men's willingness to pay). Rejected for that reason.

**Premium/Pro subscription tier (decided — freemium, not eviction-based, two-tier bundle, available to both genders):**
- **Pro tier availability (DECIDED): open to both men and women**, not men-only — relevant since the entry-tier visibility feature below is now gated behind it for women specifically.
- An earlier idea (monthly subscription required to remain active, with non-payers evicted back to the waitlist) was **explicitly rejected** — it would punitively remove already-active users, contradicts the "equal playing field" positioning, and manufactures artificial churn in the very ratio system the app is trying to stabilize.
- Replaced with a standard **freemium model**: base access (15 matches/day) remains free forever for all active users, never revoked.
- **Bundle structure (DECIDED): two-tier Pro** — a "Basic Pro" and a higher "Pro Plus," rather than a single all-in-one bundle or fully à la carte pricing. Exact feature split between the two tiers and pricing not yet finalized (see open items), but the general shape:
  - *Basic Pro* (illustrative): increased daily match limit (e.g., 30/day), undo swipe, advanced filters.
  - *Pro Plus* (illustrative): everything in Basic Pro, plus "see who liked you," highest match limit (e.g., 40+/day), boosted visibility.
- **Boosted visibility** sits in the higher tier (Pro Plus, per above) — boosted profiles get increased visibility/placement in others' daily queues, but **must be explicitly labeled as "Boosted"** to anyone viewing the profile (decided, for transparency). This is separate from and does not touch the underlying compatibility score.

**Women paying to see a man's entry tier (free/paid/auction) — DECIDED, gated behind Pro plan:**
- **Mechanism (DECIDED):** women can view how a man entered the platform (free/paid/auction) only if *they* hold a Pro subscription — folded into the existing Pro tier (available to both genders, see above) rather than built as a separate standalone paywall.
- Previously flagged risk still applies and is worth monitoring post-launch: this introduces a money-signal into women's decision-making that could implicitly rank paid entrants as more "serious" or stigmatize free-queue men as second-class, undercutting the platform's core fairness positioning. Gating it behind Pro (an opt-in, paid feature affecting only the viewer's own experience) somewhat contains this compared to the earlier "always visible to any paying woman via a standalone fee" framing, but the underlying dynamic is unchanged.
- No longer a deferred "maybe later" test — it's now a defined Pro-tier feature, though still worth watching reception closely after launch given the flagged risk.

**Open decisions needed:**
- Exact fixed price for the paid queue.
- Exact clock time / duration of the daily auction window.
- Exact feature split between Basic Pro and Pro Plus, and pricing for each tier — including confirming whether entry-tier visibility sits in Basic Pro or Pro Plus specifically.
- Reception monitoring plan for the entry-tier visibility feature post-launch, given the flagged fairness-perception risk.

---

## 7. Data Retention Policy

**Decided defaults (subject to final legal review per jurisdiction — see Section 11):**

**Biometric data (face embeddings, liveness captures) — highest sensitivity:**
- Verification selfie/video (liveness check at signup): **soft-deleted for 30 days (DECIDED — matches general account grace period), then genuine hard-delete.** Kept briefly to support fraud disputes, not discarded outright, but not retained indefinitely — a "soft-deleted but kept in DB forever" approach was explicitly considered and rejected, since biometric-data laws (BIPA/GDPR/DPDP) generally require genuine, bounded-time erasure, not just hiding a record while retaining the underlying biometric data. If longer-term retention is ever wanted for fraud-pattern analysis, that needs its own separate stated purpose and consent language — not folded into "soft delete."
- Face embedding used for duplicate-detection: persists as long as the account exists (necessary to catch banned users re-signing up) — only the embedding vector is retained, never the source image.
- Embedding used for visual-pattern matching (Section 3): retained under the same justification/purpose as duplicate-detection rather than as a separate retained artifact, to keep purpose-limitation simple.
- Core principle: purpose limitation — biometric data collected for verification/matching cannot be repurposed (e.g., for marketing) without fresh, separate consent.
- On account deletion: biometric data (embeddings) deleted within the **30-day grace period** (see below), or faster if a specific jurisdiction mandates a shorter window.

**Profile data (bio, photos, prompts, preferences):**
- Retained for the life of the active account.
- On deletion: **soft-delete with a 30-day grace period** (DECIDED), allowing accidental-deletion recovery, then hard delete.

**Chat/messages:**
- Retained for the life of an active match.
- After unmatch: retained for a **90-day window** (DECIDED — agreed as proposed) specifically to support abuse/harassment investigations, then deleted.
- If a harassment report is filed, retention for that conversation is paused/extended for the duration of the investigation before the standard deletion timeline resumes.

**Location data:**
- Short rolling retention of current/last-known location only — no long-term location history log. Aligns with the `last_recorded_location` mechanism (Section 1, Section 2): captured fresh on each app open, not continuously tracked, so there's no background location trail to retain in the first place.

**Payment/transaction data:**
- Retention dictated by financial regulation (tax law, payment processor requirements, chargeback windows), not by the platform's general policy — typically 5–7 years depending on jurisdiction. Decoupled from account-deletion cascade; not shortened just because a user deletes their account.

**Device/behavioral signals (bot-detection: device fingerprint, IP, swipe timing):**
- **Rolling retention window: 90 days (DECIDED)**, refreshed continuously rather than accumulated indefinitely — chosen over 180 days since bot/fraud patterns are usually caught quickly if they're going to be caught at all, and a longer window would meaningfully expand retained device/IP data for limited additional detection value. Still personal data under GDPR/DPDP — needs a stated retention limit and lawful basis, not indefinite storage.

**Account deletion cascade (DECIDED shape):**
```
On account deletion request:
 → immediate: profile hidden, removed from matching pools and all queues
 → grace period (30 days, DECIDED): soft-deleted, recoverable
    — includes profile data AND verification selfies/liveness captures (soft-delete, 30 days, per above)
 → after grace period: hard delete profile data, photos, chat history (per chat-specific 90-day-post-unmatch rule where applicable), and verification selfies/liveness captures
 → biometric embeddings: hard deleted at end of grace period, or sooner if a specific jurisdiction requires it
 → payment records: retained separately per financial regulation, decoupled from this cascade
```

**Open decisions needed:**
- Confirm the 30-day grace period and biometric-deletion timelines against jurisdiction-specific legal minimums once the combined legal review (Section 11, item 1) is complete — 30 days is the working default, but some jurisdictions may mandate faster deletion; this is pending legal confirmation, not something resolved by product decision alone.

---

## 8. Full Feature List (as scoped so far)

Organized categories agreed on: Onboarding & Profile, Core Matching & Discovery, Gender-Ratio & Waitlist System, Messaging & Communication, Safety & Trust, Engagement & Retention, Monetization, Data/Feedback Loop (backend), Admin/Ops.

**MVP scope (DECIDED — confirmed, updated):**
- Onboarding & profile basics
- Core matching/discovery (hybrid algorithm, 15 matches/day)
- Full ratio/waitlist admission system, **including all three tiers at launch: free, paid, and live auction queues, plus the two-tier Pro subscription (Basic Pro / Pro Plus)** — this was upgraded from the original leaner proposal; founder confirmed the full monetization/admission system ships at MVP rather than being phased in later.
- Basic safety/verification (liveness detection, face-embedding duplicate check)
- Admin visibility dashboard
- **In-app chat — REVERSED, now included in MVP (DECIDED):** the earlier "no chat, match list only" decision is overturned. Chat is added specifically because it's a required data source, not just a UX nicety — message count and response latency per match feed directly into the `reciprocity_prediction` and `engagement_score` signals (Section 2), and the same activity data powers churn-risk flagging (Section 1) — identifying users likely to go inactive soon based on declining message frequency/response time, before they actually stop using the app. Resolves the previously flagged post-match dead-end risk (see below).
- **Push notifications — still deferred to v2**, this decision is unchanged; users discover new matches/messages by reopening the app for MVP.

**Explicitly deferred to v2+:**
- Push notifications
- Advanced engagement features (streaks, rewind, "who liked you" beyond what's in Pro Plus, etc. — from the original feature list)
- **"We Met" real-world feedback loop** (Section 2) — **unblocked, timing revised (DECIDED):** now that chat ships in MVP, the technical prerequisite for delivering this prompt exists from launch. Still practically gated by needing a mature matched-user base with real conversations to survey, so likely rolls out shortly after MVP launch rather than being fully built for day one — but no longer categorically "v2, blocked on chat," since chat is now in scope.
- **Item-level (prompt/photo-level) matching granularity**, inspired by Hinge's approach of tracking which specific prompt/photo triggered a like rather than treating the profile as one holistic bundle — natural v2 evolution of scoring granularity, pairs well with the "We Met" loop once both exist.

**Flagged consideration — RESOLVED by adding chat to MVP:** the earlier post-match dead-end risk (matched users having no way to connect during the MVP period) is resolved now that chat is in scope. The MVP now delivers a complete dating loop: match → chat → (eventually) real-world connection, rather than only proving the ratio/admission system.

---

## 9. Future Improvements (Post-Launch Refinements)

Items that are **decided and locked for launch as working defaults**, not open questions — but explicitly flagged as candidates for refinement once real usage data exists, rather than values expected to be correct or final long-term.

- **Manual review staffing** (Section 4): in-house (founder-handled) at launch; transition to a third-party moderation vendor once signup/flag volume exceeds what one person can reasonably review — exact volume trigger point not yet defined, revisit as real signup data comes in.
- **Anti-spam dwell-time/frequency thresholds** (Section 4): under-10-second profile view time, >70% of right-swipes, and 3-warnings-then-ban are locked as launch defaults. Revisit once real swipe-timing data exists to confirm these actually separate genuine low-intent/bot behavior from, e.g., users who are simply decisive or have slower devices/connections.
- **Duplicate-face similarity threshold** (Section 4): >90% locked as the working cutoff; worth validating against a proper false-match-rate analysis once real signup volume exists.
- **Exact scoring weights** in the matching formula (Section 2) beyond the now-fixed `visual_pattern_similarity`: tune once real swipe/match/chat data accumulates.
- **H3 hex resolution** (Section 1): resolution 6 is a pragmatic starting estimate; validate and correct against real 30-day-active data from the first city's soft launch.
- **Ratio tolerance/buffer percentages** (Section 1): current hysteresis band (1.05/0.95) can be tightened once real churn volatility data exists.

---

## 10. Technical Architecture Overview

A translation of the product decisions above into concrete services, data stores, and background jobs. This is an implementation blueprint derived from what's been decided — not new undiscussed product decisions — organized so an engineering team could start scoping work from it.

### Logical services

- **Identity & Verification Service** — onboarding, liveness-detection capture, FaceNet embedding generation (via DeepFace), duplicate-check against existing embeddings (>90% similarity → human review), profile-photo-to-selfie match. Owns the bot-risk composite score and the auto-approve/auto-reject/human-review routing (Section 4).
- **Admission & Queue Service** — per-H3-hex-region active men/women tracking, hysteresis-based admission control (1.05/0.95 band), the three-tier queue (free 60% / paid 25% / auction 15%), the daily live auction engine, and waitlist prioritization by engagement quality (Section 1).
- **Matching Service** — candidate-pool generation (filters by `last_recorded_location` + user's slider radius, 1–100km), cold-start heuristic scoring, blended scoring during graduation transition, full learned-model scoring (gradient-boosted trees for reciprocity, matrix factorization for collaborative filtering), and the daily 15-match delivery batch (Section 2, Section 5).
- **Chat Service** — messaging, per-match message count and response-latency tracking (feeds `engagement_score`, reciprocity training data, and the "We Met" trigger), churn-risk signal contribution (Section 1, Section 2, Section 8).
- **Anti-Abuse Service** — swipe dwell-time tracking, indiscriminate-swipe detection (<10s dwell, >70% of right-swipes), 3-warning escalation, and ban enforcement (Section 4). Distinct from the Identity & Verification Service's bot-risk routing — this is a separate warning/ban track for a specific behavior pattern.
- **Monetization Service** — Pro subscription management (Basic Pro / Pro Plus, available to both genders), entry-tier visibility gating for women, paid-queue fixed pricing, boosted-visibility labeling (Section 6).
- **Feedback & ML Pipeline** — "We Met" survey delivery (trigger: 20–30 messages over 3 days; re-ask every 1–2 weeks if unconfirmed) and periodic batch retraining (weekly/monthly) of the reciprocity and collaborative-filtering models using accumulated survey responses (Section 2).
- **Admin/Ops Dashboard** — live visibility into per-region ratio health, queue states, flagged-account review queue (in-house at launch, Section 4), and monetization metrics (Section 8's Admin/Ops feature category).

### Core data stores (MongoDB collections, illustrative)

| Collection | Holds | Retention tie-in |
|---|---|---|
| `users` | Profile, verification status, `last_recorded_location`, radius setting, active-status fields | Soft-delete 30 days → hard delete (Section 7) |
| `embeddings` | Face embedding vectors only (no source images) | Persists for account lifetime; hard-deleted with account (Section 7) |
| `verification_captures` | Liveness selfie/video | Soft-delete 30 days → hard delete (Section 7) |
| `swipes` | Swipe events: timestamp, dwell time, direction | Feeds anti-spam detection; rolling window per Section 4 |
| `matches` | Match records, status, formed_at, region | — |
| `messages` | Chat messages, per-match | 90-day post-unmatch retention, extended during harassment investigations (Section 7) |
| `queues` | Per-hex-region queue state: active counts, waitlist entries, auction bids | — |
| `subscriptions` | Pro tier status per user | — |
| `bot_risk_flags` | Composite risk scores, review queue state | — |
| `we_met_responses` | Survey responses | Ground-truth training data for batch retraining |
| `device_signals` | Device fingerprint, IP, behavioral signals | 90-day rolling window (Section 7) |

Embedding similarity search runs through **MongoDB Atlas Vector Search** directly against `embeddings` (Section 3) — no separate vector database.

### Background jobs

- **Daily match-generation batch** — computes and delivers each user's 15 matches (timing — all-at-once vs. trickled — still open, Section 2).
- **Daily auction close** — fixed daily window, admits top bidders at close (Section 6).
- **Ratio/hysteresis recompute** — triggered on active-count changes per hex region, governs admission freeze/resume (Section 1).
- **Churn-risk flagging job** — periodic scan of declining sessions/messages/response latency to flag at-risk women proactively (Section 1, Section 2).
- **Batch model retraining** — weekly/monthly, retrains reciprocity (gradient-boosted trees) and collaborative-filtering (matrix factorization) models, incorporating "We Met" labels (Section 2).
- **"We Met" prompt scheduler** — fires on the 20–30-message/3-day trigger, re-fires every 1–2 weeks if unconfirmed (Section 2).
- **Retention-cleanup jobs** — 30-day grace-period hard-deletes (profile, verification captures, embeddings), 90-day chat purge post-unmatch, 90-day device-signal rolling purge (Section 7).

### Tech stack summary

| Layer | Choice | Rationale (see relevant section) |
|---|---|---|
| Core database | MongoDB (+ Atlas Vector Search) | Already the core backend; avoids a separate vector DB (Section 3) |
| Face embeddings | FaceNet via DeepFace | Clean commercial licensing vs. InsightFace/ArcFace/VGGFace2 (Section 3) |
| Geospatial admission partitioning | H3, resolution 6 | Tiles all of India with no gaps, unlike CBSA/UA boundaries (Section 1) |
| Reciprocity model | Gradient-boosted trees (XGBoost/LightGBM) | Best complexity-to-value ratio pre-launch (Section 2) |
| Collaborative filtering | Matrix factorization (SVD/ALS) | Same rationale as above (Section 2) |
| Payments | RBI-regulated aggregator (not yet named) | GST nationally uniform, no state-level licensing complexity for India launch (Section 6) |

**Open item flowing from this section:** specific payment aggregator selection isn't yet named anywhere in this document — worth adding to the knowledge gaps list if it needs deciding before build starts.

---

## 11. Key Knowledge Gaps / Decisions Still Needed

This is the punch-list of things not yet decided that will block execution. (Fully resolved items — matching paradigm, sibling-similarity handling, monetization queue structure, subscription model, vendor/model selection, geographic partition scheme, post-match dead-end risk, entry-tier visibility, duplicate-face threshold, reciprocity/collaborative-filtering methods, blend-confidence curve, candidate-pool radius cap and slider UI, manual review staffing model, "We Met" trigger/re-ask/retraining design — have been removed from this list entirely; their decisions live in the relevant sections above, and locked-but-refinable defaults live in Section 9.)

1. **Legal review — combined single pending item (Section 3, Section 7):** no lawyer has been consulted yet on any of: biometric-processing consent language (even similarity-only embeddings), jurisdiction-specific requirements (BIPA/GDPR/DPDP), or confirming the 30-day data-retention grace period and biometric-deletion timelines against jurisdiction-specific legal minimums. All of this should happen as one legal-review engagement before any face-analysis code ships or public launch, not piecemeal.
2. **Monetization pricing figures** (Section 6) — exact fixed paid-queue price, exact daily auction window time/duration, exact feature split + pricing between Basic Pro and Pro Plus (including where entry-tier visibility sits), and a reception-monitoring plan for the entry-tier visibility feature post-launch.
3. **Payment aggregator selection (NEW, surfaced by Section 10)** — an RBI-regulated payment aggregator is required for the India launch (Section 6's monetization design assumes one exists), but no specific vendor has been named or evaluated yet.

---

*This document reflects decisions and open questions as of the current conversation. It is a working project reference, not a legal or technical specification — items flagged as "open decision needed" should be resolved (with legal counsel where noted) before implementation.*
