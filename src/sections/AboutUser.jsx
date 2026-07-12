import Reveal from '../components/Reveal.jsx'

export default function AboutUser() {
  return (
    <section id="about-user" className="tint">
      <div className="wrap">
        <Reveal>
          <p className="kicker">About the User Experience</p>
          <h2>
            Designed for two sides of <span className="grad-text">the same connection</span>
          </h2>
          <p className="lede">
            Sincère isn't just another dating app with a different coat of paint. We've rebuilt the 
            onboarding and matchmaking dynamics for both men and women to solve the structural ratio problems.
          </p>
        </Reveal>

        <div className="user-journey-grid">
          {/* For Women */}
          <Reveal className="user-card female-card" delay={100}>
            <div className="user-card-header">
              <div className="user-badge female-badge">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 2a5 5 0 1 0 0 10 5 5 0 0 0 0-10Z" />
                  <path d="M12 12v9" />
                  <path d="M9 17h6" />
                </svg>
                <span>For Women</span>
              </div>
              <h3>Curated, Safe & Focused</h3>
            </div>
            
            <ul className="user-list">
              <li>
                <strong>Instant Admission:</strong>
                <span>Women are never waitlisted. The ratio ceiling controls male admission to protect your inbox from being overwhelmed.</span>
              </li>
              <li>
                <strong>Zero Catfishing:</strong>
                <span>Every match is 100% verified using randomized liveness video prompts (blink, turn head) and face-matching duplicates checks.</span>
              </li>
              <li>
                <strong>Absolute Privacy:</strong>
                <span>Your coordinates are captured only when you open the app and immediately overwrite the previous location. No tracking history.</span>
              </li>
              <li>
                <strong>Real Conversations:</strong>
                <span>No passive matching. In-app chat measures responsiveness so quiet, stagnant accounts are automatically deprioritized.</span>
              </li>
            </ul>
          </Reveal>

          {/* For Men */}
          <Reveal className="user-card male-card" delay={200}>
            <div className="user-card-header">
              <div className="user-badge male-badge">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="10" cy="14" r="5" />
                  <path d="m19 5-5.4 5.4" />
                  <path d="M14 5h5v5" />
                </svg>
                <span>For Men</span>
              </div>
              <h3>Transparent & High-Intent</h3>
            </div>

            <ul className="user-list">
              <li>
                <strong>Ratio-Enforced Entry:</strong>
                <span>Men enter based on local active ratios (H3 hex cells). Once inside, your profile actually gets seen instead of buried under thousands.</span>
              </li>
              <li>
                <strong>Three Admission Lanes:</strong>
                <span>Choose how you enter: a free waitlist (60% of slots), a fixed-price priority lane (25%), or the daily live auction (15%).</span>
              </li>
              <li>
                <strong>100% Score Parity:</strong>
                <span>An ironclad rule — paying only controls waitlist priority, never match quality. We never boost scores for money.</span>
              </li>
              <li>
                <strong>Intentional Swiping:</strong>
                <span>The platform penalizes rapid, low-intent right-swipes with warnings and bans. You are shown matches who are verified and interested.</span>
              </li>
            </ul>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
