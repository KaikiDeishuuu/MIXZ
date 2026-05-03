function parseBatchId(batchId: string): string {
  const normalized = batchId.trim().replaceAll('_', ' ');
  const match = normalized.match(/^(\d{4}-\d{2}-\d{2})\s+(.+)$/);

  if (!match) {
    return normalized;
  }

  const [, datePart, rawTimePart] = match;
  const compactTime = rawTimePart.replace(/\s+/g, '');

  if (/^\d{6}$/.test(compactTime)) {
    return `${datePart} ${compactTime.slice(0, 2)}:${compactTime.slice(2, 4)}:${compactTime.slice(4, 6)}`;
  }

  if (/^\d{4}$/.test(compactTime)) {
    return `${datePart} ${compactTime.slice(0, 2)}:${compactTime.slice(2, 4)}`;
  }

  return `${datePart} ${rawTimePart.trim()}`;
}

export function formatBatchLabel(batchId: string): string {
  return parseBatchId(batchId);
}

export function formatBatchShort(batchId: string): string {
  const normalized = parseBatchId(batchId);
  const [datePart, timePart] = normalized.split(' ');

  if (!datePart) {
    return normalized;
  }

  if (!timePart) {
    return datePart;
  }

  const [, month, day] = datePart.split('-');
  return month && day ? `${month}-${day} ${timePart.slice(0, 5)}` : normalized;
}

export function getRelativeTime(value?: string): string {
  if (!value) {
    return 'Unknown';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  const diffMs = parsed.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60000);
  const diffHours = Math.round(diffMs / 3600000);
  const diffDays = Math.round(diffMs / 86400000);

  const formatter = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' });

  if (Math.abs(diffMinutes) < 60) {
    return formatter.format(diffMinutes, 'minute');
  }

  if (Math.abs(diffHours) < 24) {
    return formatter.format(diffHours, 'hour');
  }

  return formatter.format(diffDays, 'day');
}
