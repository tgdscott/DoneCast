export function formatMediaDisplayName(raw, clamp = true) {
  try {
    let s = String(raw || "");
    if (typeof raw === "object" && raw) {
      s =
        raw.display_name ||
        raw.original_name ||
        raw.filename ||
        raw.name ||
        raw.id ||
        "";
    }
    s = s.split(/[\\/]/).pop();
    s = s.replace(/\.[a-z0-9]{2,4}$/i, "");
    s = s.replace(/^(?:[a-f0-9]{8,}|[a-f0-9-]{8,})[_-]+/i, "");
    s = s.replace(/[._-]+/g, " ");
    s = s.trim().replace(/\s+/g, " ");
    s = s.toLowerCase();
    if (s.length) s = s[0].toUpperCase() + s.slice(1);

    if (!clamp) return s;

    let count = 0;
    let end = s.length;
    for (let i = 0; i < s.length; i += 1) {
      if (/[a-z0-9]/i.test(s[i])) count += 1;
      if (count >= 25) {
        let j = i + 1;
        while (j < s.length && /[a-z0-9]/i.test(s[j])) j += 1;
        end = j;
        break;
      }
    }
    const clamped = s.slice(0, end);
    return end < s.length ? `${clamped}…` : clamped;
  } catch {
    return String(raw || "");
  }
}
