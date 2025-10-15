export function toSeconds(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return 0;

  const parts = value.trim().split(':').map((p) => p.trim());
  if (parts.some((p) => p === '' || isNaN(Number(p)))) return 0;

  // Support s, m:s, h:m:s
  const nums = parts.map((p) => Number(p));
  if (nums.length === 1) return nums[0];
  if (nums.length === 2) {
    const [m, s] = nums;
    return m * 60 + s;
  }
  if (nums.length === 3) {
    const [h, m, s] = nums;
    return h * 3600 + m * 60 + s;
  }
  // Longer forms not supported; fall back to 0
  return 0;
}

export function formatTime(total) {
  if (!Number.isFinite(total) || total < 0) return '0:00';
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = Math.floor(total % 60);
  const mm = hours > 0 ? String(minutes).padStart(2, '0') : String(minutes);
  const ss = String(seconds).padStart(2, '0');
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}

