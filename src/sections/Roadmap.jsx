export default function Roadmap() {
  return (
    <section id="roadmap">
      <div className="wrap">
        <p className="kicker">Where this is going</p>
        <h2>Roadmap</h2>
        <div className="timeline">
          <div className="tl-item">
            <div className="tl-phase">Launch (MVP)</div>
            <div>
              <h3>One city, done properly</h3>
              <p>
                Full ratio and queue system, 15-a-day matching, liveness verification, in-app chat,
                all three entry lanes, and Pro plans — launched deep in a single Indian city first,
                because the ratio system needs critical mass in one place before it needs breadth.
              </p>
            </div>
          </div>
          <div className="tl-item">
            <div className="tl-phase">Shortly after</div>
            <div>
              <h3>The “We Met” loop goes live</h3>
              <p>
                Once enough real conversations exist, the did-you-actually-meet feedback loop
                starts retraining the matching models on real-world outcomes.
              </p>
            </div>
          </div>
          <div className="tl-item">
            <div className="tl-phase">v2</div>
            <div>
              <h3>Push notifications & richer matching</h3>
              <p>
                Push notifications arrive (at launch, the daily 15 is a reason to open the app,
                not another ping). Matching gets more granular — learning which specific prompt or
                photo earned a like, not just the profile as a whole.
              </p>
            </div>
          </div>
          <div className="tl-item">
            <div className="tl-phase">Scale</div>
            <div>
              <h3>City by city</h3>
              <p>
                Each new city launches as its own fresh, balanced region — the honeycomb design
                means growth adds cities side by side without destabilizing the ones already
                working.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
