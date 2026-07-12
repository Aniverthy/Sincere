export default function Problem() {
  return (
    <section id="problem">
      <div className="wrap">
        <p className="kicker">The problem</p>
        <h2>Dating apps are built on a broken ratio.</h2>
        <p className="lede">
          Typical dating apps run at roughly 70% men and 30% women — and everything bad about them
          flows from that one number. Women drown in low-effort attention and leave. As they leave,
          the skew worsens, so more women leave: a death spiral. Men shout into the void, then pay
          for boosts that can’t fix the underlying scarcity. And a healthy-looking national average
          can hide a badly skewed city underneath it.
        </p>
        <div className="stat-row">
          <div className="stat">
            <div className="stat-value">~70 / 30</div>
            <div className="stat-label">Typical men-to-women split on major dating apps</div>
          </div>
          <div className="stat">
            <div className="stat-value">Firehose</div>
            <div className="stat-label">What the experience becomes for women — volume, not quality</div>
          </div>
          <div className="stat">
            <div className="stat-value">Void</div>
            <div className="stat-label">What it becomes for men — near-zero results, paid or not</div>
          </div>
          <div className="stat">
            <div className="stat-value">Spiral</div>
            <div className="stat-label">Women churn → skew worsens → more women churn</div>
          </div>
        </div>
        <div className="principle">
          <strong>Incumbents can’t fix this.</strong>
          <p>
            Their revenue is built on the imbalance — boosts and super-likes are painkillers sold
            for a disease the business model needs. Sincère removes the imbalance instead.
          </p>
        </div>
      </div>
    </section>
  )
}
