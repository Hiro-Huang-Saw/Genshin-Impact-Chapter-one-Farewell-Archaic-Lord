"""
===================================================================================
引号专项赋码工具
===================================================================================

【功能说明】
对中英文文本中的引号进行行内标注赋码，用于语料库标点专项分析。

【赋码标签体系】
  「」  →  <QZH1>  中文单引号（直角引号）
  『』  →  <QZH2>  中文双引号（直角引号）
  ""    →  <QZH3>  中文全角双引号
  ''    →  <QZH4>  中文全角单引号
  ""    →  <QEN1>  英文双引号
  ''    →  <QEN2>  英文单引号（已排除缩写撇号和所有格撇号）

【缩写撇号排除规则】
  规则1：字母 + ' + 字母 → 缩写撇号（如 it's, don't, we've, let's）
  规则2：字母 + s + ' + 非字母 → 所有格撇号（如 Rex Lapis', thieves'）
  规则3：词首 ' + 已知缩写词 → 非正式缩写（如 'em, 'cause, 'bout）
  以上撇号不参与赋码，仅在统计报告中记录排除数量。
  如需保留所有格撇号参与配对，使用 --keep-possessive 参数。

【赋码格式】
  原文：  「璃月港」是璃月的中心。
  赋码：  「<QZH1>璃月港<QZH1>」是璃月的中心。

  原文：  He said "hello" to her.
  赋码：  He said "<QEN1>hello<QEN1>" to her.

【使用方法】
  1. 对单个文件赋码：
     python quote_tagger.py -i 输入文件.txt -o 输出文件.txt

  2. 对目录下所有 .txt 文件批量赋码：
     python quote_tagger.py -i ./目录路径 -o ./输出目录

  3. 同时输出统计报告：
     python quote_tagger.py -i 输入文件.txt -o 输出文件.txt -s 统计报告.txt

  4. 仅生成统计报告不输出赋码文件：
     python quote_tagger.py -i 输入文件.txt --stats-only

【依赖】
  无额外依赖，仅使用 Python 标准库
===================================================================================
"""

import re
import os
import sys
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime


QUOTE_PATTERNS = [
    ("QZH1", "「", "」"),
    ("QZH2", "『", "』"),
    ("QZH3", "\u201c", "\u201d"),
    ("QZH4", "\u2018", "\u2019"),
    ("QEN1", "\"", "\""),
    ("QEN2", "'", "'"),
]

INFORMAL_CONTRACTIONS = frozenset({
    "em", "cause", "bout", "tis", "twas", "til", "till", "twill",
    "twere", "twould", "tisn't", "twasn't", "n",
})

QUOTE_INFO = {
    "QZH1": {"open": "「", "close": "」", "desc": "中文单引号（直角引号）"},
    "QZH2": {"open": "『", "close": "』", "desc": "中文双引号（直角引号）"},
    "QZH3": {"open": "\u201c", "close": "\u201d", "desc": "中文全角双引号"},
    "QZH4": {"open": "\u2018", "close": "\u2019", "desc": "中文全角单引号"},
    "QEN1": {"open": "\"", "close": "\"", "desc": "英文双引号"},
    "QEN2": {"open": "'", "close": "'", "desc": "英文单引号（排除缩写/所有格）"},
}


def is_contraction_apostrophe(text, pos, filter_possessive=True):
    if pos < 0 or pos >= len(text):
        return False
    char = text[pos]
    if char not in ("'", "\u2019"):
        return False
    has_letter_before = pos > 0 and text[pos - 1].isalpha()
    has_letter_after = pos + 1 < len(text) and text[pos + 1].isalpha()

    if has_letter_before and has_letter_after:
        return True

    if filter_possessive and has_letter_before and text[pos - 1].lower() == "s":
        if pos + 1 >= len(text) or not text[pos + 1].isalpha():
            return True

    if not has_letter_before and has_letter_after:
        word_end = pos + 1
        while word_end < len(text) and text[word_end].isalpha():
            word_end += 1
        word_after = text[pos + 1:word_end].lower()
        if word_after in INFORMAL_CONTRACTIONS:
            return True

    return False


def tag_quotes_in_text(text, filter_possessive=True):
    tagged_text = text
    stats = Counter()
    quote_contents = defaultdict(list)
    excluded_contractions = 0
    excluded_possessives = 0

    events = []
    for tag, open_q, close_q in QUOTE_PATTERNS:
        if open_q == close_q:
            pattern = re.compile(re.escape(open_q))
            positions = [m.start() for m in pattern.finditer(text)]

            if tag == "QEN2":
                filtered = []
                for p in positions:
                    if is_contraction_apostrophe(text, p, filter_possessive):
                        if p > 0 and text[p - 1].isalpha() and p + 1 < len(text) and text[p + 1].isalpha():
                            excluded_contractions += 1
                        else:
                            excluded_possessives += 1
                    else:
                        filtered.append(p)
                positions = filtered

            for i in range(0, len(positions) - 1, 2):
                open_pos = positions[i]
                close_pos = positions[i + 1]
                content = text[open_pos + len(open_q):close_pos]
                events.append((open_pos, "open", tag, open_q))
                events.append((close_pos, "close", tag, close_q))
                stats[tag] += 1
                quote_contents[tag].append(content)
        else:
            open_pattern = re.compile(re.escape(open_q))
            close_pattern = re.compile(re.escape(close_q))
            open_positions = [(m.start(), "open", tag, open_q) for m in open_pattern.finditer(text)]
            close_positions = [(m.start(), "close", tag, close_q) for m in close_pattern.finditer(text)]

            if tag == "QZH4":
                close_positions = [
                    (p, pt, pg, pc) for p, pt, pg, pc in close_positions
                    if not is_contraction_apostrophe(text, p, filter_possessive)
                ]

            all_positions = open_positions + close_positions
            all_positions.sort(key=lambda x: x[0])

            stack = []
            for pos, ptype, ptag, char in all_positions:
                if ptype == "open":
                    stack.append((pos, ptag))
                elif ptype == "close" and stack:
                    open_pos, otag = stack.pop()
                    content = text[open_pos + len(open_q):pos]
                    events.append((open_pos, "open", otag, char))
                    events.append((pos, "close", otag, char))
                    stats[otag] += 1
                    quote_contents[otag].append(content)

    events.sort(key=lambda x: x[0])

    for pos, etype, tag, char in reversed(events):
        insert_pos = pos + len(char) if etype == "open" else pos
        tagged_text = tagged_text[:insert_pos] + f"<{tag}>" + tagged_text[insert_pos:]

    return tagged_text, stats, quote_contents, excluded_contractions, excluded_possessives


def process_file(input_path, output_path=None, stats_path=None, filter_possessive=True):
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    tagged_text, stats, quote_contents, excluded_contractions, excluded_possessives = tag_quotes_in_text(text, filter_possessive)

    total_quotes = sum(stats.values())
    total_excluded = excluded_contractions + excluded_possessives

    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("引号专项赋码统计报告")
    report_lines.append("=" * 70)
    report_lines.append(f"源文件: {input_path}")
    report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"文件总字符数: {len(text)}")
    report_lines.append(f"引号对总数: {total_quotes}")
    if total_excluded > 0:
        report_lines.append(f"排除撇号总数: {total_excluded}（缩写 {excluded_contractions} + 所有格 {excluded_possessives}）")
    report_lines.append("")

    if total_excluded > 0:
        report_lines.append("-" * 70)
        report_lines.append("排除撇号统计")
        report_lines.append("-" * 70)
        report_lines.append(f"  缩写撇号（it's, don't等）: {excluded_contractions}")
        report_lines.append(f"  所有格撇号（Lapis'等）  : {excluded_possessives}")
        report_lines.append(f"  合计排除               : {total_excluded}")
        report_lines.append("")

    report_lines.append("-" * 70)
    report_lines.append("各类型引号统计")
    report_lines.append("-" * 70)
    report_lines.append(f"{'标签':<8} {'引号':<6} {'说明':<25} {'数量':<8} {'占比':<10}")
    report_lines.append("-" * 70)

    for tag, open_q, close_q in QUOTE_PATTERNS:
        count = stats.get(tag, 0)
        pct = f"{count / total_quotes * 100:.1f}%" if total_quotes > 0 else "0.0%"
        desc = QUOTE_INFO[tag]["desc"]
        quote_display = f"{open_q}{close_q}"
        report_lines.append(f"{tag:<8} {quote_display:<6} {desc:<25} {count:<8} {pct:<10}")

    report_lines.append("-" * 70)
    report_lines.append("")

    if any(quote_contents[tag] for tag in quote_contents):
        report_lines.append("-" * 70)
        report_lines.append("引号内容详表")
        report_lines.append("-" * 70)
        for tag, _, _ in QUOTE_PATTERNS:
            contents = quote_contents.get(tag, [])
            if contents:
                report_lines.append("")
                report_lines.append(f"[{tag}] {QUOTE_INFO[tag]['desc']} ({QUOTE_INFO[tag]['open']}{QUOTE_INFO[tag]['close']}) — 共 {len(contents)} 处")
                report_lines.append("-" * 50)
                for idx, content in enumerate(contents, 1):
                    display = content.replace("\n", "\\n")
                    if len(display) > 80:
                        display = display[:77] + "..."
                    report_lines.append(f"  {idx:>3}. {display}")

    report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("赋码标签说明")
    report_lines.append("=" * 70)
    for tag in QUOTE_INFO:
        info = QUOTE_INFO[tag]
        report_lines.append(f"  <{tag}>  {info['open']}{info['close']}  {info['desc']}")

    report = "\n".join(report_lines)

    if output_path:
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(tagged_text)
        print(f"[完成] 赋码文件已保存: {output_path}")

    if stats_path:
        stats_dir = os.path.dirname(stats_path)
        if stats_dir and not os.path.exists(stats_dir):
            os.makedirs(stats_dir, exist_ok=True)
        with open(stats_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[完成] 统计报告已保存: {stats_path}")

    if not output_path and not stats_path:
        print(report)

    return tagged_text, stats, report


def process_directory(input_dir, output_dir, stats_path=None, filter_possessive=True):
    txt_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".txt")]

    if not txt_files:
        print(f"[警告] 目录中未找到 .txt 文件: {input_dir}")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    all_stats = Counter()
    all_contents = defaultdict(list)
    all_excluded_contractions = 0
    all_excluded_possessives = 0
    file_reports = []

    for filename in sorted(txt_files):
        input_path = os.path.join(input_dir, filename)
        base, ext = os.path.splitext(filename)
        output_path = os.path.join(output_dir, f"{base}_tagged{ext}")

        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read()

        tagged_text, stats, quote_contents, excluded_contractions, excluded_possessives = tag_quotes_in_text(text, filter_possessive)
        all_stats.update(stats)
        all_excluded_contractions += excluded_contractions
        all_excluded_possessives += excluded_possessives
        for tag, contents in quote_contents.items():
            all_contents[tag].extend(contents)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(tagged_text)
        print(f"[完成] {filename} -> {os.path.basename(output_path)}")

        file_reports.append({
            "filename": filename,
            "chars": len(text),
            "quotes": dict(stats),
            "total": sum(stats.values()),
        })

    total_quotes = sum(all_stats.values())
    total_excluded = all_excluded_contractions + all_excluded_possessives

    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("引号专项赋码统计报告（批量）")
    report_lines.append("=" * 70)
    report_lines.append(f"源目录: {input_dir}")
    report_lines.append(f"输出目录: {output_dir}")
    report_lines.append(f"处理文件数: {len(txt_files)}")
    report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"引号对总数: {total_quotes}")
    if total_excluded > 0:
        report_lines.append(f"排除撇号总数: {total_excluded}（缩写 {all_excluded_contractions} + 所有格 {all_excluded_possessives}）")
    report_lines.append("")

    if total_excluded > 0:
        report_lines.append("-" * 70)
        report_lines.append("排除撇号统计（汇总）")
        report_lines.append("-" * 70)
        report_lines.append(f"  缩写撇号（it's, don't等）: {all_excluded_contractions}")
        report_lines.append(f"  所有格撇号（Lapis'等）  : {all_excluded_possessives}")
        report_lines.append(f"  合计排除               : {total_excluded}")
        report_lines.append("")

    report_lines.append("-" * 70)
    report_lines.append("各文件统计")
    report_lines.append("-" * 70)
    report_lines.append(f"{'文件名':<35} {'字符数':<10} {'引号对数':<10}")
    report_lines.append("-" * 70)
    for fr in file_reports:
        report_lines.append(f"{fr['filename']:<35} {fr['chars']:<10} {fr['total']:<10}")
    report_lines.append("-" * 70)
    report_lines.append("")

    report_lines.append("-" * 70)
    report_lines.append("各类型引号汇总统计")
    report_lines.append("-" * 70)
    report_lines.append(f"{'标签':<8} {'引号':<6} {'说明':<25} {'数量':<8} {'占比':<10}")
    report_lines.append("-" * 70)
    for tag, open_q, close_q in QUOTE_PATTERNS:
        count = all_stats.get(tag, 0)
        pct = f"{count / total_quotes * 100:.1f}%" if total_quotes > 0 else "0.0%"
        desc = QUOTE_INFO[tag]["desc"]
        quote_display = f"{open_q}{close_q}"
        report_lines.append(f"{tag:<8} {quote_display:<6} {desc:<25} {count:<8} {pct:<10}")
    report_lines.append("-" * 70)
    report_lines.append("")

    if any(all_contents[tag] for tag in all_contents):
        report_lines.append("-" * 70)
        report_lines.append("引号内容详表（汇总）")
        report_lines.append("-" * 70)
        for tag, _, _ in QUOTE_PATTERNS:
            contents = all_contents.get(tag, [])
            if contents:
                report_lines.append("")
                report_lines.append(f"[{tag}] {QUOTE_INFO[tag]['desc']} ({QUOTE_INFO[tag]['open']}{QUOTE_INFO[tag]['close']}) — 共 {len(contents)} 处")
                report_lines.append("-" * 50)
                for idx, content in enumerate(contents, 1):
                    display = content.replace("\n", "\\n")
                    if len(display) > 80:
                        display = display[:77] + "..."
                    report_lines.append(f"  {idx:>3}. {display}")

    report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("赋码标签说明")
    report_lines.append("=" * 70)
    for tag in QUOTE_INFO:
        info = QUOTE_INFO[tag]
        report_lines.append(f"  <{tag}>  {info['open']}{info['close']}  {info['desc']}")

    report = "\n".join(report_lines)

    if stats_path:
        stats_dir = os.path.dirname(stats_path)
        if stats_dir and not os.path.exists(stats_dir):
            os.makedirs(stats_dir, exist_ok=True)
        with open(stats_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[完成] 统计报告已保存: {stats_path}")
    else:
        print(report)

    return report


def main():
    parser = argparse.ArgumentParser(
        description="引号专项赋码工具 — 对文本中的引号进行行内标注（自动排除英文缩写撇号）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
赋码标签体系:
  <QZH1>  「」  中文单引号（直角引号）
  <QZH2>  『』  中文双引号（直角引号）
  <QZH3>  ""   中文全角双引号
  <QZH4>  ''   中文全角单引号
  <QEN1>  ""   英文双引号
  <QEN2>  ''   英文单引号（已排除缩写/所有格撇号）

排除规则:
  规则1: 字母 + ' + 字母 → 缩写撇号 (it's, don't, we've)
  规则2: 字母 + s + ' + 非字母 → 所有格撇号 (Rex Lapis', thieves')
  规则3: 词首 ' + 已知缩写词 → 非正式缩写 ('em, 'cause, 'bout)
  使用 --keep-possessive 可关闭规则2

示例:
  python quote_tagger.py -i text.txt -o text_tagged.txt
  python quote_tagger.py -i text.txt -o text_tagged.txt -s report.txt
  python quote_tagger.py -i ./corpus/ -o ./tagged/ -s report.txt
  python quote_tagger.py -i text.txt --stats-only
  python quote_tagger.py -i text.txt -o out.txt --keep-possessive
        """,
    )
    parser.add_argument("-i", "--input", required=True, help="输入文件或目录路径")
    parser.add_argument("-o", "--output", help="输出文件或目录路径")
    parser.add_argument("-s", "--stats", help="统计报告输出路径")
    parser.add_argument("--stats-only", action="store_true", help="仅输出统计报告，不生成赋码文件")
    parser.add_argument("--keep-possessive", action="store_true", help="保留所有格撇号参与配对（默认排除所有格如 Rex Lapis'）")

    args = parser.parse_args()
    filter_possessive = not args.keep_possessive

    if not os.path.exists(args.input):
        print(f"[错误] 路径不存在: {args.input}")
        sys.exit(1)

    if os.path.isfile(args.input):
        if args.stats_only:
            process_file(args.input, stats_path=args.stats, filter_possessive=filter_possessive)
        else:
            if not args.output:
                base, ext = os.path.splitext(args.input)
                args.output = f"{base}_tagged{ext}"
                print(f"[提示] 未指定输出路径，默认输出到: {args.output}")
            process_file(args.input, args.output, args.stats, filter_possessive=filter_possessive)

    elif os.path.isdir(args.input):
        if args.stats_only:
            process_directory(args.input, output_dir=os.path.join(args.input, "tagged"), stats_path=args.stats, filter_possessive=filter_possessive)
        else:
            if not args.output:
                args.output = os.path.join(args.input, "tagged")
                print(f"[提示] 未指定输出目录，默认输出到: {args.output}")
            process_directory(args.input, args.output, args.stats, filter_possessive=filter_possessive)
    else:
        print(f"[错误] 无效路径: {args.input}")
        sys.exit(1)


if __name__ == "__main__":
    main()
