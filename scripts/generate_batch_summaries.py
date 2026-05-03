#!/usr/bin/env python3
"""
Generate AI summaries for batches with new articles.
Summaries highlight key innovations and research contributions.
"""

import json
import os
from pathlib import Path
from datetime import datetime

# Paths
WORKSPACE = Path("/root/.openclaw/workspace/mixz")
BATCHES_DIR = WORKSPACE / "site/data/articles/batches"
ARTICLES_INDEX = WORKSPACE / "site/data/articles/articles_index.json"
SUMMARIES_FILE = WORKSPACE / "site/data/articles/batch_summaries.json"

def load_articles_index():
    """Load the full articles index."""
    with open(ARTICLES_INDEX, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_batch(batch_file):
    """Load a batch JSON file."""
    with open(batch_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_article_details(articles_index, article_ids):
    """Find full article details from the index."""
    id_to_article = {a['id']: a for a in articles_index}
    return [id_to_article.get(aid) for aid in article_ids if aid in id_to_article]

def generate_summary_prompt(articles):
    """Generate a prompt for AI to summarize the batch."""
    articles_text = []
    for i, article in enumerate(articles[:10], 1):  # Limit to 10 articles
        if not article:
            continue
        title = article.get('title', 'Unknown')
        abstract = article.get('abstract', '')
        journal = article.get('journal', 'Unknown')
        
        articles_text.append(f"{i}. {title}\n   期刊: {journal}\n   摘要: {abstract[:300]}...")
    
    return "\n\n".join(articles_text)

def generate_summary_with_ai(articles):
    """
    Generate a Chinese summary of the batch highlighting innovations.
    This is a placeholder - you should call your actual AI model here.
    """
    if not articles:
        return None
    
    # For now, return a template summary
    # In production, you would call an LLM API here
    count = len(articles)
    journals = list(set(a.get('journal', 'Unknown') for a in articles if a))
    
    # Simple template-based summary
    summary = f"本批次收录了 {count} 篇新文章，"
    
    if len(journals) == 1:
        summary += f"全部来自 {journals[0]}。"
    else:
        summary += f"涵盖 {', '.join(journals[:3])} 等 {len(journals)} 个期刊。"
    
    # Add research themes (simplified)
    keywords = []
    for article in articles[:5]:
        if article and article.get('title'):
            title = article['title'].lower()
            if 'imaging' in title or '成像' in title:
                keywords.append('生物成像')
            if 'quantum' in title or '量子' in title:
                keywords.append('量子技术')
            if 'neural' in title or 'brain' in title or '神经' in title:
                keywords.append('神经科学')
            if 'cancer' in title or '肿瘤' in title:
                keywords.append('肿瘤研究')
    
    if keywords:
        unique_keywords = list(set(keywords))
        summary += f" 研究主题包括{' 、'.join(unique_keywords[:3])}等领域的最新进展。"
    
    return summary

def main():
    """Main function to generate summaries for all batches."""
    print("Loading articles index...")
    articles_index = load_articles_index()
    
    print(f"Found {len(articles_index)} articles in index")
    
    # Load existing summaries if any
    summaries = {}
    if SUMMARIES_FILE.exists():
        with open(SUMMARIES_FILE, 'r', encoding='utf-8') as f:
            summaries = json.load(f)
    
    # Process each batch
    batch_files = sorted(BATCHES_DIR.glob("*.json"), reverse=True)
    print(f"Processing {len(batch_files)} batches...")
    
    updated_count = 0
    for batch_file in batch_files[:50]:  # Process recent 50 batches
        batch_id = batch_file.stem
        
        # Skip if already has summary
        if batch_id in summaries:
            continue
        
        try:
            batch = load_batch(batch_file)
            new_count = batch.get('new_articles_count', 0)
            
            if new_count == 0:
                continue
            
            # Get article IDs from new_articles
            new_article_ids = []
            if 'new_articles' in batch and batch['new_articles']:
                new_article_ids = [a.get('id') for a in batch['new_articles'] if a and a.get('id')]
            
            if not new_article_ids:
                continue
            
            # Find full article details
            articles = find_article_details(articles_index, new_article_ids)
            articles = [a for a in articles if a]  # Filter out None
            
            if not articles:
                continue
            
            # Generate summary
            summary = generate_summary_with_ai(articles)
            
            if summary:
                summaries[batch_id] = {
                    'batch_id': batch_id,
                    'summary': summary,
                    'article_count': len(articles),
                    'generated_at': datetime.now().isoformat()
                }
                updated_count += 1
                print(f"✓ {batch_id}: {summary[:60]}...")
        
        except Exception as e:
            print(f"✗ {batch_id}: {e}")
            continue
    
    # Save summaries
    with open(SUMMARIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Generated {updated_count} new summaries")
    print(f"📝 Total summaries: {len(summaries)}")
    print(f"💾 Saved to: {SUMMARIES_FILE}")

if __name__ == '__main__':
    main()
