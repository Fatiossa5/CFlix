// Oynatıcıdaki sınırlama ve ardışık sarma hesabı, DOM'dan bağımsızdır.
export function seekStep(position, duration, direction, previous, now) {
  if (!Number.isFinite(position) || !Number.isFinite(duration) || duration <= 0) return null;
  const sign = direction < 0 ? -1 : 1;
  const target = Math.max(0, Math.min(duration, position + sign * 10));
  const sameBurst = previous && previous.direction === sign && now - previous.at < 900;
  return {target, direction: sign, at: now, total: (sameBurst ? previous.total : 0) + Math.abs(target - position)};
}

export function qualitySources(movie) {
  const sources = [{label: 'Orijinal', src: movie.video, value: 'original'}];
  const seen = new Set();
  for (const variant of movie.qualities || []) {
    if (!/^(360|480|720|1080|1440|2160)p$/.test(variant.label) || !/^\/media\/[a-f0-9]{32}$/.test(variant.src) || seen.has(variant.label)) continue;
    seen.add(variant.label);
    sources.push({...variant, value: variant.label});
  }
  return sources;
}

export function restorePosition(position, duration) {
  return Number.isFinite(duration) && duration > 0 ? Math.max(0, Math.min(position, Math.max(0, duration - .05))) : 0;
}
