export interface Article {
  id: string;
  title: string;
  authors?: string[];
  author?: string;
  journal?: string;
  doi?: string;
  doi_url?: string;
  url?: string;
  detail_href?: string;
  abstract?: string;
  full_abstract?: string;
  snippet?: string;
  published_date?: string;
  pub_date?: string;
  first_seen_date?: string;
  first_seen_time?: string;
  first_seen_batch_id?: string;
  last_seen_date?: string;
  last_seen_time?: string;
  last_seen_batch_id?: string;
  seen_batch_ids?: string[];
  crawl_date?: string;
  crawl_time?: string;
  crawl_batch_id?: string;
  source?: string;
  keywords?: string[];
  tags?: string[];
  is_new_in_batch?: boolean;
  abstract_source?: string;
  journal_slug?: string;
  search_blob?: string;
  crawl_history?: Array<{ batch_id: string; crawl_time?: string; crawl_date?: string; rank_in_batch?: number }>;
}

export interface BatchPayload {
  batch_id: string;
  crawl_time?: string;
  crawl_date?: string;
  article_count?: number;
  total_observed_articles?: number;
  new_articles_count?: number;
  seen_again_count?: number;
  journal_count?: number;
  journals?: string[];
  articles: Article[];
  new_articles?: Article[];
  seen_again_articles?: Article[];
}

export interface ArchiveSummary {
  latest_batch_id: string;
  latest_crawl_time?: string;
  latest_crawl_date?: string;
  latest_batch_article_count?: number;
  latest_batch_journal_count?: number;
  latest_batch_new_article_count?: number;
  latest_batch_seen_again_count?: number;
  total_articles: number;
  total_batches: number;
  journals?: Array<{ journal?: string; name?: string; article_count: number; latest_crawl_date?: string } | string>;
  dates?: Array<{ date: string; batch_count: number; article_count: number; journals?: string[] }>;
  sources?: Array<{ source: string; article_count: number } | string>;
}
