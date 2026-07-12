/**
 * Decorative drifting honeycomb — the H3 hex-region mechanic as a brand visual.
 * Pure CSS animation; hidden from screen readers; frozen under reduced motion.
 */
const HEXES = [
  { left: '4%', top: '18%', size: 90, dur: 26, delay: 0, o: 0.5 },
  { left: '12%', top: '64%', size: 56, dur: 32, delay: -8, o: 0.35 },
  { left: '22%', top: '30%', size: 38, dur: 22, delay: -4, o: 0.5 },
  { left: '78%', top: '12%', size: 70, dur: 28, delay: -12, o: 0.45 },
  { left: '86%', top: '52%', size: 110, dur: 36, delay: -6, o: 0.4 },
  { left: '68%', top: '74%', size: 48, dur: 24, delay: -16, o: 0.5 },
  { left: '54%', top: '8%', size: 34, dur: 20, delay: -2, o: 0.4 },
  { left: '38%', top: '82%', size: 64, dur: 30, delay: -10, o: 0.3 },
]

function Hex({ size }) {
  return (
    <svg viewBox="0 0 100 115" width={size} height={size * 1.15} fill="none">
      <path
        d="M50 3 95 29.5v56L50 112 5 85.5v-56L50 3Z"
        stroke="url(#hexg)"
        strokeWidth="2.5"
      />
      <defs>
        <linearGradient id="hexg" x1="0" y1="0" x2="100" y2="115" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ff5c7a" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
    </svg>
  )
}

export default function HexField() {
  return (
    <div className="hexfield" aria-hidden="true">
      {HEXES.map((h, i) => (
        <span
          key={i}
          className="hexfield-hex"
          style={{
            left: h.left,
            top: h.top,
            opacity: h.o,
            animationDuration: `${h.dur}s`,
            animationDelay: `${h.delay}s`,
          }}
        >
          <Hex size={h.size} />
        </span>
      ))}
    </div>
  )
}
