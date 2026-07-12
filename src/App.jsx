import Nav from './components/Nav.jsx'
import Marquee from './components/Marquee.jsx'
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
      <Nav />
      <Hero />
      <Marquee />
      <main>
        <Problem />
        <HowItWorks />
        <Features />
        <Fairness />
        <Roadmap />
        <Docs />
      </main>
      <footer className="footer">
        <div className="wrap footer-inner">
          <div className="footer-brand">
            <span className="nav-heart" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M12 21s-7.5-4.9-10-9.2C.3 8.7 2 5 5.5 5c2 0 3.4 1.1 4.2 2.4l2.3 3.4 2.3-3.4C15.1 6.1 16.5 5 18.5 5 22 5 23.7 8.7 22 11.8 19.5 16.1 12 21 12 21z" />
              </svg>
            </span>
            <strong>Sincère</strong> — the dating app where the odds are actually fair.
          </div>
          <p className="footer-note">
            Pre-launch · India-first. This page describes the product as designed; details marked
            “planned” are subject to the project’s open decisions.
          </p>
        </div>
      </footer>
    </>
  )
}
