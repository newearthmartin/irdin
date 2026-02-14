import { useState, useEffect, useRef } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import "./PalestraDetail.css";

function highlightText(text, words) {
  if (!words.length || !text) return text;
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(regex);
  return parts.map((part, i) =>
    regex.test(part) ? <mark key={i}>{part}</mark> : part
  );
}

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

function TrackPlayer({ track, words }) {
  const audioRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const linesRef = useRef([]);
  const lines = parseTimecoded(track.transcription_timecoded);
  linesRef.current = lines;

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
    audio.addEventListener("play", onPlay);
    audio.addEventListener("timeupdate", onTimeUpdate);
    return () => {
      audioPlayers.delete(audio);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("timeupdate", onTimeUpdate);
    };
  }, []);

  function seekTo(seconds) {
    const audio = audioRef.current;
    if (!audio || seconds === null) return;
    audio.currentTime = seconds;
    if (audio.paused) {
      audio.play();
    }
  }

  return (
    <div className="track-section">
      <h3 className="track-name">{track.name}</h3>
      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={track.audio_url}
        className="track-audio"
      />
      {lines.length > 0 && (
        <div className="transcription">
          {lines.map((line, i) => (
            <div
              key={i}
              className={`transcription-line${i === activeIndex ? " active" : ""}${line.seconds !== null ? " clickable" : ""}`}
              onClick={() => seekTo(line.seconds)}
            >
              {line.timestamp && (
                <span className="timestamp">{line.timestamp}</span>
              )}
              <span className="line-text">
                {highlightText(line.text, words)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function PalestraDetail() {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const q = searchParams.get("q") || "";
  const words = q.trim().split(/\s+/).filter(Boolean);

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

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
    <div className="container detail-page">
      <Link to={q ? `/?q=${encodeURIComponent(q)}` : "/"} className="back-link">
        ← Voltar à pesquisa
      </Link>

      <h1>{data.title}</h1>

      {data.authors.length > 0 && (
        <p className="meta authors">{data.authors.join(", ")}</p>
      )}

      {(data.categories || data.tags) && (
        <p className="meta tags">
          {[data.categories, data.tags].filter(Boolean).join(" · ")}
        </p>
      )}

      {data.description && (
        <div className="detail-description">
          <p>{highlightText(data.description, words)}</p>
        </div>
      )}

      <a
        href={data.url}
        target="_blank"
        rel="noopener noreferrer"
        className="original-link"
      >
        Ver no site original ↗
      </a>

      {data.tracks.length > 0 && (
        <div className="tracks">
          {data.tracks.map((track) => (
            <TrackPlayer key={track.id} track={track} words={words} />
          ))}
        </div>
      )}
    </div>
  );
}
