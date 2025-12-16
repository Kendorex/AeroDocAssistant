const API_BASE = "http://127.0.0.1:8000";

export async function classify(text) {
  const res = await fetch(`${API_BASE}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || "classify failed");
  }
  return res.json(); // { label }
}

export async function chat(text) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || "chat failed");
  }
  return res.json(); // { answer, sources }
}
