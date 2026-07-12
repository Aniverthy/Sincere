import Reveal from '../components/Reveal.jsx'

export default function Problem() {
  return (
    <section id="problem">
      <div className="wrap">
        <Reveal>
          <p className="kicker">The problem</p>
          <h2>
            Dating apps are built on a <span className="grad-text">broken ratio.</span>
          </h2>
          <p className="lede">
            Typical dating apps run at roughly 70% men and 30% women — and everything bad about
            them flows from that one number. Women drown in low-effort attention and leave. As they
            leave, the skew worsens, so more women leave: a death spiral. Men shout into the void,
            then pay for boosts that can’t fix the underlying scarcity.
          </p>
        </Reveal>

        <Reveal className="ratio-compare" delay={120}>
          <div className="ratio-row">
            <span className="ratio-label">Every other app</span>
            <div className="ratio-bar">
              <span className="ratio-fill ratio-fill--them" style={{ '--w': '70%' }}>
                70% men
              </span>
              <span className="ratio-rest">30% women</span>
            </div>
          </div>
          <div className="ratio-row">
            <span className="ratio-label ratio-label--us">Sincère</span>
            <div className="ratio-bar">
              <span className="ratio-fill ratio-fill--us" style={{ '--w': '50%' }}>
                50% men
              </span>
              <span className="ratio-rest ratio-rest--us">50% women</span>
            </div>
          </div>
          <p className="ratio-caption">Active users per area — enforced by admission control, not hoped for.</p>
        </Reveal>

        <div className="stat-row">
          {[
            ['~70 / 30', 'Typical men-to-women split on major dating apps'],
            ['Firehose', 'What the experience becomes for women — volume, not quality'],
            ['Void', 'What it becomes for men — near-zero results, paid or not'],
            ['Spiral', 'Women churn → skew worsens → more women churn'],
          ].map(([v, l], i) => (
            <Reveal className="stat" key={v} delay={i * 90}>
              <div className="stat-value">{v}</div>
              <div className="stat-label">{l}</div>
            </Reveal>
          ))}
        </div>

        <Reveal className="principle" delay={100}>
          <strong>Incumbents can’t fix this.</strong>
          <p>
            Their revenue is built on the imbalance — boosts and super-likes are painkillers sold
            for a disease the business model needs. Sincère removes the imbalance instead.
          </p>
        </Reveal>
      </div>
    </section>
  )
}
