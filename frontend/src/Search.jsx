import { useState, useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { highlightText, snippetAround } from "./textUtils.jsx";
import ThemeToggle from "./ThemeToggle.jsx";

const ALL_FIELDS = [
  { key: "title", label: "Título" },
  { key: "description", label: "Descrição" },
  { key: "transcriptions", label: "Transcrição" },
  { key: "tags", label: "Tags" },
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

function loadSelectedCategories() {
  try {
    const stored = localStorage.getItem("searchCategories");
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
  const initialFields = searchParams.getAll("fields").length > 0
    ? searchParams.getAll("fields")
    : loadFields();
  const initialAuthors = searchParams.getAll("author").length > 0
    ? searchParams.getAll("author")
    : loadSelectedAuthors();
  const initialLanguages = searchParams.getAll("language").length > 0
    ? searchParams.getAll("language")
    : loadSelectedLanguages();
  const initialCategories = searchParams.getAll("category").length > 0
    ? searchParams.getAll("category")
    : loadSelectedCategories();

  const [query, setQuery] = useState(initialQ);
  const [fields, setFields] = useState(initialFields);
  const [selectedAuthors, setSelectedAuthors] = useState(initialAuthors);
  const [selectedLanguages, setSelectedLanguages] = useState(initialLanguages);
  const [selectedCategories, setSelectedCategories] = useState(initialCategories);
  const [authorsList, setAuthorsList] = useState([]);
  const [languagesList, setLanguagesList] = useState([]);
  const [categoriesList, setCategoriesList] = useState([]);
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
    fetch("/api/categories")
      .then((r) => r.json())
      .then((data) => setCategoriesList(data.categories.map((c) => ({ value: c, label: c }))));
  }, []);

  function updateUrl(q, p, f, authors, languages, categories) {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q);
    if (p > 1) params.set("page", String(p));
    f.forEach((field) => params.append("fields", field));
    authors.forEach((slug) => params.append("author", slug));
    languages.forEach((lang) => params.append("language", lang));
    categories.forEach((c) => params.append("category", c));
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

  function toggleCategory(cat) {
    setSelectedCategories((prev) => {
      const next = prev.includes(cat) ? prev.filter((s) => s !== cat) : [...prev, cat];
      localStorage.setItem("searchCategories", JSON.stringify(next));
      return next;
    });
  }

  function doSearch(q, p = 1, f = fields, authors = selectedAuthors, languages = selectedLanguages, categories = selectedCategories) {
    if (!q.trim() && authors.length === 0 && languages.length === 0 && categories.length === 0) {
      setResults([]);
      setTotal(0);
      setPage(1);
      setPages(1);
      updateUrl("", 1, f, authors, languages, categories);
      return;
    }
    setLoading(true);
    updateUrl(q, p, f, authors, languages, categories);
    const params = new URLSearchParams();
    params.set("q", q);
    params.set("page", p);
    f.forEach((field) => params.append("fields", field));
    authors.forEach((slug) => params.append("author", slug));
    languages.forEach((lang) => params.append("language", lang));
    categories.forEach((c) => params.append("category", c));
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
      doSearch(query, initialPage, fields, selectedAuthors, selectedLanguages, selectedCategories);
      return;
    }
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      doSearch(query, 1, fields, selectedAuthors, selectedLanguages, selectedCategories);
    }, 300);
    return () => clearTimeout(timerRef.current);
  }, [query, fields, selectedAuthors, selectedLanguages, selectedCategories]);

  const words = query.trim().split(/\s+/).filter(Boolean);

  return (
    <>
    <div className="topbar">
      <div className="topbar-inner">
        <span />
      </div>
      <ThemeToggle />
    </div>
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
          label="Autor"
          pluralLabel="Autores"
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
        <CheckboxDropdown
          label="Categoria"
          pluralLabel="Categorias"
          items={categoriesList}
          selected={selectedCategories}
          onToggle={toggleCategory}
        />
      </div>

      {loading && <p className="status">Buscando…</p>}

      {!loading && (query.trim() || selectedAuthors.length > 0 || selectedLanguages.length > 0 || selectedCategories.length > 0) && (
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
                    {a.name}
                  </span>
                ))}
              </div>
            )}
            {(r.categories || r.tags || r.language) && (
              <p className="meta tags">
                {[r.language, r.categories, r.tags].filter(Boolean).join(" · ")}
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
    </>
  );
}
