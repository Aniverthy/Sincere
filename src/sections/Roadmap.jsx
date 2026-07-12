import Reveal from '../components/Reveal.jsx'

const PHASES = [
  {
    phase: 'Launch (MVP)',
    title: 'One city, done properly',
    body: 'Full ratio and queue system, 15-a-day matching, liveness verification, in-app chat, all three entry lanes, and Pro plans — launched deep in a single Indian city first, because the ratio system needs critical mass in one place before it needs breadth.',
  },
  {
    phase: 'Shortly after',
    title: 'The “We Met” loop goes live',
    body: 'Once enough real conversations exist, the did-you-actually-meet feedback loop starts retraining the matching models on real-world outcomes.',
  },
  {
    phase: 'v2',
    title: 'Push notifications & richer matching',
    body: 'Push notifications arrive (at launch, the daily 15 is a reason to open the app, not another ping). Matching gets more granular — learning which specific prompt or photo earned a like, not just the profile as a whole.',
  },
  {
    phase: 'Scale',
    title: 'City by city',
    body: 'Each new city launches as its own fresh, balanced region — the honeycomb design means growth adds cities side by side without destabilizing the ones already working.',
  },
]

export default function Roadmap() {
  return (
    <section id="roadmap">
      <div className="wrap">
        <Reveal>
          <p className="kicker">Where this is going</p>
          <h2>
            The <span className="grad-text">roadmap</span>
          </h2>
        </Reveal>
        <div className="timeline">
          {PHASES.map((p, i) => (
            <Reveal className="tl-item" key={p.phase} delay={i * 110}>
              <div className="tl-marker">
                <span className="tl-dot" />
                {i < PHASES.length - 1 && <span className="tl-line" />}
              </div>
              <div className="tl-body">
                <div className="tl-phase">{p.phase}</div>
                <h3>{p.title}</h3>
                <p>{p.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
