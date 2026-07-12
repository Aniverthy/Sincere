const ITEMS = [
  '1 : 1 active ratio — enforced',
  '15 curated matches a day',
  'Every profile liveness-verified',
  'No infinite swipe',
  'No beauty scores, ever',
  'No background location tracking',
  'Paying never buys a better match',
  'India-first',
]

export default function Marquee() {
  const row = ITEMS.map((t, i) => (
    <span className="marquee-item" key={i}>
      {t} <span className="marquee-dot">◆</span>
    </span>
  ))
  return (
    <div className="marquee" aria-hidden="true">
      <div className="marquee-track">
        {row}
        {row}
      </div>
    </div>
  )
}
