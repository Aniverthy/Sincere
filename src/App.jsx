import Hero from './sections/Hero.jsx'
import Problem from './sections/Problem.jsx'
import HowItWorks from './sections/HowItWorks.jsx'
import Features from './sections/Features.jsx'
import Fairness from './sections/Fairness.jsx'
import Roadmap from './sections/Roadmap.jsx'
import Docs from './sections/Docs.jsx'

export default function App() {
  return (
    <>
      <Hero />
      <main>
        <Problem />
        <HowItWorks />
        <Features />
        <Fairness />
        <Roadmap />
        <Docs />
      </main>
      <footer className="footer">
        <p>
          <strong>Sincère</strong> — the dating app where the odds are actually fair.
        </p>
        <p className="footer-note">
          Pre-launch. India-first. This page describes the product as designed; details marked
          “planned” are subject to the project’s open decisions.
        </p>
      </footer>
    </>
  )
}
