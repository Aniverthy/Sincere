/**
 * Stylized app preview: today's 15, a card stack with a looping like animation,
 * and a live-feeling ratio pill. Illustrative UI only — no real user data.
 */
const CARDS = [
  { name: 'Ananya, 27', meta: '4 km away · verified', grad: 'g1' },
  { name: 'Rahul, 29', meta: '7 km away · verified', grad: 'g2' },
  { name: 'Ishita, 26', meta: '2 km away · verified', grad: 'g3' },
]

export default function PhoneMockup() {
  return (
    <div className="phone-wrap" aria-hidden="true">
      <div className="phone-glow" />
      <div className="phone">
        <div className="phone-notch" />
        <div className="phone-screen">
          <div className="phone-top">
            <span className="phone-logo">Sincère</span>
            <span className="ratio-pill">
              <span className="ratio-dot" /> 1.00 : 1 in your area
            </span>
          </div>
          <div className="phone-title">
            Today’s 15 <span className="phone-count">3 / 15</span>
          </div>
          <div className="card-stack">
            {CARDS.map((c, i) => (
              <div key={c.name} className={`match-card match-card--${i} ${c.grad}`}>
                <div className="match-photo">
                  <span className="match-verified">
                    <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor">
                      <path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z" />
                    </svg>
                    Verified
                  </span>
                </div>
                <div className="match-info">
                  <strong>{c.name}</strong>
                  <span>{c.meta}</span>
                </div>
              </div>
            ))}
            <div className="like-burst">
              <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor">
                <path d="M12 21s-7.5-4.9-10-9.2C.3 8.7 2 5 5.5 5c2 0 3.4 1.1 4.2 2.4l2.3 3.4 2.3-3.4C15.1 6.1 16.5 5 18.5 5 22 5 23.7 8.7 22 11.8 19.5 16.1 12 21 12 21z" />
              </svg>
            </div>
          </div>
          <div className="phone-actions">
            <span className="action action--pass">✕</span>
            <span className="action action--like">♥</span>
          </div>
        </div>
      </div>
    </div>
  )
}
