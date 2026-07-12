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
        <p className="kicker">For the curious</p>
        <h2>Read the full documentation</h2>
        <p className="lede">
          Sincère is designed in the open inside this repository. The complete documentation suite
          lives alongside this page.
        </p>
        <div className="grid">
          {DOCS.map((d) => (
            <a key={d.file} className="card doc-card" href={`./${d.file}`}>
              <span className="doc-file">{d.file}</span>
              <h3>{d.title}</h3>
              <p>{d.blurb}</p>
            </a>
          ))}
        </div>
      </div>
    </section>
  )
}
