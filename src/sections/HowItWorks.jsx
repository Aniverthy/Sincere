import Reveal from '../components/Reveal.jsx'

const STEPS = [
  {
    title: 'The map is a honeycomb',
    body: 'The country is divided into equal hexagons (about 36 km² each, using Uber’s open-source H3 grid). Every hexagon runs its own independent gender-ratio count and admission queue — so a balanced average can never hide a skewed city.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
        <path d="M12 2.5 20 7v10l-8 4.5L4 17V7l8-4.5Z" />
      </svg>
    ),
  },
  {
    title: 'A thermostat keeps the ratio at 1:1',
    body: 'The ratio counts active users only — logged in within 30 days and actually swiping. New men are admitted while there’s room; when active men reach 105% of active women, admissions pause, resuming once the balance recovers. Nobody already inside is ever removed — only new entry waits.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M12 3v10.5M12 21a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
        <path d="M8.5 6.5 12 3l3.5 3.5" />
      </svg>
    ),
  },
  {
    title: 'Men enter through a transparent queue',
    body: 'Three lanes into each area: a free waitlist (60% of daily openings, where genuine engagement moves you up), a fixed-price fast lane (25% — no surge pricing, ever), and a once-daily live auction (15%) where the day’s top bidders take the remaining spots.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M4 6h16M4 12h10M4 18h6" />
      </svg>
    ),
  },
  {
    title: 'Everyone gets 15 real options a day',
    body: 'No infinite swipe. A ranked, curated set of 15 profiles daily, drawn from a radius you choose yourself (1–100 km). The matching engine learns what you like, predicts who will like you back, and mixes in deliberate variety so the same profiles don’t monopolize everyone’s day.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="12" height="16" rx="2" />
        <path d="M18 6h3v14a2 2 0 0 1-2 2h-9" />
      </svg>
    ),
  },
  {
    title: 'It learns from real dates, not just swipes',
    body: 'After a genuinely substantial conversation, the app privately asks both people whether they met in person and whether it was good. Those answers retrain the matching models on real-world outcomes — the thing every swipe-metric app only guesses at. (Rolls out shortly after launch.)',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12a9 9 0 1 1-3-6.7" />
        <path d="M21 3v6h-6" />
      </svg>
    ),
  },
]

export default function HowItWorks() {
  return (
    <section id="how" className="tint">
      <div className="wrap">
        <Reveal>
          <p className="kicker">How it works</p>
          <h2>
            Fairness as a <span className="grad-text">mechanism</span>, not a slogan.
          </h2>
        </Reveal>
        <div className="steps">
          {STEPS.map((s, i) => (
            <Reveal className="step" key={s.title} delay={i * 90}>
              <div className="step-badge">
                <span className="step-num">{String(i + 1).padStart(2, '0')}</span>
                <span className="step-icon">{s.icon}</span>
              </div>
              <div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
