import { useState, useEffect, useRef } from "react";

function highlightText(text, words) {
  if (!words.length || !text) return text;
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, i) =>
    regex.test(part) ? <mark key={i}>{part}</mark> : part
  );
}

function snippetAround(text, words, maxLen = 300) {
  if (!text) return "";
  if (text.length <= maxLen) return text;
  const lower = text.toLowerCase();
  let bestIdx = 0;
  for (const w of words) {
    const idx = lower.indexOf(w.toLowerCase());
    if (idx !== -1) {
      bestIdx = idx;
      break;
    }
  }
  const start = Math.max(0, bestIdx - Math.floor(maxLen / 2));
  const end = Math.min(text.length, start + maxLen);
  let snippet = text.slice(start, end);
  if (start > 0) snippet = "…" + snippet;
  if (end < text.length) snippet = snippet + "…";
  return snippet;
}

const ALL_FIELDS = [
  { key: "title", label: "Título" },
  { key: "description", label: "Descrição" },
  { key: "categories", label: "Categorias" },
  { key: "tags", label: "Tags" },
  { key: "authors", label: "Autores" },
  { key: "transcriptions", label: "Transcrições" },
];

const ALL_KEYS = ALL_FIELDS.map((f) => f.key);

function loadFields() {
  try {
    const stored = localStorage.getItem("searchFields");
    if (stored) return JSON.parse(stored);
  } catch {}
  return ALL_KEYS;
}

export default function App() {
  const [query, setQuery] = useState("");
  const [fields, setFields] = useState(loadFields);
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);

  function toggleField(key) {
    setFields((prev) => {
      const next = prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key];
      localStorage.setItem("searchFields", JSON.stringify(next));
      return next;
    });
  }

  function doSearch(q, p = 1, f = fields) {
    if (!q.trim()) {
      setResults([]);
      setTotal(0);
      setPage(1);
      setPages(1);
      return;
    }
    setLoading(true);
    const params = new URLSearchParams();
    params.set("q", q);
    params.set("page", p);
    f.forEach((field) => params.append("fields", field));
    fetch(`/api/search?${params}`)
      .then((r) => r.json())
      .then((data) => {
        setResults(data.results);
        setTotal(data.total);
        setPage(data.page);
        setPages(data.pages);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      doSearch(query, 1, fields);
    }, 300);
    return () => clearTimeout(timerRef.current);
  }, [query, fields]);

  const words = query.trim().split(/\s+/).filter(Boolean);

  return (
    <div className="container">
      <h1>IRDIN — Pesquisa de Palestras</h1>
      <input
        type="text"
        className="search-input"
        placeholder="Pesquisar palestras…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />

      <div className="field-filters">
        {ALL_FIELDS.map(({ key, label }) => (
          <label key={key} className="field-checkbox">
            <input
              type="checkbox"
              checked={fields.includes(key)}
              onChange={() => toggleField(key)}
            />
            {label}
          </label>
        ))}
      </div>

      {loading && <p className="status">Buscando…</p>}

      {!loading && query.trim() && (
        <p className="status">
          {total} resultado{total !== 1 ? "s" : ""} encontrado
          {total !== 1 ? "s" : ""}
        </p>
      )}

      <div className="results">
        {results.map((r) => (
          <div key={r.id} className="result-card">
            <h2>
              <a href={r.url} target="_blank" rel="noopener noreferrer">
                {highlightText(r.title, words)}
              </a>
            </h2>
            {r.authors.length > 0 && (
              <p className="meta authors">
                {highlightText(r.authors.join(", "), words)}
              </p>
            )}
            {(r.categories || r.tags) && (
              <p className="meta tags">
                {highlightText(
                  [r.categories, r.tags].filter(Boolean).join(" · "),
                  words
                )}
              </p>
            )}
            {r.description && (
              <p className="description">
                {highlightText(snippetAround(r.description, words), words)}
              </p>
            )}
            {r.track_count > 0 && (
              <p className="meta tracks">
                {r.track_count} faixa{r.track_count !== 1 ? "s" : ""} de áudio
              </p>
            )}
            {r.transcription_snippets?.length > 0 && (
              <div className="transcription-matches">
                {r.transcription_snippets.map((t, i) => (
                  <div key={i} className="transcription-snippet">
                    <span className="snippet-label">{t.track_name}:</span>{" "}
                    {highlightText(t.snippet, words)}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {pages > 1 && (
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => doSearch(query, page - 1)}>
            ← Anterior
          </button>
          <span>
            Página {page} de {pages}
          </span>
          <button
            disabled={page >= pages}
            onClick={() => doSearch(query, page + 1)}
          >
            Próxima →
          </button>
        </div>
      )}
    </div>
  );
}
