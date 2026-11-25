import { useEffect, useRef, useState } from "react";

// one FedAvg round, as the viewer sees it
export const PHASES = [["sending", 800], ["training", 900], ["uploading", 800], ["aggregating", 500]];

// Animates each round once it appears in run.history (data-driven, not a timer loop).
// Mount with key={run.id} so a new run starts fresh.
export function useRoundPlayer(run) {
  const last = run?.history?.round.at(-1) ?? 0;
  const [shown, setShown] = useState(last); // rounds already on screen; opening a run shows its current state
  const [phase, setPhase] = useState("idle");
  const [replaying, setReplaying] = useState(false);
  const lastRef = useRef(last);
  lastRef.current = last;
  const pending = last > shown;

  useEffect(() => {
    if (!pending) {
      setReplaying(false);
      return;
    }
    // fell behind (slow poll, fast rounds): catch up instead of replaying old rounds
    if (!replaying && lastRef.current - shown > 2) {
      setShown(lastRef.current);
      return;
    }
    const timers = [];
    let t = 0;
    for (const [p, ms] of PHASES) {
      timers.push(setTimeout(() => setPhase(p), t));
      t += ms;
    }
    timers.push(setTimeout(() => { setPhase("idle"); setShown((s) => s + 1); }, t));
    return () => timers.forEach(clearTimeout);
  }, [shown, pending, replaying]);

  const replay = () => { setShown(0); setReplaying(true); };
  return { shown, phase, replay, playing: pending };
}
