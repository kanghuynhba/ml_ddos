import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MODEL_LABEL, fmt, get } from "./api.js";
import { Info } from "./Info.jsx";
import { clientLabel } from "./Topology.jsx";

const COLORS = ["#0078d4", "#ca5010", "#8764b8", "#107c10", "#c239b3", "#038387"];
const AXIS = { stroke: "#c8c6c4", tick: { fill: "#605e5c", fontSize: 11 } };
const GRID = { stroke: "#edebe9", vertical: false };
const TIP = { contentStyle: { background: "#fff", border: "1px solid #e1dfdd", borderRadius: 2, fontSize: 12, boxShadow: "0 3.2px 7.2px rgba(0,0,0,.13)" }, labelStyle: { color: "#605e5c" } };
const NO_CLIENT_DATA = "Cần dữ liệu theo từng client ở mỗi vòng (đã có trong kế hoạch API).";
export const STATUS_VI = { running: "Đang chạy", done: "Hoàn tất", failed: "Lỗi" };
const kb = (b) => (b == null ? "–" : (b / 1024).toFixed(1));
const Note = ({ children }) => <div className="note">{children}</div>;
const roundLabel = (r) => `Vòng ${r}`;

const historyRows = (run) =>
  run?.history?.round.map((r, i) => ({ round: r, f1: run.history.global_f1[i], loss: run.history.global_loss[i] })) ?? [];

// one row per round, one key per client: {round, client_0: v, ...}
function perClientRows(clients, field) {
  const byRound = {};
  for (const c of clients) for (const r of c.rounds ?? []) (byRound[r.round] ??= { round: r.round })[c.name] = r[field];
  return Object.values(byRound).sort((a, b) => a.round - b.round);
}

// round ticks at a "nice" step (1, 2, 5, 10, …) so 25 rounds reads 0, 5, 10, … 25
export function roundTicks(n) {
  const step = [1, 2, 5, 10, 20, 50, 100].find((s) => n / s <= 6) ?? 100;
  const t = [];
  for (let i = 0; i <= n; i += step) t.push(i);
  if (t.at(-1) !== n) t.push(n);
  return t;
}

// y range that fits the data (and baseline) instead of always 0–1, snapped to 0.05
function f1Domain(values) {
  const lo = Math.max(0, Math.floor((Math.min(...values) - 0.02) * 20) / 20);
  const step = 1 - lo > 0.5 ? 0.25 : 1 - lo > 0.2 ? 0.1 : 0.05;
  const ticks = [];
  for (let v = 1; v >= lo - 1e-9; v -= step) ticks.unshift(+v.toFixed(2));
  return { domain: [ticks[0], 1], ticks };
}

const LegendItem = ({ dashed, color, children }) => (
  <span className="legend-item"><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dashed ? "4 3" : undefined} /></svg>{children}</span>
);

// global F1 per round up to `upTo`, with the best local-only model as a dashed baseline
export function F1Chart({ run, upTo = Infinity, bestLocal, height = 240 }) {
  if (!run?.history) return <Note>Chọn một lượt chạy học liên kết (FL) để xem các vòng.</Note>;
  const all = historyRows(run);
  const data = all.filter((d) => d.round <= upTo);
  // range from the whole run, so the axis doesn't jump while rounds replay
  const y = f1Domain([...all.map((d) => d.f1), ...(bestLocal != null ? [bestLocal] : [])]);
  const rounds = run.config.rounds || 1;
  return (
    <>
      <div className="chart-legend">
        <LegendItem color="#0078d4">F1 của FedAvg</LegendItem>
        {bestLocal != null && <LegendItem dashed color="#8a8886">Mô hình cục bộ tốt nhất ({fmt(bestLocal)})</LegendItem>}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 14 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="round" type="number" domain={[0, rounds]} ticks={roundTicks(rounds)} {...AXIS}
            label={{ value: "Vòng", position: "insideBottom", offset: -8, fill: "#605e5c", fontSize: 11 }} />
          <YAxis domain={y.domain} ticks={y.ticks} allowDataOverflow tickFormatter={(v) => v.toFixed(2)} width={44} {...AXIS}
            label={{ value: "F1", angle: -90, position: "insideLeft", offset: 8, fill: "#605e5c", fontSize: 11 }} />
          <Tooltip formatter={(v) => fmt(v)} labelFormatter={roundLabel} {...TIP} />
          {bestLocal != null && <ReferenceLine y={bestLocal} stroke="#8a8886" strokeDasharray="4 3" />}
          <Line dataKey="f1" name="F1 của FedAvg" stroke="#0078d4" strokeWidth={2} isAnimationActive={false}
            dot={false} activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

export function TrafficTable({ clients, shown }) {
  const hasData = clients.some((c) => c.rounds?.length);
  return (
    <>
      <table>
        <thead><tr><th /><th className="num">↓ KB</th><th className="num">↑ KB</th></tr></thead>
        <tbody>
          {clients.map((c) => {
            const r = c.rounds?.find((x) => x.round === shown);
            return <tr key={c.id}><td>Client {c.id} · {c.attack}</td><td className="num">{kb(r?.bytes_down)}</td><td className="num">{kb(r?.bytes_up)}</td></tr>;
          })}
        </tbody>
      </table>
      {!hasData && <Note>{NO_CLIENT_DATA}</Note>}
    </>
  );
}

export const METRICS = [["f1", "F1"], ["precision", "Precision"], ["recall", "Recall"], ["fpr", "Báo động nhầm"]];
export const METRIC_NAME = Object.fromEntries(METRICS);
const pct = (v, d = 2) => (v == null ? "–" : `${(v * 100).toFixed(d)}%`);
const fmtMetric = (metric, v) => (metric === "fpr" ? pct(v) : fmt(v, 2));

// segmented control to pick which detection metric a table shows
export function MetricSwitch({ value, onChange }) {
  return (
    <div className="seg" role="group" aria-label="Chọn độ đo">
      {METRICS.map(([k, label]) => (
        <button key={k} className={k === value ? "on" : ""} aria-pressed={k === value} onClick={() => onChange(k)}>{label}</button>
      ))}
      <Info k={value} />
    </div>
  );
}

export function CompareTable({ compare, clients, run, localRun, metric = "f1" }) {
  const cols = compare?.columns ?? [...clients.map((c) => `${c.name}_test`), "global_test"];
  // without GET /compare we only know each local model's own test + global test, and FedAvg's global test
  const rows = compare?.rows ?? [
    ...Object.entries(localRun?.local_metrics ?? {}).map(([name, m]) => ({
      model: `local ${name}`,
      f1: cols.map((col) => (col === `${name}_test` ? m.local_test_f1 : col === "global_test" ? m.global_test_f1 : null)),
    })),
    ...(run?.history ? [{ model: "fedavg", f1: cols.map((col) => (col === "global_test" ? run.history.global_f1.at(-1) : null)) }] : []),
  ];
  const colHead = (col) => {
    const c = clients.find((x) => `${x.name}_test` === col);
    if (c) return <>Test client {c.id}<small>{c.attack} <Info text={`Phần test riêng của client ${c.id}: chỉ gồm tấn công ${c.attack} và lưu lượng bình thường của client đó.`} /></small></>;
    if (col === "global_test") return <>Test chung<small>mọi loại tấn công <Info k="globalTest" /></small></>;
    return col;
  };
  const localModel = MODEL_LABEL[localRun?.config.model ?? "mlp"];
  const flModel = MODEL_LABEL[run?.config.model ?? "mlp"];
  const rowLabel = (m) => (m === "fedavg" ? `Liên kết, ${flModel} (trung tâm)` : `${m.replace(/^local client_/, "Cục bộ client ")} · ${localModel}`);

  return (
    <>
      <table className="compare">
        <thead><tr><th>Mô hình</th>{cols.map((c) => <th key={c} className="num">{colHead(c)}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.model} className={r.model === "fedavg" ? "hl" : ""}>
              <td>{rowLabel(r.model)}</td>{(r.values ?? (metric === "f1" ? r.f1 : r.f1.map(() => null))).map((v, i) => <td key={i} className="num">{fmtMetric(metric, v)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {!localRun && <Note>Hãy chạy baseline cục bộ để điền các hàng so sánh.</Note>}
      {!compare && rows.length > 0 && <Note>Ô “–” cần API GET /compare (đang trong kế hoạch).</Note>}
      {compare && metric !== "f1" && compare.rows.some((r) => r.values?.some((v) => v == null)) &&
        <Note>Ô “–”: lượt chạy được tạo trước khi có số liệu chi tiết. Chạy lại để có {METRIC_NAME[metric]}.</Note>}
      {metric === "fpr" && <Note>Với tỉ lệ báo động nhầm, <b>càng thấp càng tốt</b>.</Note>}
      <Note>Mỗi mô hình cục bộ tốt trên loại tấn công của chính nó và yếu với các loại khác. Mô hình liên kết cần tốt trên tất cả.</Note>
    </>
  );
}

export function Convergence({ run }) {
  const data = historyRows(run);
  if (!data.length) return <Note>Chọn một lượt chạy học liên kết (FL).</Note>;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data}>
        <CartesianGrid {...GRID} /><XAxis dataKey="round" type="number" domain={[0, data.at(-1).round]} ticks={roundTicks(data.at(-1).round)} {...AXIS} />
        <YAxis yAxisId="f1" domain={[0, 1]} {...AXIS} /><YAxis yAxisId="loss" orientation="right" tickFormatter={(v) => v.toFixed(2)} {...AXIS} />
        <Tooltip formatter={(v) => fmt(v)} labelFormatter={roundLabel} {...TIP} /><Legend />
        <Line yAxisId="f1" dataKey="f1" name="F1 toàn cục" stroke="#0078d4" dot={false} isAnimationActive={false} />
        <Line yAxisId="loss" dataKey="loss" name="Loss toàn cục" stroke="#ca5010" dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function PerClient({ clients }) {
  if (!clients.some((c) => c.rounds?.length)) return <Note>{NO_CLIENT_DATA}</Note>;
  const chart = (field, title, info, domain) => (
    <div style={{ flex: 1 }}>
      <div className="card-title">{title} <Info k={info} /></div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={perClientRows(clients, field)}>
          <CartesianGrid {...GRID} /><XAxis dataKey="round" {...AXIS} /><YAxis domain={domain} {...AXIS} />
          <Tooltip formatter={(v) => fmt(v)} labelFormatter={roundLabel} {...TIP} /><Legend />
          {clients.map((c, i) => (
            <Line key={c.id} dataKey={c.name} name={clientLabel(c)} stroke={COLORS[i % COLORS.length]} dot={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
  return <div className="row">{chart("val_f1", "F1 validation", "valF1", [0, 1])}{chart("train_loss", "Loss khi train", "trainLoss", ["auto", "auto"])}</div>;
}

export function CommCost({ clients }) {
  if (!clients.some((c) => c.rounds?.length)) return <Note>{NO_CLIENT_DATA}</Note>;
  const sum = (c, k) => c.rounds.reduce((s, r) => s + (r[k] ?? 0), 0);
  const all = (k) => clients.reduce((s, c) => s + sum(c, k), 0);
  return (
    <table>
      <thead><tr><th>Client</th><th className="num">Số vòng</th><th className="num">Tổng ↓ KB</th><th className="num">Tổng ↑ KB</th></tr></thead>
      <tbody>
        {clients.map((c) => (
          <tr key={c.id}><td>{clientLabel(c)}</td><td className="num">{c.rounds.length}</td><td className="num">{kb(sum(c, "bytes_down"))}</td><td className="num">{kb(sum(c, "bytes_up"))}</td></tr>
        ))}
        <tr className="hl"><td>Tất cả client</td><td /><td className="num">{kb(all("bytes_down"))}</td><td className="num">{kb(all("bytes_up"))}</td></tr>
      </tbody>
    </table>
  );
}

export function RunsTab({ runs, selId, onSelect }) {
  const [log, setLog] = useState(null);
  const showLog = (id) => get(`/runs/${id}/log`).then((r) => setLog({ id, text: r?.log ?? "(không có log)" }));
  const result = (r) =>
    r.history ? `F1 ${fmt(r.history.global_f1.at(-1))} @ vòng ${r.history.round.at(-1)}`
      : r.local_metrics ? Object.entries(r.local_metrics).map(([k, v]) => `${k} ${fmt(v.global_test_f1)}`).join(" · ") : "–";
  return (
    <>
      <table>
        <thead><tr><th>Mã lượt chạy</th><th>Trạng thái</th><th>Cấu hình</th><th>Kết quả</th><th /></tr></thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className={`click ${r.id === selId ? "hl" : ""}`} onClick={() => onSelect(r.id)}>
              <td>{r.id}</td><td><span className={`status ${r.status}`}><i />{STATUS_VI[r.status] ?? r.status}</span></td>
              <td><code>{MODEL_LABEL[r.config.model ?? "mlp"]} · {r.config.kind === "fl" ? `${r.config.mu > 0 ? `FedProx μ=${r.config.mu}` : "FedAvg"}${r.config.weighting === "uniform" ? " · đều" : ""} · ${r.config.rounds} vòng · ` : "local · "}{r.config.model === "rf" ? "100 cây" : `${r.config.epochs} epoch · lr ${r.config.lr} · batch ${r.config.batch_size}`}{r.config.seed != null && ` · seed ${r.config.seed}`}</code></td>
              <td>{result(r)}</td>
              <td><button className="link" onClick={(e) => { e.stopPropagation(); showLog(r.id); }}>Xem log</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      {log && <><div className="card-title" style={{ marginTop: 14 }}>Log · {log.id}</div><pre className="log">{log.text}</pre></>}
    </>
  );
}

// 2x2 confusion matrix of the federated model on one test set (attack = positive)
export function ConfusionMatrix({ run, clients }) {
  const cols = run?.final?.columns ?? [];
  const [col, setCol] = useState(Math.max(0, cols.length - 1));
  if (run?.config.kind !== "fl") return <Note>Chọn một lượt chạy học liên kết (FL).</Note>;
  const ms = run.final?.metrics;
  if (!ms) return <Note>{run.status === "running" ? "Ma trận có sau vòng cuối cùng." : "Lượt chạy này được tạo trước khi có số liệu chi tiết. Hãy chạy lại để xem ma trận nhầm lẫn."}</Note>;
  const m = ms[col] ?? ms.at(-1);
  const n = (v) => v.toLocaleString("vi-VN");
  const share = (a, b) => (b ? `${((100 * a) / b).toFixed((100 * a) / b < 1 ? 2 : 1)}%` : "–");
  const label = (c) => {
    const cl = clients.find((x) => `${x.name}_test` === c);
    return c === "global_test" ? "Test chung (mọi loại tấn công)" : cl ? `Test client ${cl.id} (${cl.attack})` : c;
  };
  const attacks = m.tp + m.fn, benign = m.fp + m.tn;
  return (
    <>
      <label className="cmd-select" style={{ marginBottom: 12 }}>Tập kiểm thử
        <select value={col} onChange={(e) => setCol(Number(e.target.value))}>
          {cols.map((c, i) => <option key={c} value={i}>{label(c)}</option>)}
        </select>
      </label>
      <table className="cm">
        <thead><tr><th /><th>Mô hình nói: <b>tấn công</b></th><th>Mô hình nói: <b>bình thường</b></th></tr></thead>
        <tbody>
          <tr>
            <th>Thật sự là tấn công <small>{n(attacks)} flow</small></th>
            <td className="ok"><span>TP · bắt được</span><b>{n(m.tp)}</b><small>{share(m.tp, attacks)} số tấn công</small></td>
            <td className="miss"><span>FN · bỏ sót</span><b>{n(m.fn)}</b><small>{share(m.fn, attacks)} số tấn công</small></td>
          </tr>
          <tr>
            <th>Thật sự bình thường <small>{n(benign)} flow</small></th>
            <td className="miss"><span>FP · báo động nhầm</span><b>{n(m.fp)}</b><small>{share(m.fp, benign)} lưu lượng bình thường</small></td>
            <td className="ok"><span>TN · đúng, im lặng</span><b>{n(m.tn)}</b><small>{share(m.tn, benign)} lưu lượng bình thường</small></td>
          </tr>
        </tbody>
      </table>
      <div className="cm-rates">
        <span>Precision <Info k="precision" /> <b>{fmt(m.precision)}</b></span>
        <span>Recall <Info k="recall" /> <b>{fmt(m.recall)}</b></span>
        <span>F1 <Info k="f1" /> <b>{fmt(m.f1)}</b></span>
        <span>Tỉ lệ báo động nhầm <Info k="fpr" /> <b>{pct(m.fpr)}</b></span>
      </div>
    </>
  );
}

// precision / recall (left axis) and false-alarm rate (right axis, %) of the global model per round
export function DetectionChart({ run }) {
  const h = run?.history;
  if (!h?.global_precision?.length) return <Note>{run?.config.kind === "fl" ? "Lượt chạy này được tạo trước khi có precision/recall theo vòng. Hãy chạy lại." : "Chọn một lượt chạy học liên kết (FL)."}</Note>;
  const data = h.round.map((r, i) => ({ round: r, precision: h.global_precision[i], recall: h.global_recall[i], fpr: h.global_fpr[i] * 100 }));
  const rounds = data.at(-1).round;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="round" type="number" domain={[0, rounds]} ticks={roundTicks(rounds)} {...AXIS} />
        <YAxis yAxisId="r" domain={[0, 1]} tickFormatter={(v) => v.toFixed(2)} width={44} {...AXIS} />
        <YAxis yAxisId="f" orientation="right" tickFormatter={(v) => `${v.toFixed(0)}%`} width={44} {...AXIS} />
        <Tooltip formatter={(v, name) => (name.startsWith("Tỉ lệ") ? `${v.toFixed(2)}%` : fmt(v))} labelFormatter={roundLabel} {...TIP} />
        <Legend />
        <Line yAxisId="r" dataKey="precision" name="Precision" stroke="#0078d4" dot={false} isAnimationActive={false} />
        <Line yAxisId="r" dataKey="recall" name="Recall (tỉ lệ phát hiện)" stroke="#107c10" dot={false} isAnimationActive={false} />
        <Line yAxisId="f" dataKey="fpr" name="Tỉ lệ báo động nhầm (trục phải)" stroke="#d13438" strokeDasharray="5 3" dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// detection rate per attack type on the shared test: the federated model vs the best/worst local-only model
export function PerAttackTable({ run, localRun, clients }) {
  const pa = run?.final?.per_attack;
  if (!pa) return <Note>Chưa có: cần lượt chạy học liên kết trên dữ liệu v2 (có cột loại tấn công trong tập test).</Note>;
  const trained = new Set(clients.flatMap((c) => c.attacks ?? [c.attack]));
  const locals = Object.values(localRun?.local_metrics ?? {}).filter((m) => m.per_attack);
  const rows = Object.entries(pa).map(([key, v]) => {
    const [attack, day] = key.split("@");
    const rates = locals.map((m) => m.per_attack[key]?.rate).filter((x) => x != null);
    return { key, attack, day, n: v.n, fl: v.rate, best: rates.length ? (attack === "BENIGN" ? Math.min(...rates) : Math.max(...rates)) : null,
             worst: rates.length ? (attack === "BENIGN" ? Math.max(...rates) : Math.min(...rates)) : null };
  }).sort((a, b) => (a.attack === "BENIGN") - (b.attack === "BENIGN") || a.day.localeCompare(b.day) || a.attack.localeCompare(b.attack));
  const tone = (r, v) => (v == null ? "" : r.attack === "BENIGN" ? (v <= 0.01 ? "good" : v >= 0.05 ? "bad" : "") : v >= 0.95 ? "good" : v < 0.5 ? "bad" : "");
  const cell = (r, v) => <td className={`num rate ${tone(r, v)}`}>{v == null ? "–" : `${(v * 100).toFixed(1)}%`}</td>;
  return (
    <>
      <table className="per-attack">
        <thead><tr>
          <th>Loại lưu lượng</th><th>Ngày</th><th className="num">Số flow</th>
          <th className="num">Liên kết</th><th className="num">Cục bộ tốt nhất</th><th className="num">Cục bộ kém nhất</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={r.attack === "BENIGN" ? "benign" : ""}>
              <td>
                {r.attack === "BENIGN" ? <>Bình thường <small>(tỉ lệ báo nhầm, thấp là tốt)</small></> : r.attack}
                {r.attack !== "BENIGN" && !trained.has(r.attack) && <span className="badge warn">chưa client nào học</span>}
              </td>
              <td>{r.day === "test_day" ? <span className="badge">ngày khác</span> : "cùng ngày"}</td>
              <td className="num">{r.n.toLocaleString("vi-VN")}</td>
              {cell(r, r.fl)}{cell(r, r.best)}{cell(r, r.worst)}
            </tr>
          ))}
        </tbody>
      </table>
      <Note>Với tấn công: tỉ lệ flow bị phát hiện (càng cao càng tốt). “Ngày khác” = lưu lượng từ ngày ghi thứ hai, mô hình chưa từng thấy ngày này.
        {!locals.length && " Chạy baseline cục bộ trên dữ liệu v2 để có hai cột so sánh."}</Note>
    </>
  );
}
