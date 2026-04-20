#!/usr/bin/env python3
import re
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

TZ = datetime.now().astimezone().tzinfo

POEMS = [
    {"theme":"春景", "title":"苏轼 · 《定风波·莫听穿林打叶声》", "lines":["莫听穿林打叶声，何妨吟啸且徐行。", "竹杖芒鞋轻胜马，谁怕？一蓑烟雨任平生。", "料峭春风吹酒醒，微冷，山头斜照却相迎。", "回首向来萧瑟处，归去，也无风雨也无晴。"]},
    {"theme":"春夜", "title":"晏殊 · 《浣溪沙·一曲新词酒一杯》", "lines":["一曲新词酒一杯，去年天气旧亭台。夕阳西下几时回？", "无可奈何花落去，似曾相识燕归来。小园香径独徘徊。"]},
    {"theme":"夏日", "title":"辛弃疾 · 《西江月·夜行黄沙道中》", "lines":["明月别枝惊鹊，清风半夜鸣蝉。", "稻花香里说丰年，听取蛙声一片。", "七八个星天外，两三点雨山前。", "旧时茅店社林边，路转溪桥忽见。"]},
    {"theme":"夏夜", "title":"秦观 · 《满庭芳·山抹微云》", "lines":["山抹微云，天连衰草，画角声断谯门。", "暂停征棹，聊共引离尊。多少蓬莱旧事，空回首、烟霭纷纷。", "斜阳外，寒鸦万点，流水绕孤村。", "销魂。当此际，香囊暗解，罗带轻分。谩赢得青楼，薄幸名存。", "此去何时见也？襟袖上、空惹啼痕。伤情处，高城望断，灯火已黄昏。"]},
    {"theme":"秋思", "title":"辛弃疾 · 《丑奴儿·书博山道中壁》", "lines":["少年不识愁滋味，爱上层楼。爱上层楼，为赋新词强说愁。", "而今识尽愁滋味，欲说还休。欲说还休，却道天凉好个秋。"]},
    {"theme":"秋夜", "title":"柳永 · 《雨霖铃·寒蝉凄切》", "lines":["寒蝉凄切，对长亭晚，骤雨初歇。都门帐饮无绪，留恋处、兰舟催发。", "执手相看泪眼，竟无语凝噎。念去去、千里烟波，暮霭沉沉楚天阔。", "多情自古伤离别，更那堪、冷落清秋节！", "今宵酒醒何处？杨柳岸、晓风残月。", "此去经年，应是良辰好景虚设。便纵有千种风情，更与何人说？"]},
    {"theme":"冬雪", "title":"苏轼 · 《江城子·乙卯正月二十日夜记梦》", "lines":["十年生死两茫茫，不思量，自难忘。", "千里孤坟，无处话凄凉。", "纵使相逢应不识，尘满面，鬓如霜。", "夜来幽梦忽还乡。小轩窗，正梳妆。", "相顾无言，惟有泪千行。", "料得年年肠断处，明月夜，短松冈。"]},
    {"theme":"冬夜", "title":"姜夔 · 《扬州慢·淮左名都》", "lines":["淮左名都，竹西佳处，解鞍少驻初程。", "过春风十里，尽荠麦青青。", "自胡马窥江去后，废池乔木，犹厌言兵。", "渐黄昏，清角吹寒，都在空城。", "杜郎俊赏，算而今、重到须惊。", "纵豆蔻词工，青楼梦好，难赋深情。", "二十四桥仍在，波心荡、冷月无声。", "念桥边红药，年年知为谁生。"]},
    {"theme":"山水", "title":"王维 · 《终南别业》", "lines":["中岁颇好道，晚家南山陲。", "兴来每独往，胜事空自知。", "行到水穷处，坐看云起时。", "偶然值林叟，谈笑无还期。"]},
    {"theme":"思乡", "title":"苏轼 · 《水调歌头·明月几时有》", "lines":["明月几时有？把酒问青天。", "不知天上宫阙，今夕是何年。", "我欲乘风归去，又恐琼楼玉宇，高处不胜寒。", "起舞弄清影，何似在人间。", "转朱阁，低绮户，照无眠。", "不应有恨，何事长向别时圆？", "人有悲欢离合，月有阴晴圆缺，此事古难全。", "但愿人长久，千里共婵娟。"]},
    {"theme":"思乡", "title":"李商隐 · 《夜雨寄北》", "lines":["君问归期未有期，巴山夜雨涨秋池。", "何当共剪西窗烛，却话巴山夜雨时。"]},
    {"theme":"离别", "title":"欧阳修 · 《蝶恋花·庭院深深深几许》", "lines":["庭院深深深几许，杨柳堆烟，帘幕无重数。", "玉勒雕鞍游冶处，楼高不见章台路。", "雨横风狂三月暮，门掩黄昏，无计留春住。", "泪眼问花花不语，乱红飞过秋千去。"]},
    {"theme":"励志", "title":"李白 · 《行路难（其一）》", "lines":["金樽清酒斗十千，玉盘珍羞直万钱。", "停杯投箸不能食，拔剑四顾心茫然。", "欲渡黄河冰塞川，将登太行雪满山。", "闲来垂钓碧溪上，忽复乘舟梦日边。", "行路难，行路难，多歧路，今安在？", "长风破浪会有时，直挂云帆济沧海。"]},
]

THEME_BY_MONTH = {
    3:"春景", 4:"春夜", 5:"山水",
    6:"夏日", 7:"夏夜", 8:"励志",
    9:"秋思", 10:"秋夜", 11:"思乡",
    12:"冬雪", 1:"冬夜", 2:"春景",
}

WEEKDAY_BOOST = {
    0:"励志", 1:"山水", 2:"思乡", 3:"离别", 4:"秋思", 5:"春景", 6:"夏夜"
}

POET_ERA = {
    "李白": "唐",
    "王维": "唐",
    "李商隐": "唐",
    "苏轼": "宋",
    "辛弃疾": "宋",
    "秦观": "宋",
    "晏殊": "宋",
    "柳永": "宋",
    "姜夔": "宋",
    "欧阳修": "宋",
}

EXCLUDED_COMMON_TITLES = {
    "《静夜思》", "《江雪》", "《小池》"
}


def _is_long_form(poem):
    return len(poem.get("lines", [])) >= 3


def _is_not_too_common(poem):
    t = poem.get("title", "")
    return not any(x in t for x in EXCLUDED_COMMON_TITLES)


def pick_poem(dt: datetime):
    base_theme = THEME_BY_MONTH.get(dt.month, "山水")
    boost = WEEKDAY_BOOST.get(dt.weekday())

    candidates = [p for p in POEMS if p["theme"] in {base_theme, boost} and _is_not_too_common(p)]
    if not candidates:
        candidates = [p for p in POEMS if p["theme"] == base_theme and _is_not_too_common(p)]
    if not candidates:
        candidates = [p for p in POEMS if _is_not_too_common(p)] or POEMS

    long_candidates = [p for p in candidates if _is_long_form(p)]
    pool = long_candidates if long_candidates else candidates

    idx = dt.timetuple().tm_yday % len(pool)
    return pool[idx]


def _format_title_with_era(title: str):
    # input: "李白 · 《行路难（其一）》" -> "唐 · 李白《行路难（其一）》"
    if " · " in title:
        poet, work = title.split(" · ", 1)
    else:
        poet, work = title, ""
    poet = poet.strip()
    work = work.strip()
    era = POET_ERA.get(poet)
    if era:
        return f"{era} · {poet}{work}"
    return f"{poet}{work}" if work else poet


def render_block(poem):
    line_html = "".join([f'<p class="poem-line">{line}</p>' for line in poem["lines"]])
    poet = poem["title"].split(" · ", 1)[0] if " · " in poem["title"] else poem["title"]
    title = poem["title"].split(" · ", 1)[1] if " · " in poem["title"] else poem["title"]
    era = POET_ERA.get(poet)
    meta = f"{era} · {poet}" if era else poet
    return (
        "<!-- POEM_BLOCK_START -->"
        f'<section aria-label="今日诗词" class="poem-card" data-theme="{poem["theme"]}">'
        '<div class="poem-kicker">Daily Verse</div>'
        f'<div class="poem-title">{title}</div>'
        f'<div class="poem-meta">{meta}</div>'
        f'<div class="poem-body">{line_html}</div>'
        f'<div class="poem-footer"><span>诗意与研究笔记同页停留</span><span>Theme · {poem["theme"]}</span></div>'
        '</section>'
        '<!-- POEM_BLOCK_END -->'
    )


def update_index(path: Path, poem):
    s = path.read_text(encoding="utf-8")
    original = s

    # 清理已有诗词块（包含旧版无标记块），确保最终只保留一个
    s = re.sub(r"\s*<!-- POEM_BLOCK_START -->.*?<!-- POEM_BLOCK_END -->", "", s, flags=re.S)
    s = re.sub(r'\s*<section[^>]*class="poem-card"[^>]*>.*?</section>', "", s, flags=re.S)

    soup = BeautifulSoup(s, 'html.parser')
    tabs = soup.find('div', class_='tabs', attrs={'role': 'tablist', 'aria-label': 'Mixz tabs'})
    if not tabs:
        return False

    frag = BeautifulSoup(render_block(poem), 'html.parser')
    tabs.insert_before(frag)
    out = str(soup)
    path.write_text(out, encoding="utf-8")
    return out != original


def main():
    now = datetime.now(TZ)
    poem = pick_poem(now)

    paths = [
        Path('/root/.openclaw/workspace/mixz-site/index.html'),
        Path('/var/www/mixz/index.html'),
    ]
    updated = []
    for p in paths:
        if p.exists():
            updated.append((str(p), update_index(p, poem)))

    print(f"poem updated: {poem['theme']} | {poem['title']} | {now.strftime('%F %T')} | {updated}")


if __name__ == '__main__':
    main()
