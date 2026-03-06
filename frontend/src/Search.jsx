import { useState, useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";

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
  { key: "transcriptions", label: "Transcrições" },
];

function loadFields() {
  try {
    const stored = localStorage.getItem("searchFields");
    if (stored) return JSON.parse(stored);
  } catch {}
  return [];
}

function loadSelectedAuthors() {
  try {
    const stored = localStorage.getItem("searchAuthors");
    if (stored) return JSON.parse(stored);
  } catch {}
  return [];
}

function loadSelectedLanguages() {
  try {
    const stored = localStorage.getItem("searchLanguages");
    if (stored) return JSON.parse(stored);
  } catch {}
  return [];
}

function CheckboxDropdown({ label, pluralLabel, items, selected, onToggle }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const btnLabel =
    selected.length === 0
      ? label
      : selected.length === 1
      ? items.find((i) => i.value === selected[0])?.label || selected[0]
      : `${selected.length} ${(pluralLabel || label).toLowerCase()}`;

  return (
    <div className="author-dropdown" ref={ref}>
      <button
        className={`author-dropdown-btn${selected.length > 0 ? " active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        type="button"
      >
        {btnLabel} ▾
      </button>
      {open && (
        <div className="author-dropdown-panel">
          {items.map((item) => (
            <label key={item.value} className="field-checkbox">
              <input
                type="checkbox"
                checked={selected.includes(item.value)}
                onChange={() => onToggle(item.value)}
              />
              {item.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Search() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get("q") || "";
  const initialPage = parseInt(searchParams.get("page"), 10) || 1;

  const [query, setQuery] = useState(initialQ);
  const [fields, setFields] = useState(loadFields);
  const [selectedAuthors, setSelectedAuthors] = useState(loadSelectedAuthors);
  const [selectedLanguages, setSelectedLanguages] = useState(loadSelectedLanguages);
  const [authorsList, setAuthorsList] = useState([]);
  const [languagesList, setLanguagesList] = useState([]);
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(initialPage);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef(null);
  const initialLoad = useRef(true);

  useEffect(() => {
    fetch("/api/authors")
      .then((r) => r.json())
      .then((data) => setAuthorsList(data.authors.map((a) => ({ value: a.slug, label: a.name }))));
    fetch("/api/languages")
      .then((r) => r.json())
      .then((data) => setLanguagesList(data.languages.map((l) => ({ value: l, label: l }))));
  }, []);

  function updateUrl(q, p) {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q);
    if (p > 1) params.set("page", String(p));
    setSearchParams(params, { replace: true });
  }

  function toggleField(key) {
    setFields((prev) => {
      const next = prev.includes(key) ? prev.filter((f) => f !== key) : [...prev, key];
      localStorage.setItem("searchFields", JSON.stringify(next));
      return next;
    });
  }

  function toggleAuthor(slug) {
    setSelectedAuthors((prev) => {
      const next = prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug];
      localStorage.setItem("searchAuthors", JSON.stringify(next));
      return next;
    });
  }

  function toggleLanguage(lang) {
    setSelectedLanguages((prev) => {
      const next = prev.includes(lang) ? prev.filter((s) => s !== lang) : [...prev, lang];
      localStorage.setItem("searchLanguages", JSON.stringify(next));
      return next;
    });
  }

  function doSearch(q, p = 1, f = fields, authors = selectedAuthors, languages = selectedLanguages) {
    if (!q.trim() && authors.length === 0 && languages.length === 0) {
      setResults([]);
      setTotal(0);
      setPage(1);
      setPages(1);
      updateUrl("", 1);
      return;
    }
    setLoading(true);
    updateUrl(q, p);
    const params = new URLSearchParams();
    params.set("q", q);
    params.set("page", p);
    f.forEach((field) => params.append("fields", field));
    authors.forEach((slug) => params.append("author", slug));
    languages.forEach((lang) => params.append("language", lang));
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
    if (initialLoad.current) {
      initialLoad.current = false;
      doSearch(query, initialPage, fields, selectedAuthors, selectedLanguages);
      return;
    }
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      doSearch(query, 1, fields, selectedAuthors, selectedLanguages);
    }, 300);
    return () => clearTimeout(timerRef.current);
  }, [query, fields, selectedAuthors, selectedLanguages]);

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
        <CheckboxDropdown
          label="Autores"
          items={authorsList}
          selected={selectedAuthors}
          onToggle={toggleAuthor}
        />
        <CheckboxDropdown
          label="Idioma"
          pluralLabel="Idiomas"
          items={languagesList}
          selected={selectedLanguages}
          onToggle={toggleLanguage}
        />
      </div>

      {loading && <p className="status">Buscando…</p>}

      {!loading && (query.trim() || selectedAuthors.length > 0 || selectedLanguages.length > 0) && (
        <p className="status">
          {total} resultado{total !== 1 ? "s" : ""} encontrado
          {total !== 1 ? "s" : ""}
        </p>
      )}

      <div className="results">
        {results.map((r) => (
          <div key={r.id} className="result-card">
            <h2>
              <Link to={`/palestras/${r.slug}${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`}>
                {highlightText(r.title, words)}
              </Link>
              <a
                href={r.url}
                target="_blank"
                rel="noopener noreferrer"
                className="external-link"
                title="Abrir no site original"
              >
                ↗
              </a>
            </h2>
            {r.authors.length > 0 && (
              <div className="authors-row">
                {r.authors.map((a, i) => (
                  <span key={i} className="author-chip">
                    {a.photo_url
                      ? <img src={a.photo_url} alt={a.name} className="author-avatar" />
                      : <span className="author-avatar author-initial">{a.name[0]}</span>
                    }
                    {highlightText(a.name, words)}
                  </span>
                ))}
              </div>
            )}
            {(r.categories || r.tags || r.language) && (
              <p className="meta tags">
                {highlightText(
                  [r.language, r.categories, r.tags].filter(Boolean).join(" · "),
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
