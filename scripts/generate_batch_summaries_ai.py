#!/usr/bin/env python3
"""
Generate AI summaries for batches with new articles using LLM.
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
    with open(ARTICLES_INDEX, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_batch(batch_file):
    with open(batch_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def find_article_details(articles_index, article_ids):
    id_to_article = {a['id']: a for a in articles_index}
    return [id_to_article.get(aid) for aid in article_ids if aid in id_to_article]

def generate_summary_with_claude(articles):
    if not articles:
        return None
    
    articles_info = []
    for article in articles[:10]:
        if not article:
            continue
        articles_info.append({
            'title': article.get('title', 'Unknown'),
            'journal': article.get('journal', 'Unknown'),
            'abstract': article.get('abstract', '')[:500]
        })
    
    if not articles_info:
        return None
    
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
        prompt += f"{i}. 《{article['title']}》\n   期刊：{article['journal']}\n"
        if article['abstract']:
            prompt += f"   摘要：{article['abstract']}\n"
        prompt += "\n"
    
    try:
        response = client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=300,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None

def main():
    print("Loading articles...")
    articles_index = load_articles_index()
    
    summaries = {}
    if SUMMARIES_FILE.exists():
        with open(SUMMARIES_FILE, 'r', encoding='utf-8') as f:
            summaries = json.load(f)
    
    batch_files = sorted(BATCHES_DIR.glob("*.json"), reverse=True)
    updated = 0
    
    for batch_file in batch_files[:20]:
        batch_id = batch_file.stem
        
        if batch_id in summaries:
            print(f"⊙ {batch_id}: Skip")
            continue
        
        try:
            batch = load_batch(batch_file)
            if batch.get('new_articles_count', 0) == 0:
                continue
            
            article_ids = [a.get('id') for a in batch.get('new_articles', []) if a and a.get('id')]
            if not article_ids:
                continue
            
            articles = [a for a in find_article_details(articles_index, article_ids) if a]
            if not articles:
                continue
            
            print(f"⟳ {batch_id}: Generating...")
            summary = generate_summary_with_claude(articles)
            
            if summary:
                summaries[batch_id] = {
                    'batch_id': batch_id,
                    'summary': summary,
                    'article_count': len(articles),
                    'generated_at': datetime.now().isoformat()
                }
                updated += 1
                print(f"✓ {batch_id}: {summary[:50]}...")
        except Exception as e:
            print(f"✗ {batch_id}: {e}")
    
    with open(SUMMARIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Generated {updated} new summaries (Total: {len(summaries)})")

if __name__ == '__main__':
    main()
