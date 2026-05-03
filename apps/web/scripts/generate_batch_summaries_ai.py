#!/usr/bin/env python3
"""
Generate AI summaries for batches with new articles using LLM.
Summaries highlight key innovations and research contributions in Chinese.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import anthropic

# Paths
WORKSPACE = Path("/root/.openclaw/workspace/mixz")
BATCHES_DIR = WORKSPACE / "site/data/articles/batches"
ARTICLES_INDEX = WORKSPACE / "site/data/articles/articles_index.json"
SUMMARIES_FILE = WORKSPACE / "site/data/articles/batch_summaries.json"

# Initialize Anthropic client
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

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

def generate_summary_with_claude(articles):
    """Generate a Chinese summary using Claude."""
    if not articles:
        return None
    
    # Prepare article information
    articles_info = []
    for i, article in enumerate(articles[:10], 1):  # Limit to 10 articles
        if not article:
            continue
        title = article.get('title', 'Unknown')
        abstract = article.get('abstract', '')[:500]  # Limit abstract length
        journal = article.get('journal', 'Unknown')
        
        articles_info.append({
            'title': title,
            'journal': journal,
            'abstract': abstract
        })
    
    if not articles_info:
        return None
    
    # Create prompt
    prompt = f"""请为这批生物医学成像领域的新文章生成一段简洁的中文总结（80-120字）。

要求：
1. 突出研究的创新点和技术突破
2. 用通俗易懂的语言描述研究成果
3. 如果有多篇文章，概括共同的研究主题或趋势
4. 语气专业但不失亲和力
5. 不要使用"本批次"、"收录"等元数据描述，直接描述研究内容

文章列表（共 {len(articles_info)} 篇）：

"""
    
    for i, article in enumerate(articles_info, 1):
        prompt += f"{i}. 《{article['title']}》\n"
        prompt += f"   期刊：{article['journal']}\n"
        if article['abstract']:
            prompt += f"   摘要：{article['abstract']}\n"
        prompt += "\n"
    
    try:
        response = client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=300,
            temperature=0.7,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        summary = response.content[0].text.strip()
        return summary
    
    except Exception as e:
        print(f"Error calling Claude API: {e}", file=sys.stderr)
        return None

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
    for batch_file in batch_files[:20]:  # Process recent 20 batches
        batch_id = batch_file.stem
        
        # Skip if already has summary
        if batch_id in summaries:
            print(f"⊙ {batch_id}: Already has summary")
            continue
        
        try:
            batch = load_batch(batch_file)
            new_count = batch.get('new_articles_count', 0)
            
            if new_count == 0:
                print(f"○ {batch_id}: No new articles")
                continue
            
            # Get article IDs from new_articles
            new_article_ids = []
            if 'new_articles' in batch and batch['new_articles']:
                new_article_ids = [a.get('id') for a in batch['new_articles'] if a and a.get('id')]
            
            if not new_article_ids:
                print(f"○ {batch_id}: No article IDs found")
                continue
            
            # Find full article details
            articles = find_article_details(articles_index, new_article_ids)
            articles = [a for a in articles if a]  # Filter out None
            
            if not articles:
                print(f"○ {batch_id}: No article details found")
                continue
            
            print(f"⟳ {batch_id}: Generating summary for {len(articles)} articles...")
            
            # Generate summary with Claude
            summary = generate_summary_with_claude(articles)
            
            if summary:
                summaries[batch_id] = {
                    'batch_id': batch_id,
                    'summary': summary,
                    'article_count': len(articles),
                    'generated_at': datetime.now().isoformat()
                }
                updated_count += 1
                print(f"✓ {batch_id}: {summary[:60]}...")
            else:
                print(f"✗ {batch_id}: Failed to generate summary")
        
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
