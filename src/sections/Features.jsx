import Reveal from '../components/Reveal.jsx'

const FEATURES = [
  {
    tag: 'Verification',
    title: 'Every profile is a live human',
    body: 'Signup requires a short selfie video with randomized instructions — blink, turn your head — which defeats stolen photos and pre-made deepfakes. Face matching also catches one person running multiple accounts, and confirms profile photos are actually of the verified person.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 6 9 17l-5-5" />
      </svg>
    ),
  },
  {
    tag: 'Privacy',
    title: 'No location trail — ever',
    body: 'The app records your location once, when you open it, and overwrites the previous value. There is no background tracking and no movement history to leak, because it was never recorded in the first place.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 21s-6-5.1-6-10a6 6 0 1 1 12 0c0 4.9-6 10-6 10Z" />
        <circle cx="12" cy="11" r="2.2" />
      </svg>
    ),
  },
  {
    tag: 'Privacy',
    title: 'No beauty scores',
    body: 'Sincère never rates anyone’s appearance — no visible score, no hidden one, no ranked facial features. Face data is used only for verification and a small personal “resembles what you’ve liked” signal that’s different for every viewer.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3l18 18M10.6 10.6a3 3 0 0 0 4.2 4.2" />
        <path d="M9 5.2A9.8 9.8 0 0 1 12 5c6 0 9.5 6.2 9.5 6.2a17 17 0 0 1-3 3.7M5.6 7.5A16.5 16.5 0 0 0 2.5 11.2s3.5 6.2 9.5 6.2c1 0 2-.2 2.9-.5" />
      </svg>
    ),
  },
  {
    tag: 'Conduct',
    title: 'Low-intent swiping has consequences',
    body: 'Rapid-fire, indiscriminate right-swiping earns warnings, and repeat offenders are banned. Being decisive is fine; treating people as a slot machine isn’t.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 9v4M12 17h.01" />
        <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      </svg>
    ),
  },
  {
    tag: 'Messaging',
    title: 'Real conversations, in-app',
    body: 'Chat with your matches from day one. If a match goes quiet on you, the algorithm notices — responsiveness is part of how future matches are ranked.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 12a8 8 0 0 1-8 8H4l2.5-2.9A8 8 0 1 1 21 12Z" />
      </svg>
    ),
  },
  {
    tag: 'Safety',
    title: 'Reports are taken seriously',
    body: 'Harassment reports freeze the conversation’s normal deletion schedule so evidence survives the investigation. Deleted accounts get a 30-day recovery window, then data is genuinely erased.',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10Z" />
      </svg>
    ),
  },
]

export default function Features() {
  return (
    <section id="features">
      <div className="wrap">
        <Reveal>
          <p className="kicker">Built in, not bolted on</p>
          <h2>
            Trust and privacy are <span className="grad-text">architecture</span>, not policy.
          </h2>
        </Reveal>
        <div className="grid">
          {FEATURES.map((f, i) => (
            <Reveal className="card feature-card" key={f.title} delay={(i % 3) * 90}>
              <div className="feature-head">
                <span className="feature-icon">{f.icon}</span>
                <span className="tag">{f.tag}</span>
              </div>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
