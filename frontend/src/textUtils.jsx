function stripAccents(s) {
  return s.normalize("NFD").replace(/\p{Mn}/gu, "");
}

export function highlightText(text, words) {
  if (!words || !words.length || !text) return text;
  // Build patterns that match base chars optionally followed by combining diacritic marks,
  // so "jesus" matches "Jesús" and vice versa.
  const patterns = words.map((w) =>
    [...stripAccents(w)]
      .map((c) => c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\p{Mn}*")
      .join("")
  );
  const regex = new RegExp(`(${patterns.join("|")})`, "giu");
  const textNFD = text.normalize("NFD");
  const parts = [];
  let last = 0;
  let match;
  while ((match = regex.exec(textNFD)) !== null) {
    if (match.index > last)
      parts.push(textNFD.slice(last, match.index).normalize("NFC"));
    parts.push(
      <mark key={match.index}>
        {textNFD.slice(match.index, match.index + match[0].length).normalize("NFC")}
      </mark>
    );
    last = match.index + match[0].length;
  }
  if (last < textNFD.length) parts.push(textNFD.slice(last).normalize("NFC"));
  return parts.length ? parts : text;
}

export function snippetAround(text, words, maxLen = 300) {
  if (!text) return "";
  if (text.length <= maxLen) return text;
  const normalized = stripAccents(text.toLowerCase());
  let bestIdx = 0;
  for (const w of words) {
    const idx = normalized.indexOf(stripAccents(w.toLowerCase()));
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
