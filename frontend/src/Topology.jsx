import { fmt } from "./api.js";

const ATTACK = { SYN: "SYN flood", DNS: "DNS DrDoS", UDP: "UDP DrDoS" };
const SERVER_Y = 17, CLIENT_Y = 74; // % of panel height, node centres

export const clientLabel = (c) => `Client ${c.id} · ${ATTACK[c.attack] ?? c.attack}`;
export const Bar = ({ v }) => <div className="bar"><i style={{ width: `${(v ?? 0) * 100}%` }} /></div>;

export default function Topology({ run, clients, shown, phase }) {
  const xs = clients.map((_, i) => ((i + 0.5) / clients.length) * 100);
  const total = run?.config.rounds ?? 0;
  const idx = run?.history?.round.indexOf(shown) ?? -1;
  const minSamples = Math.min(...clients.map((c) => c.train_samples || Infinity));
  const flying = phase === "sending" ? "down" : phase === "uploading" ? "up" : null;
  const width = `min(170px, calc(${100 / clients.length}% - 16px))`;

  return (
    <div className="topo">
      <svg className="lines" viewBox="0 0 100 100" preserveAspectRatio="none">
        {xs.map((x) => (
          <line key={x} x1="50" y1={SERVER_Y + 8} x2={x} y2={CLIENT_Y - 10} className={flying ? `flow-${flying}` : ""} />
        ))}
      </svg>

      <div className={`node server ${phase === "aggregating" ? "agg" : ""}`} style={{ top: `${SERVER_Y}%` }}>
        <div className="node-kicker">server trung tâm · FedAvg</div>
        <div className="node-title">mô hình toàn cục <span className="mono">v{shown}</span></div>
        <div className="node-stats">
          <span>vòng <b className="mono">{shown}/{total}</b></span>
          <span>F1 <b className="mono accent">{fmt(idx >= 0 ? run.history.global_f1[idx] : null)}</b></span>
        </div>
        <Bar v={total ? shown / total : 0} />
      </div>

      {clients.map((c, i) => {
        const r = c.rounds?.find((x) => x.round === shown);
        const share = c.share ?? (c.train_samples && isFinite(minSamples) ? Math.round(c.train_samples / minSamples) : null);
        return (
          <div key={c.id} style={{ left: `${xs[i]}%`, top: `${CLIENT_Y}%`, width }}
            className={`node client ${phase === "training" ? "train" : ""} ${phase === "uploading" ? "done" : ""}`}>
            <div className="node-kicker">client {c.id} <span className="tag">{c.attack}</span></div>
            <div className="node-title">{ATTACK[c.attack] ?? c.attack}</div>
            <div className="node-stats">
              <span>{share != null ? `${share}× dữ liệu` : "–"} · {c.model}</span>
              <span>F1 <b className="mono">{fmt(r?.val_f1)}</b></span>
            </div>
            <Bar v={r?.val_f1} />
          </div>
        );
      })}

      {flying && xs.map((x) => {
        const down = flying === "down";
        return (
          <i key={`${phase}-${shown}-${x}`} className={`dot ${flying}`} style={{
            "--x0": down ? "50%" : `${x}%`, "--x1": down ? `${x}%` : "50%",
            "--y0": `${down ? SERVER_Y : CLIENT_Y}%`, "--y1": `${down ? CLIENT_Y : SERVER_Y}%`,
          }} />
        );
      })}

      <div className="legend">
        <span className="swatch down" />trọng số toàn cục ↓<span className="swatch up" />cập nhật cục bộ ↑
        <span className="sep">·</span>dữ liệu thô không rời khỏi client
      </div>
    </div>
  );
}
