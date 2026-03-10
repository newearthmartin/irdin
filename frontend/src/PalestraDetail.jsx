import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import "./PalestraDetail.css";
import { highlightText } from "./textUtils.jsx";

function parseTimecoded(text) {
  if (!text) return [];
  return text.split("\n").filter(Boolean).map((line) => {
    const match = line.match(/^\[(\d{2}):(\d{2}):(\d{2})\]\s*(.*)/);
    if (!match) return { seconds: null, text: line };
    const [, h, m, s] = match;
    return {
      seconds: parseInt(h) * 3600 + parseInt(m) * 60 + parseInt(s),
      timestamp: `${h}:${m}:${s}`,
      text: match[4],
    };
  });
}

const audioPlayers = new Set();

function pauseOtherPlayers(current) {
  for (const audio of audioPlayers) {
    if (audio !== current && !audio.paused) {
      audio.pause();
    }
  }
}

function TrackPlayer({ track, words, initialTime, onSeek, getShareUrl, onCopy }) {
  const audioRef = useRef(null);
  const trackSectionRef = useRef(null);
  const transcriptionRef = useRef(null);
  const lineElemsRef = useRef([]);
  const [copiedIndex, setCopiedIndex] = useState(null);

  function copyShareLink(e, seconds, index) {
    e.stopPropagation();
    const url = getShareUrl(track.id, seconds);
    navigator.clipboard.writeText(url).then(() => {
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex(null), 1500);
      if (onCopy) onCopy();
    });
  }

  const lines = parseTimecoded(track.transcription_timecoded);
  const linesRef = useRef(lines);
  linesRef.current = lines;

  const [activeIndex, setActiveIndex] = useState(() => {
    if (initialTime == null) return -1;
    let active = -1;
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].seconds !== null && lines[i].seconds <= initialTime) active = i;
    }
    return active;
  });

  const initialTimeRef = useRef(initialTime);

  // Scroll page to the highlighted line on initial load
  useEffect(() => {
    if (initialTime == null) return;
    const lineEl = activeIndex >= 0 ? lineElemsRef.current[activeIndex] : null;
    const target = lineEl || trackSectionRef.current;
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep active line visible within the transcript box during playback
  useEffect(() => {
    if (activeIndex < 0) return;
    const container = transcriptionRef.current;
    const lineEl = lineElemsRef.current[activeIndex];
    if (!container || !lineEl) return;
    const cRect = container.getBoundingClientRect();
    const lRect = lineEl.getBoundingClientRect();
    const nextEl = lineElemsRef.current[activeIndex + 1];
    const nextRect = nextEl ? nextEl.getBoundingClientRect() : null;
    if (nextRect && nextRect.bottom > cRect.bottom) {
      // Next sentence is out of view — scroll current to top
      container.scrollTo({ top: container.scrollTop + lRect.top - cRect.top, behavior: "smooth" });
    } else if (lRect.top < cRect.top) {
      // Current sentence scrolled above — bring it back
      container.scrollTo({ top: container.scrollTop - (cRect.top - lRect.top), behavior: "smooth" });
    }
  }, [activeIndex]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audioPlayers.add(audio);
    function onPlay() {
      pauseOtherPlayers(audio);
    }
    function onTimeUpdate() {
      const t = audio.currentTime;
      const ls = linesRef.current;
      let active = -1;
      for (let i = 0; i < ls.length; i++) {
        if (ls[i].seconds !== null && ls[i].seconds <= t) {
          active = i;
        }
      }
      setActiveIndex((prev) => (prev !== active ? active : prev));
    }
    function onLoaded() {
      if (initialTimeRef.current != null) {
        audio.currentTime = initialTimeRef.current;
        initialTimeRef.current = null;
      }
    }
    audio.addEventListener("play", onPlay);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("loadedmetadata", onLoaded);
    return () => {
      audioPlayers.delete(audio);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("loadedmetadata", onLoaded);
    };
  }, []);

  function seekTo(seconds) {
    const audio = audioRef.current;
    if (!audio || seconds === null) return;
    audio.currentTime = seconds;
    if (audio.paused) {
      audio.play();
    }
    if (onSeek) onSeek(track.id, seconds);
  }

  return (
    <div className="track-section" ref={trackSectionRef}>
      <h3 className="track-name">{track.name}</h3>
      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={track.audio_url}
        className="track-audio"
      />
      {lines.length > 0 && (
        <div className="transcription" ref={transcriptionRef}>
          {lines.map((line, i) => (
            <div
              key={i}
              ref={(el) => { lineElemsRef.current[i] = el; }}
              className={`transcription-line${i === activeIndex ? " active" : ""}${line.seconds !== null ? " clickable" : ""}`}
              onClick={() => seekTo(line.seconds)}
            >
              {line.timestamp && (
                <span className="timestamp">{line.timestamp}</span>
              )}
              <span className="line-text">
                {highlightText(line.text, words)}
              </span>
              {line.seconds !== null && (
                <button
                  className={`share-btn${copiedIndex === i ? " copied" : ""}`}
                  title="Copiar link"
                  onClick={(e) => copyShareLink(e, line.seconds, i)}
                >
                  {copiedIndex === i ? "✓" : (
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                    </svg>
                  )}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PalestraDetail({ toggle }) {
  const { slug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") || "";
  const words = q.trim().split(/\s+/).filter(Boolean);
  const initialTrackId = searchParams.get("track") ? parseInt(searchParams.get("track"), 10) : null;
  const initialTime = searchParams.get("t") ? parseFloat(searchParams.get("t")) : null;

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(false);
  const toastTimerRef = useRef(null);

  function showToast() {
    clearTimeout(toastTimerRef.current);
    setToast(true);
    toastTimerRef.current = setTimeout(() => setToast(false), 2500);
  }

  const getShareUrl = useCallback((trackId, seconds) => {
    const params = new URLSearchParams();
    if (data && data.tracks.length > 1) params.set("track", String(trackId));
    params.set("t", String(Math.floor(seconds)));
    return `${window.location.origin}/palestras/${slug}?${params}`;
  }, [data, slug]);

  const handleSeek = useCallback((trackId, seconds) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (data && data.tracks.length > 1) {
        next.set("track", String(trackId));
      } else {
        next.delete("track");
      }
      next.set("t", String(Math.floor(seconds)));
      return next;
    }, { replace: true });
  }, [setSearchParams, data]);

  useEffect(() => {
    fetch(`/api/palestras/${slug}`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found");
        return r.json();
      })
      .then(setData)
      .catch(() => setError("Palestra não encontrada."));
  }, [slug]);

  if (error) {
    return (
      <div className="container">
        <p className="status">{error}</p>
        <Link to="/" className="back-link">← Voltar à pesquisa</Link>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="container">
        <p className="status">Carregando…</p>
      </div>
    );
  }

  return (
    <>
    <div className="container detail-page">
      {toggle}
      <Link to={q ? `/?q=${encodeURIComponent(q)}` : "/"} className="back-link">
        ← Voltar à pesquisa
      </Link>

      <h1>{data.title}</h1>

      {data.authors.length > 0 && (
        <div className="authors-row">
          {data.authors.map((a, i) => (
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

      {(data.categories || data.tags || data.language) && (
        <p className="meta tags">
          {[data.language, data.categories, data.tags].filter(Boolean).join(" · ")}
        </p>
      )}

      {data.description && (
        <div className="detail-description">
          <p>{highlightText(data.description, words)}</p>
        </div>
      )}

      <div className="links-row">
        <a
          href={data.url}
          target="_blank"
          rel="noopener noreferrer"
          className="original-link"
        >
          Ver no site original ↗
        </a>
        {q && (
          <>
            {" — "}
            <Link to={`/palestras/${slug}`} className="original-link">
              Remover destaque de "{q}" ×
            </Link>
          </>
        )}
      </div>

      {data.tracks.length > 0 && (
        <div className="tracks">
          {data.tracks.map((track) => (
            <TrackPlayer
              key={track.id}
              track={track}
              words={words}
              initialTime={
                (track.id === initialTrackId || (initialTrackId === null && data.tracks.length === 1))
                  ? initialTime
                  : null
              }
              onSeek={handleSeek}
              getShareUrl={getShareUrl}
              onCopy={showToast}
            />
          ))}
        </div>
      )}
    </div>

    {toast && (
      <div className="toast">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{marginRight: "0.4rem", verticalAlign: "middle"}}>
          <rect x="9" y="2" width="6" height="4" rx="1"/>
          <path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2"/>
        </svg>
        Link copiado para a área de transferência
      </div>
    )}
    </>
  );
}
