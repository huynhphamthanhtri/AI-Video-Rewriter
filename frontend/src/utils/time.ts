export function parseSrtTime(value: string): number {
  const [hms, ms] = value.split(',');
  const [h, m, s] = hms.split(':').map(Number);
  return h * 3600 + m * 60 + s + Number(ms) / 1000;
}

export function parseClipTime(value: string): number {
  const [hms, ms] = value.split('.');
  const [h, m, s] = hms.split(':').map(Number);
  return h * 3600 + m * 60 + s + Number(ms) / 1000;
}

export function fmt(seconds: number): string {
  if (!Number.isFinite(seconds)) return '0.0s';
  return `${seconds.toFixed(1)}s`;
}