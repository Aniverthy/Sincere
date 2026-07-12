export default function HowItWorks() {
  return (
    <section id="how" className="tint">
      <div className="wrap">
        <p className="kicker">How it works</p>
        <h2>Fairness as a mechanism, not a slogan.</h2>
        <div className="steps">
          <div className="step">
            <div className="step-num">1</div>
            <div>
              <h3>The map is a honeycomb</h3>
              <p>
                The country is divided into equal hexagons (about 36 km² each, using Uber’s
                open-source H3 grid). Every hexagon runs its own independent gender-ratio count and
                admission queue — so a balanced average can never hide a skewed city.
              </p>
            </div>
          </div>
          <div className="step">
            <div className="step-num">2</div>
            <div>
              <h3>A thermostat keeps the ratio at 1:1</h3>
              <p>
                The ratio counts <em>active</em> users only — logged in within 30 days and actually
                swiping. New men are admitted while there’s room; when active men reach 105% of
                active women, admissions pause, resuming once the balance recovers. Nobody already
                inside is ever removed — only new entry waits.
              </p>
            </div>
          </div>
          <div className="step">
            <div className="step-num">3</div>
            <div>
              <h3>Men enter through a transparent queue</h3>
              <p>
                Three lanes into each area: a free waitlist (60% of daily openings, where genuine
                engagement moves you up), a fixed-price fast lane (25% — no surge pricing, ever),
                and a once-daily live auction (15%) where the day’s top bidders take the remaining
                spots.
              </p>
            </div>
          </div>
          <div className="step">
            <div className="step-num">4</div>
            <div>
              <h3>Everyone gets 15 real options a day</h3>
              <p>
                No infinite swipe. A ranked, curated set of 15 profiles daily, drawn from a radius
                you choose yourself (1–100 km). The matching engine learns what you like, predicts
                who will like you <em>back</em>, and mixes in deliberate variety so the same
                profiles don’t monopolize everyone’s day.
              </p>
            </div>
          </div>
          <div className="step">
            <div className="step-num">5</div>
            <div>
              <h3>It learns from real dates, not just swipes</h3>
              <p>
                After a genuinely substantial conversation, the app privately asks both people
                whether they met in person and whether it was good. Those answers retrain the
                matching models on real-world outcomes — the thing every swipe-metric app only
                guesses at. (Rolls out shortly after launch.)
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
