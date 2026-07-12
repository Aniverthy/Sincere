import Nav from './components/Nav.jsx'
import Marquee from './components/Marquee.jsx'
import Hero from './sections/Hero.jsx'
import Problem from './sections/Problem.jsx'
import HowItWorks from './sections/HowItWorks.jsx'
import Features from './sections/Features.jsx'
import Fairness from './sections/Fairness.jsx'
import Roadmap from './sections/Roadmap.jsx'
import AboutUser from './sections/AboutUser.jsx'

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
        <AboutUser />
      </main>
      <footer className="footer">
        <div className="wrap footer-grid">
          <div className="footer-col footer-col--brand">
            <div className="footer-brand">
              <span className="nav-heart" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M12 21s-7.5-4.9-10-9.2C.3 8.7 2 5 5.5 5c2 0 3.4 1.1 4.2 2.4l2.3 3.4 2.3-3.4C15.1 6.1 16.5 5 18.5 5 22 5 23.7 8.7 22 11.8 19.5 16.1 12 21 12 21z" />
                </svg>
              </span>
              <strong>Sincère</strong>
            </div>
            <p className="footer-desc">
              The dating app where the odds are actually fair. A 1:1 active gender ratio, enforced locally.
            </p>
          </div>

          <div className="footer-col">
            <h4>Product</h4>
            <ul className="footer-links">
              <li><a href="#problem">The Problem</a></li>
              <li><a href="#how">How It Works</a></li>
              <li><a href="#features">Trust & Safety</a></li>
              <li><a href="#fairness">Honest Monetization</a></li>
              <li><a href="#roadmap">Development Roadmap</a></li>
              <li><a href="#about-user">User Journey</a></li>
            </ul>
          </div>

          <div className="footer-col">
            <h4>Technology</h4>
            <ul className="footer-links">
              <li><span className="footer-info-item">H3 Hexagonal Partitioning</span></li>
              <li><span className="footer-info-item">Liveness verification (FaceNet)</span></li>
              <li><span className="footer-info-item">Responsiveness Reciprocity Model</span></li>
              <li><span className="footer-info-item">100% Score Parity Enforced</span></li>
            </ul>
          </div>
        </div>

        <div className="wrap footer-bottom">
          <p className="footer-note">
            Pre-launch · India-first. This page describes the product as designed; details marked
            “planned” are subject to the project’s open decisions.
          </p>
          <p className="footer-copy">&copy; {new Date().getFullYear()} Sincère. All rights reserved.</p>
        </div>
      </footer>
    </>
  )
}
