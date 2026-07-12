import { useEffect, useState } from 'react'

const LINKS = [
  ['#problem', 'The problem'],
  ['#how', 'How it works'],
  ['#features', 'Trust'],
  ['#fairness', 'Fairness'],
  ['#roadmap', 'Roadmap'],
]

export default function Nav() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <nav className={`nav ${scrolled ? 'nav--scrolled' : ''}`}>
      <div className="nav-inner">
        <a href="#top" className="nav-brand">
          <span className="nav-heart" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M12 21s-7.5-4.9-10-9.2C.3 8.7 2 5 5.5 5c2 0 3.4 1.1 4.2 2.4l2.3 3.4 2.3-3.4C15.1 6.1 16.5 5 18.5 5 22 5 23.7 8.7 22 11.8 19.5 16.1 12 21 12 21z" />
            </svg>
          </span>
          Sincère
        </a>
        <div className={`nav-links ${open ? 'nav-links--open' : ''}`}>
          {LINKS.map(([href, label]) => (
            <a key={href} href={href} onClick={() => setOpen(false)}>
              {label}
            </a>
          ))}
          <a href="#docs" className="btn btn-small" onClick={() => setOpen(false)}>
            Read the docs
          </a>
        </div>
        <button
          className="nav-burger"
          aria-label="Toggle menu"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <span />
          <span />
          <span />
        </button>
      </div>
    </nav>
  )
}
