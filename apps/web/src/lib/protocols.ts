import pdotsMarkdown from './protocol-markdown/pdots.txt?raw';
import cellIfMarkdown from './protocol-markdown/cell-if.txt?raw';
import extractionBufferMarkdown from './protocol-markdown/extraction-buffer.txt?raw';

export interface ProtocolItem {
  slug: string;
  eyebrow: string;
  icon: string;
  title: string;
  description: string;
  tags: string[];
  markdown: string;
}

export const protocols: ProtocolItem[] = [
  {
    slug: 'pdots',
    eyebrow: 'Nanoparticle prep',
    icon: '🧪',
    title: 'Pdots Protocol',
    description: 'PFPV/PSMA 体系的制备、Pdots-SA 偶联，以及 UV-Vis / 荧光 / DLS 表征完整流程。',
    tags: ['Pdots', 'PFPV/PSMA', 'Streptavidin', 'UV-Vis', 'DLS'],
    markdown: pdotsMarkdown,
  },
  {
    slug: 'cell-if',
    eyebrow: 'Cell imaging',
    icon: '🔬',
    title: 'Cell IF Protocol',
    description: '细胞培养、复苏、传代、冻存与免疫荧光固定、透化、封闭、抗体孵育、成像完整流程。',
    tags: ['Cell IF', 'Fixation', 'Blocking', 'Imaging'],
    markdown: cellIfMarkdown,
  },
  {
    slug: 'extraction-buffer',
    eyebrow: 'Buffer prep',
    icon: '⚗️',
    title: 'Extraction Buffer Protocol',
    description: 'PIPES / EGTA / MgCl₂ / Triton X-100 提取缓冲液配方、stock 配置、计算和保存条件。',
    tags: ['Buffer', 'PIPES', 'EGTA', 'Triton X-100'],
    markdown: extractionBufferMarkdown,
  },
];
