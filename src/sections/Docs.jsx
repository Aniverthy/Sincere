import Reveal from '../components/Reveal.jsx'

const DOCS = [
  {
    file: 'README.md',
    title: 'Project README',
    blurb: 'Executive summary, product overview, tech stack, setup, and high-level architecture.',
  },
  {
    file: 'APPLICATION_WORKING.md',
    title: 'How Sincère Works',
    blurb:
      'The whole system end to end in plain English — every formula and model explained before the math.',
  },
  {
    file: 'TECHNICAL_IMPLEMENTATION_PLAN.md',
    title: 'Technical Implementation Plan',
    blurb: 'Requirements, APIs, database schema, ML models, security, testing, and rollout.',
  },
  {
    file: 'ARCHITECTURE_PLAN.md',
    title: 'Architecture Plan',
    blurb:
      'Modular monolith today, microservices when needed — boundaries, diagrams, and the migration path.',
  },
  {
    file: 'MARKETING_PLAN.md',
    title: 'Marketing Plan',
    blurb: 'Positioning, personas, market sizing, go-to-market, growth loops, KPIs, and revenue.',
  },
]

export default function Docs() {
  return (
    <section id="docs" className="tint">
      <div className="wrap">
        <Reveal>
          <h2>Documentation</h2>
          <p className="lede">
            The complete documentation suite lives alongside this page — product, engineering,
            architecture, and go-to-market.
          </p>
        </Reveal>
        <div className="grid">
          {DOCS.map((d, i) => (
            <Reveal key={d.file} delay={(i % 3) * 90}>
              <a className="card doc-card" href={`./${d.file}`}>
                <span className="doc-file">{d.file}</span>
                <h3>{d.title}</h3>
                <p>{d.blurb}</p>
                <span className="doc-arrow" aria-hidden="true">
                  →
                </span>
              </a>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
