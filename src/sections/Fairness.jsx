import Reveal from '../components/Reveal.jsx'

const LANES = [
  {
    name: 'Free queue',
    share: 60,
    blurb: 'Standard waitlist — genuine engagement moves you up, not just time served.',
    note: 'Always available',
  },
  {
    name: 'Paid queue',
    share: 25,
    blurb: 'One fixed price for a faster lane. No dynamic pricing, no surge — decided.',
    note: 'Fixed price',
  },
  {
    name: 'Daily auction',
    share: 15,
    blurb: 'A once-daily live bidding window; top bidders at close take that day’s spots.',
    note: 'Once a day',
  },
]

export default function Fairness() {
  return (
    <section id="fairness" className="tint">
      <div className="wrap">
        <Reveal>
          <p className="kicker">Honest monetization</p>
          <h2>
            Money buys the front of the line. <span className="grad-text">Never a better match.</span>
          </h2>
          <p className="lede">
            All paid entry draws from the same ratio-based ceiling — paying controls{' '}
            <em>priority</em>, never extra capacity that would break the 1:1 promise.
          </p>
        </Reveal>

        <div className="lanes">
          {LANES.map((l, i) => (
            <Reveal className="lane-card" key={l.name} delay={i * 100}>
              <div className="lane-top">
                <span className="lane-note">{l.note}</span>
                <span className="lane-share">{l.share}%</span>
              </div>
              <div className="lane-meter">
                <span style={{ '--w': `${l.share}%` }} />
              </div>
              <h3>{l.name}</h3>
              <p>{l.blurb}</p>
            </Reveal>
          ))}
        </div>

        <div className="principles-grid">
          <Reveal className="principle" delay={60}>
            <strong>Score parity is a hard rule.</strong>
            <p>
              However a man entered — free, paid, or auction — his match scoring is identical.
              Inflating paid users’ scores would mean deliberately showing women worse matches to
              monetize men’s impatience. That was considered, and rejected.
            </p>
          </Reveal>
          <Reveal className="principle" delay={160}>
            <strong>The free tier is free forever.</strong>
            <p>
              15 matches a day costs nothing and is never revoked. Optional Pro plans (for
              everyone, not just men) add more daily matches, filters, and visibility — and any
              boosted profile is clearly labeled “Boosted” to the people who see it.
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
