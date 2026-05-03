import articlesIndex from '../../../../site/data/articles/articles_index.json';
import archiveSummary from '../../../../site/data/articles/archive_summary.json';
import batchSummaries from '../../../../site/data/articles/batch_summaries.json';
import type { Article, ArchiveSummary, BatchPayload } from '../types';

export const articles = articlesIndex as Article[];
export const summary = archiveSummary as unknown as ArchiveSummary;
export const summaries = batchSummaries as Record<string, { batch_id: string; summary: string; article_count: number; generated_at: string }>;

const latestId = summary.latest_batch_id;
const batchModules = import.meta.glob('../../../../site/data/articles/batches/*.json', { eager: true, import: 'default' });

export function normalizeBatchId(value?: string): string {
  return String(value || '').trim().replaceAll('_', ' ').replace(/\s+/g, ' ');
}

const rawBatches = Object.values(batchModules)
  .map((value) => value as BatchPayload)
  .sort((a, b) => String(b.crawl_time || b.batch_id).localeCompare(String(a.crawl_time || a.batch_id)));

const seenBatchKeys = new Set<string>();
export const batches = rawBatches.filter((batch) => {
  const key = normalizeBatchId(batch.batch_id);
  if (seenBatchKeys.has(key)) {
    return false;
  }
  seenBatchKeys.add(key);
  return true;
});

export const latest = (batches.find((batch) => normalizeBatchId(batch.batch_id) === normalizeBatchId(latestId)) || batches[0]) as BatchPayload;

/**
 * Get summary for a batch, or find the most recent batch with a summary
 */
export function getBatchSummary(batchId?: string): { batch_id: string; summary: string; article_count: number } | null {
  // If batch ID provided and has summary, return it
  if (batchId && summaries[batchId]) {
    return summaries[batchId];
  }
  
  // Otherwise find the most recent batch with a summary
  for (const batch of batches) {
    if (summaries[batch.batch_id]) {
      return summaries[batch.batch_id];
    }
  }
  
  return null;
}

export function archiveJournalHref(journal: string): string {
  return `/archive?journal=${encodeURIComponent(journal)}`;
}

export function archiveBatchHref(batchId: string): string {
  return `/archive?batch=${encodeURIComponent(batchId)}`;
}

export function articleBatchIds(article: Article): string[] {
  const rawIds = [
    ...(article.seen_batch_ids || []),
    article.first_seen_batch_id,
    article.last_seen_batch_id,
    article.crawl_batch_id,
  ].filter(Boolean) as string[];

  return Array.from(new Set(rawIds.flatMap((id) => [id, normalizeBatchId(id)])));
}

export function paperSlug(article: Article): string {
  return String(article.detail_href || article.doi || article.id)
    .replace(/^\/papers\//, '')
    .replace(/\.html$/, '')
    .replaceAll('/', '-');
}

export function formatDate(value?: string): string {
  if (!value || value === 'unknown') return 'Unknown';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeZone: 'Asia/Shanghai' }).format(d);
}

export function formatDateTime(value?: string): string {
  if (!value || value === 'unknown') return 'Unknown';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(d);
}

export function journalList(): Array<{ name: string; count: number }> {
  const map = new Map<string, number>();
  for (const article of articles) {
    const name = article.journal || 'Unknown';
    map.set(name, (map.get(name) || 0) + 1);
  }
  return [...map.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

export function findArticleBySlug(slug: string): Article | undefined {
  return articles.find((article) => paperSlug(article) === slug || article.id === slug || article.doi === slug);
}
