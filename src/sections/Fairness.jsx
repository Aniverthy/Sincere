export default function Fairness() {
  return (
    <section id="fairness" className="tint">
      <div className="wrap">
        <p className="kicker">Honest monetization</p>
        <h2>Money buys the front of the line. Never a better match.</h2>
        <p className="lede">
          All paid entry draws from the same ratio-based ceiling — paying controls <em>priority</em>,
          never extra capacity that would break the 1:1 promise.
        </p>
        <table className="queue-table">
          <thead>
            <tr>
              <th>Lane</th>
              <th>Share of daily openings</th>
              <th>How it works</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Free queue</td>
              <td className="queue-share">60%</td>
              <td>Standard waitlist — genuine engagement moves you up, not just time served.</td>
            </tr>
            <tr>
              <td>Paid queue</td>
              <td className="queue-share">25%</td>
              <td>One fixed price for a faster lane. No dynamic pricing, no surge — decided.</td>
            </tr>
            <tr>
              <td>Daily auction</td>
              <td className="queue-share">15%</td>
              <td>A once-daily live bidding window; top bidders at close take that day’s spots.</td>
            </tr>
          </tbody>
        </table>
        <div className="principle">
          <strong>Score parity is a hard rule.</strong>
          <p>
            However a man entered — free, paid, or auction — his match scoring is identical.
            Inflating paid users’ scores would mean deliberately showing women worse matches to
            monetize men’s impatience. That was considered, and rejected.
          </p>
        </div>
        <div className="principle">
          <strong>The free tier is free forever.</strong>
          <p>
            15 matches a day costs nothing and is never revoked. Optional Pro plans (for everyone,
            not just men) add more daily matches, filters, and visibility — and any boosted profile
            is clearly labeled “Boosted” to the people who see it.
          </p>
        </div>
      </div>
    </section>
  )
}
