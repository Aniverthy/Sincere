import HexField from '../components/HexField.jsx'
import PhoneMockup from '../components/PhoneMockup.jsx'

export default function Hero() {
  return (
    <header className="hero" id="top">
      <div className="aurora" aria-hidden="true">
        <span className="aurora-blob aurora-a" />
        <span className="aurora-blob aurora-b" />
        <span className="aurora-blob aurora-c" />
      </div>
      <HexField />
      <div className="wrap hero-grid">
        <div className="hero-copy">
          <p className="hero-eyebrow">
            <span className="pulse-dot" /> Pre-launch · India-first
          </p>
          <h1>
            The dating app where the odds are <em>actually&nbsp;fair.</em>
          </h1>
          <p className="lede">
            One man for every woman — enforced, not promised. 15 curated matches a day instead of
            an endless feed. Paying moves you up the entry queue, but it never buys a better match.
          </p>
          <div className="hero-cta">
            <a className="btn btn-primary" href="#how">
              See how it works
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </a>
            <a className="btn btn-ghost" href="#fairness">
              See the fairness rules
            </a>
          </div>
          <div className="hero-proof">
            <div>
              <strong>1 : 1</strong>
              <span>active ratio, enforced per area</span>
            </div>
            <div>
              <strong>15 / day</strong>
              <span>curated matches, never infinite</span>
            </div>
            <div>
              <strong>100%</strong>
              <span>of profiles liveness-verified</span>
            </div>
          </div>
        </div>
        <PhoneMockup />
      </div>
      <a className="scroll-hint" href="#problem" aria-label="Scroll to content">
        <span />
      </a>
    </header>
  )
}
