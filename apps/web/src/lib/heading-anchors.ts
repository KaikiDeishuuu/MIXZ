export interface Heading { id: string; text: string; level: number; }

function slugifyHeading(text: string, index: number): string {
  const slug = text
    .toLowerCase()
    .normalize('NFKC')
    .replace(/[^\p{Letter}\p{Number}]+/gu, '-')
    .replace(/(^-|-$)/g, '');

  return slug || `section-${index + 1}`;
}

function uniqueSlug(slug: string, counts: Map<string, number>): string {
  const count = counts.get(slug) || 0;
  counts.set(slug, count + 1);
  return count === 0 ? slug : `${slug}-${count + 1}`;
}

export function extractHeadings(markdown: string): Heading[] {
  const matches = markdown.match(/^(#{1,6})\s+(.+)$/gm) || [];
  const counts = new Map<string, number>();

  return matches.map((match, index) => {
    const p = match.split(/^(#+)\s+/);
    const level = p[1].length;
    const text = p[2].trim();
    const id = uniqueSlug(slugifyHeading(text, index), counts);
    return { id, text, level };
  });
}

export function injectHeadingIds(html: string, headings: Heading[]): string {
  let index = 0;

  return html.replace(/<h([1-6])>([\s\S]*?)<\/h\1>/g, (match, level, content) => {
    const heading = headings[index];
    index += 1;

    if (!heading) {
      return match;
    }

    return `<h${level} id="${heading.id}">${content}</h${level}>`;
  });
}
