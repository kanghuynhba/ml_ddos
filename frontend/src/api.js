export const API = import.meta.env.VITE_API_URL;

// 404 -> null, so planned (🔜) endpoints that don't exist yet just read as "no data"
export async function get(path) {
  const r = await fetch(API + path);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`GET ${path}: ${r.status}`);
  return r.json();
}

export async function post(path, body) {
  const r = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export const fmt = (v, d = 3) => (v == null ? "–" : v.toFixed(d));

// runs from before the model option have no `model` field; they were MLP
export const MODEL_LABEL = { mlp: "MLP", cnn: "1D-CNN", rf: "Random Forest" };
