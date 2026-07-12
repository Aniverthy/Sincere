export default function Features() {
  return (
    <section id="features">
      <div className="wrap">
        <p className="kicker">Built in, not bolted on</p>
        <h2>Trust and privacy are architecture, not policy.</h2>
        <div className="grid">
          <div className="card">
            <span className="tag">Verification</span>
            <h3>Every profile is a live human</h3>
            <p>
              Signup requires a short selfie video with randomized instructions — blink, turn your
              head — which defeats stolen photos and pre-made deepfakes. Face matching also catches
              one person running multiple accounts, and confirms profile photos are actually of the
              verified person.
            </p>
          </div>
          <div className="card">
            <span className="tag">Privacy</span>
            <h3>No location trail — ever</h3>
            <p>
              The app records your location once, when you open it, and overwrites the previous
              value. There is no background tracking and no movement history to leak, because it
              was never recorded in the first place.
            </p>
          </div>
          <div className="card">
            <span className="tag">Privacy</span>
            <h3>No beauty scores</h3>
            <p>
              Sincère never rates anyone’s appearance — no visible score, no hidden one, no ranked
              facial features. Face data is used only for verification and a small personal
              “resembles what you’ve liked” signal that’s different for every viewer.
            </p>
          </div>
          <div className="card">
            <span className="tag">Conduct</span>
            <h3>Low-intent swiping has consequences</h3>
            <p>
              Rapid-fire, indiscriminate right-swiping earns warnings, and repeat offenders are
              banned. Being decisive is fine; treating people as a slot machine isn’t.
            </p>
          </div>
          <div className="card">
            <span className="tag">Messaging</span>
            <h3>Real conversations, in-app</h3>
            <p>
              Chat with your matches from day one. If a match goes quiet on you, the algorithm
              notices — responsiveness is part of how future matches are ranked.
            </p>
          </div>
          <div className="card">
            <span className="tag">Safety</span>
            <h3>Reports are taken seriously</h3>
            <p>
              Harassment reports freeze the conversation’s normal deletion schedule so evidence
              survives the investigation. Deleted accounts get a 30-day recovery window, then data
              is genuinely erased.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
