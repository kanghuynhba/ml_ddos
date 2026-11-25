import { useEffect, useState } from "react";
import { MODEL_LABEL, fmt, get, post } from "./api.js";
import Topology from "./Topology.jsx";
import { Info } from "./Info.jsx";
import { CommCost, CompareTable, ConfusionMatrix, Convergence, DetectionChart, F1Chart, METRIC_NAME, MetricSwitch, PerClient, RunsTab, STATUS_VI, TrafficTable } from "./Panels.jsx";
import { PHASES, useRoundPlayer } from "./useRoundPlayer.js";
import "./styles.css";

const PAGES = [
  ["overview", "▦", "Tổng quan"],
  ["flow", "⇅", "Quá trình huấn luyện"],
  ["quality", "◔", "Chất lượng mô hình"],
  ["clients", "▤", "Client"],
  ["comm", "⇄", "Chi phí truyền thông"],
  ["runs", "☰", "Lượt chạy"],
];
const STEP_LABEL = { sending: "Gửi mô hình", training: "Huấn luyện cục bộ", uploading: "Gửi cập nhật", aggregating: "Tổng hợp" };

export default function App() {
  const [runs, setRuns] = useState([]);
  const [clientList, setClientList] = useState(null);
  const [selId, setSelId] = useState(null);
  const [page, setPage] = useState("overview");
  const [compare, setCompare] = useState(null);
  const [metric, setMetric] = useState("f1");
  const [newRun, setNewRun] = useState(false);
  const [err, setErr] = useState("");

  const load = () => get("/runs").then((r) => { setRuns(r ?? []); setErr(""); }).catch((e) => setErr(`Không kết nối được backend: ${e.message}`));
  useEffect(() => { load(); const t = setInterval(load, 1500); return () => clearInterval(t); }, []);
  useEffect(() => { get("/clients").then(setClientList).catch(() => {}); }, []);

  // /runs is newest first
  const run = runs.find((r) => r.id === selId) ?? runs.find((r) => r.config.kind === "fl");
  const localRun = runs.find((r) => r.config.kind === "local" && r.status === "done");
  const clients = run?.clients ?? clientList ?? [];
  const bestLocal = localRun ? Math.max(...Object.values(localRun.local_metrics ?? {}).map((m) => m.global_test_f1)) : null;

  useEffect(() => {
    if (!run?.history || !localRun) return setCompare(null);
    get(`/compare?fl=${run.id}&local=${localRun.id}&metric=${metric}`).then(setCompare).catch(() => setCompare(null));
  }, [run?.id, run?.status, localRun?.id, metric]);

  const title = PAGES.find((p) => p[0] === page)[2];
  const ctx = { run, runs, localRun, clients, bestLocal, compare, metric, setMetric };
  const compareCard = (
    <Card title={`So sánh cục bộ và liên kết: ${METRIC_NAME[metric]} theo tập kiểm thử`} info="compare"
      actions={<MetricSwitch value={metric} onChange={setMetric} />}>
      <CompareTable compare={compare} clients={clients} run={run} localRun={localRun} metric={metric} />
    </Card>
  );

  return (
    <div className="shell">
      <div className="topbar">
        <span className="product">FL-DDoS</span><span className="topbar-sep" />
        <span className="topbar-sub">Phát hiện tấn công DDoS bằng học liên kết · CIC-DDoS2019</span>
        <span className="spacer" />
        <span className={`conn ${err ? "off" : "on"}`}>{err ? "Mất kết nối backend" : "Đã kết nối backend"}</span>
      </div>

      <div className="body">
        <nav className="sidenav">
          {PAGES.map(([id, icon, label]) => (
            <a key={id} className={id === page ? "on" : ""} onClick={() => setPage(id)}><span className="icon">{icon}</span>{label}</a>
          ))}
        </nav>

        <main>
          <div className="breadcrumb">Trang chủ <span>›</span> FL-DDoS <span>›</span> {title}</div>
          <h1>{title}{run && <small>{run.config.kind === "fl" ? "Lượt chạy học liên kết" : "Lượt chạy cục bộ"} · {run.id}</small>}</h1>

          <div className="cmdbar">
            <button className="cmd" onClick={() => setNewRun(true)}><span>＋</span> Lượt chạy mới</button>
            <button className="cmd" onClick={load}><span>↻</span> Làm mới</button>
            <span className="cmd-sep" />
            <label className="cmd-select">Lượt chạy
              <select value={run?.id ?? ""} onChange={(e) => setSelId(e.target.value)}>
                {runs.map((r) => <option key={r.id} value={r.id}>{r.id} · {r.config.kind} · {STATUS_VI[r.status] ?? r.status}</option>)}
              </select>
            </label>
          </div>

          {err && <div className="msgbar error">{err}</div>}

          {page === "overview" && <Overview {...ctx} compareCard={compareCard} />}
          {page === "flow" && <FlowView key={run?.id ?? "none"} {...ctx} />}
          {page === "quality" && (
            <>
              <div className="grid-2">
                <Card title="Ma trận nhầm lẫn của mô hình liên kết" info="confusion"><ConfusionMatrix key={run?.id} run={run} clients={clients} /></Card>
                <Card title="Precision, Recall và tỉ lệ báo động nhầm theo vòng" info="fpr"><DetectionChart run={run} /></Card>
              </div>
              <Card title="F1 và loss toàn cục theo từng vòng" info="loss"><Convergence run={run} /></Card>
              {compareCard}
            </>
          )}
          {page === "clients" && (
            <>
              <Card title={`Danh sách client (${clients.length})`} info="nonIID"><ClientsTable clients={clients} localRun={localRun} /></Card>
              <Card title="Huấn luyện tại từng client"><PerClient clients={clients} /></Card>
            </>
          )}
          {page === "comm" && <Card title="Dữ liệu trao đổi với server" info="bytes"><CommCost clients={clients} /></Card>}
          {page === "runs" && <Card title={`Các lượt chạy (${runs.length})`}><RunsTab runs={runs} selId={run?.id} onSelect={(id) => { setSelId(id); setPage("overview"); }} /></Card>}
        </main>
      </div>

      {newRun && <NewRunPanel onClose={() => setNewRun(false)} onStarted={(id) => { setSelId(id); setNewRun(false); load(); }} />}
    </div>
  );
}

const Card = ({ title, info, actions, children, style }) => (
  <section className="card" style={style}>
    {title && <div className="card-head"><div className="card-title">{title}{info && <> <Info k={info} /></>}</div>{actions}</div>}
    {children}
  </section>
);

const Kpi = ({ label, info, value, sub, tone }) => (
  <div className="kpi"><div className="kpi-label">{label} <Info k={info} /></div><div className={`kpi-value ${tone ?? ""}`}>{value}</div>{sub && <div className="kpi-sub">{sub}</div>}</div>
);

// "FedAvg" / "FedProx (μ=0.1)" plus how clients are weighted
const modelOf = (c) => MODEL_LABEL[c?.model ?? "mlp"];

export const strategyLabel = (c) =>
  c?.kind !== "fl" ? "Chỉ huấn luyện cục bộ"
    : `${c.mu > 0 ? `FedProx (μ=${c.mu})` : "FedAvg"} · ${c.weighting === "uniform" ? "trọng số đều giữa các client" : "trọng số theo số mẫu"}`;

const Status = ({ s }) => <span className={`status ${s}`}><i />{STATUS_VI[s] ?? s}</span>;

function Overview({ run, localRun, clients, bestLocal, compareCard }) {
  const h = run?.history, c = run?.config;
  const f1 = h?.global_f1.at(-1), prev = h?.global_f1.at(-2);
  const gain = f1 != null && bestLocal != null ? f1 - bestLocal : null;
  const gm = run?.final?.metrics?.at(-1); // shared test, full confusion counts
  const fpr = gm?.fpr ?? h?.global_fpr?.at(-1);
  const signed = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)}`;
  return (
    <>
      <Card title="Thông tin chính">
        <div className="essentials">
          <div><span>Lượt chạy</span>{run?.id ?? "–"}</div>
          <div><span>Trạng thái</span>{run ? <Status s={run.status} /> : "–"}</div>
          <div><span>Chiến lược</span><span className="v">{c ? <>{strategyLabel(c)}{c.kind === "fl" && <> <Info k={c.mu > 0 ? "fedprox" : c.weighting === "uniform" ? "uniform" : "fedavg"} /></>}</> : "–"}</span></div>
          <div><span>Bộ dữ liệu</span>CIC-DDoS2019</div>
          <div><span>Clients</span>{clients.length} client · mô hình {modelOf(c)}</div>
          <div><span>Siêu tham số</span>{c ? `${c.kind === "fl" ? `${c.rounds} vòng · ` : ""}${c.model === "rf" ? "100 cây" : `${c.epochs} epoch · lr ${c.lr} · batch ${c.batch_size}`}${c.seed != null ? ` · seed ${c.seed}` : ""}` : "–"}</div>
          <div><span>Bắt đầu lúc</span>{run ? new Date(run.started * 1000).toLocaleString("vi-VN") : "–"}</div>
          <div><span>Lượt chạy baseline</span>{localRun?.id ?? "chưa có"}</div>
        </div>
      </Card>

      <div className="kpis">
        <Kpi label="F1 toàn cục (FedAvg)" info="globalF1" value={fmt(f1)} sub={prev != null ? `${signed(f1 - prev)} so với vòng trước` : null} />
        <Kpi label="Mô hình cục bộ tốt nhất" info="bestLocal" value={fmt(bestLocal)} sub={bestLocal == null ? "hãy chạy baseline cục bộ" : "F1 trên tập kiểm thử chung"} />
        <Kpi label="FedAvg so với cục bộ tốt nhất" info="gain" value={gain == null ? "–" : signed(gain)} tone={gain == null ? "" : gain >= 0 ? "good" : "bad"}
          sub={gain == null ? null : gain >= 0 ? "mô hình liên kết tốt hơn" : "mô hình cục bộ vẫn tốt hơn"} />
        <Kpi label="Tỉ lệ báo động nhầm" info="fpr" value={fpr == null ? "–" : `${(fpr * 100).toFixed(2)}%`}
          sub={gm ? `${gm.fp.toLocaleString("vi-VN")} / ${(gm.fp + gm.tn).toLocaleString("vi-VN")} flow bình thường bị báo nhầm` : fpr != null ? "trên tập kiểm thử chung" : run?.config.kind === "fl" ? "lượt chạy cũ, chưa có số liệu" : null} />
        <Kpi label="Số vòng đã hoàn thành" info="round" value={h ? `${h.round.at(-1)} / ${c.rounds}` : "–"} sub={run?.status === "running" ? "đang huấn luyện" : null} />
      </div>

      <div className="grid-2">
        <Card title="F1 toàn cục theo từng vòng" info="f1"><F1Chart run={run} bestLocal={bestLocal} /></Card>
        {compareCard}
      </div>
    </>
  );
}

function FlowView({ run, clients, bestLocal }) {
  const { shown, phase, replay, playing } = useRoundPlayer(run);
  const c = run?.config;
  const r = shown + 1;
  const caption = {
    sending: `Vòng ${r}: server gửi mô hình toàn cục hiện tại xuống tất cả client.`,
    training: `Vòng ${r}: mỗi client huấn luyện ${c?.epochs} epoch trên lưu lượng của chính mình. Dữ liệu thô không rời khỏi client.`,
    uploading: `Vòng ${r}: các client gửi trọng số đã cập nhật về server. Không gửi dữ liệu lưu lượng.`,
    aggregating: `Vòng ${r}: server lấy trung bình các cập nhật ${c?.weighting === "uniform" ? "với trọng số đều nhau giữa các client" : "có trọng số theo số mẫu của từng client"}.`,
  }[phase] ?? (run?.status === "running" ? "Đang chờ vòng tiếp theo hoàn tất…" : "Lượt chạy đã xong. Bấm “Phát lại các vòng” để xem lại từng bước.");

  return (
    <div className="grid-flow">
      <Card title="Sơ đồ học liên kết" info="round" actions={run?.history && run.status !== "running" && !playing && <button className="link" onClick={replay}>▷ Phát lại các vòng</button>}>
        <ol className="steps">
          {PHASES.map(([p], i) => <li key={p} className={p === phase ? "on" : ""}><b>{i + 1}</b>{STEP_LABEL[p]}</li>)}
        </ol>
        <Topology run={run} clients={clients} shown={shown} phase={phase} />
        <div className="msgbar neutral">{caption}</div>
      </Card>
      <div className="stack">
        <Card title={`F1 toàn cục · vòng ${shown}`} info="globalF1"><F1Chart run={run} upTo={shown} bestLocal={bestLocal} height={190} /></Card>
        <Card title={`Dữ liệu trao đổi · vòng ${shown}`} info="bytes"><TrafficTable clients={clients} shown={shown} /></Card>
      </div>
    </div>
  );
}

function ClientsTable({ clients, localRun }) {
  return (
    <table>
      <thead><tr><th>Client</th><th>Loại tấn công</th><th>Mô hình</th><th className="num">Số mẫu train <Info k="samples" /></th><th className="num">F1 cục bộ, test riêng <Info k="ownTest" /></th><th className="num">F1 cục bộ, test chung <Info k="globalTest" /></th></tr></thead>
      <tbody>
        {clients.map((c) => {
          const m = localRun?.local_metrics?.[c.name];
          return (
            <tr key={c.id}>
              <td>{c.name}</td><td>{c.attack}</td><td>{c.model}</td>
              <td className="num">{c.train_samples?.toLocaleString() ?? "–"}</td>
              <td className="num">{fmt(m?.local_test_f1)}</td><td className="num">{fmt(m?.global_test_f1)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function NewRunPanel({ onClose, onStarted }) {
  const [cfg, setCfg] = useState({ kind: "fl", rounds: 25, epochs: 2, lr: 0.001, batch_size: 64, mu: 0, weighting: "uniform", seed: "", model: "mlp" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const field = (k, label, step, help) => (
    <label className="field">{label}
      <input type="number" step={step} value={cfg[k]} onChange={(e) => setCfg({ ...cfg, [k]: Number(e.target.value) })} />
      {help && <small>{help}</small>}
    </label>
  );
  const start = async () => {
    setBusy(true); setErr("");
    const body = { ...cfg, seed: cfg.seed === "" ? null : Number(cfg.seed) };
    if (cfg.kind === "local") { delete body.mu; delete body.weighting; delete body.rounds; }
    if (cfg.model === "rf") { delete body.epochs; delete body.lr; delete body.batch_size; }
    try { onStarted((await post("/runs", body)).id); } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  return (
    <div className="overlay" onClick={onClose}>
      <aside className="blade" onClick={(e) => e.stopPropagation()}>
        <div className="blade-head"><h2>Lượt chạy mới</h2><button className="x" onClick={onClose} aria-label="Đóng">✕</button></div>
        <div className="blade-body">
          <label className="field">Loại lượt chạy
            <select value={cfg.kind} onChange={(e) => setCfg({ ...cfg, kind: e.target.value, model: e.target.value === "fl" && cfg.model === "rf" ? "mlp" : cfg.model })}>
              <option value="fl">Học liên kết (FedAvg)</option><option value="local">Baseline chỉ cục bộ</option>
            </select>
          </label>
          <label className="field">Mô hình tại client
            <select value={cfg.model} onChange={(e) => setCfg({ ...cfg, model: e.target.value })}>
              <option value="mlp">MLP</option>
              <option value="cnn">1D-CNN</option>
              {cfg.kind === "local" && <option value="rf">Random Forest</option>}
            </select>
            <small>{cfg.kind === "fl" ? "Mọi client dùng cùng kiến trúc (FedAvg chỉ lấy trung bình được trọng số của cùng một mạng). Random Forest không có trọng số để lấy trung bình nên chỉ chạy cục bộ."
              : cfg.model === "rf" ? "Random Forest (100 cây) không dùng epoch, learning rate hay batch size." : null}</small>
          </label>
          {cfg.kind === "fl" && field("rounds", "Số vòng", 1, "Số chu kỳ server ⇄ client, từ 1 đến 500")}
          {cfg.model !== "rf" && field("epochs", cfg.kind === "fl" ? "Số epoch cục bộ mỗi vòng" : "Số epoch", 1, cfg.kind === "fl" ? "Nên 1–5; nhiều hơn khiến các client trôi xa nhau" : null)}
          {cfg.model !== "rf" && field("lr", "Learning rate (tốc độ học)", 0.0001)}
          {cfg.model !== "rf" && field("batch_size", "Batch size (số mẫu mỗi lô)", 8)}
          {cfg.kind === "fl" && (
            <>
              {field("mu", "μ của FedProx", 0.01, "0 = FedAvg thường; 0.01–1 giữ client gần mô hình toàn cục")}
              <label className="field">Trọng số khi tổng hợp
                <select value={cfg.weighting} onChange={(e) => setCfg({ ...cfg, weighting: e.target.value })}>
                  <option value="uniform">Đều nhau giữa các client (mặc định)</option>
                  <option value="samples">Theo số mẫu (FedAvg gốc)</option>
                </select>
                <small>“Đều nhau” cho client ít dữ liệu (SYN) tiếng nói ngang client lớn; thí nghiệm cho thấy F1 SYN tăng từ 0.61 lên 0.95</small>
              </label>
            </>
          )}
          <label className="field">Seed (tùy chọn)
            <input type="number" step={1} min={0} value={cfg.seed} placeholder="ngẫu nhiên"
              onChange={(e) => setCfg({ ...cfg, seed: e.target.value })} />
            <small>Đặt seed để lặp lại kết quả; chạy nhiều seed để so sánh công bằng</small>
          </label>
          {err && <div className="msgbar error">{err}</div>}
        </div>
        <div className="blade-foot">
          <button className="primary" onClick={start} disabled={busy}>{busy ? "Đang khởi động…" : "Bắt đầu"}</button>
          <button className="secondary" onClick={onClose}>Hủy</button>
        </div>
      </aside>
    </div>
  );
}
