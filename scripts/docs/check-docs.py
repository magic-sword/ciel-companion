#!/usr/bin/env python3
"""Validate current-document ownership and local Markdown links without external access."""
import argparse
import html
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r'!?\[[^\]\n]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+[\"\'][^\n]*?)?\s*\)')
ROW = re.compile(r'^\| \[([^]]+)\]\(([^)]+)\) \| (.+) \|$', re.M)

def prose(text, inline=True):
    lines=[]; fence=None
    for line in text.splitlines():
        marker=re.match(r'^\s*(`{3,}|~{3,})',line)
        if marker:
            if fence is None:fence=marker[1][0]
            elif marker[1][0]==fence:fence=None
            lines.append('');continue
        lines.append('' if fence else (re.sub(r'(`+).*?\1','',line) if inline else line))
    return '\n'.join(lines)

def anchors(text):
    used=set();counts={}
    for line in prose(text, inline=False).splitlines():
        match=re.match(r'^#{1,6}\s+(.+?)\s*#*$',line)
        if not match:continue
        title=re.sub(r'\[([^]]+)\]\([^)]+\)',r'\1',match[1])
        # Preserve code-span text for anchors (prose removes spans for link scanning).
        title=html.unescape(title.replace('`','')).lower()
        slug=re.sub(r'[^\w\- ]','',title).replace(' ','-')
        count=counts.get(slug,0);counts[slug]=count+1
        used.add(slug if count==0 else f'{slug}-{count}')
    used.update(re.findall(r'<a\s+(?:id|name)=[\"\']([^\"\']+)',text,re.I))
    return used

def targets(text):
    source=prose(text)
    for match in LINK.finditer(source):yield match[1].strip('<>')
    for match in re.finditer(r'^\s*\[[^]]+\]:\s*(<[^>]+>|\S+)',source,re.M):yield match[1].strip('<>')

def link_error(root,source,target):
    parsed=urlsplit(target)
    if parsed.scheme or parsed.netloc:return None
    if not parsed.path:
        dest=source
    else:
        path=unquote(parsed.path)
        dest=(root/path.lstrip('/')) if path.startswith('/') else source.parent/path
    dest=dest.resolve()
    if not dest.exists():return f'missing target: {target}'
    if parsed.fragment and dest.suffix.lower()=='.md':
        fragment=unquote(parsed.fragment).lower()
        if fragment not in anchors(dest.read_text(encoding='utf-8-sig')):
            return f'missing heading: {target}'
    return None

def check(root):
    errors=[];docs=root/'docs';index=(docs/'README.md').read_text(encoding='utf-8')
    catalog={name:(target,role) for name,target,role in ROW.findall(index)}
    actual={p.relative_to(docs).as_posix() for p in docs.rglob('*.md')}
    for name in sorted(actual-set(catalog)):errors.append('docs/'+name+': no responsibility in docs/README.md')
    for name in sorted(set(catalog)-actual):errors.append('docs/'+name+': catalog entry has no file')
    for name in sorted(actual & set(catalog)):
        target,role=catalog[name]
        if name!='README.md' and len(Path(name).parts)==1:errors.append('docs/'+name+': use a responsibility folder, not the docs root')
        if target!=name:errors.append('docs/'+name+': catalog target must match file name')
        text=(docs/name).read_text(encoding='utf-8-sig')
        if '> 責務：'+role not in text:errors.append('docs/'+name+': responsibility header differs from index')
        if re.search(r'20\d{2}-\d{2}(?:-\d{2})?',name):errors.append('docs/'+name+': historical filenames belong in Git')
        if sum(bool(re.match(r'^#\s',line)) for line in prose(text,inline=False).splitlines())!=1:errors.append('docs/'+name+': more than one document title')
    command=['git','-c','safe.directory='+root.as_posix(),'ls-files','--cached','--others','--exclude-standard','-z']
    tracked=subprocess.check_output(command,cwd=root).decode('utf-8').split('\0')
    files={root/p for p in tracked if p.endswith('.md')}|set(docs.rglob('*.md'))
    for source in sorted(files):
        if not source.is_file():continue
        for target in targets(source.read_text(encoding='utf-8-sig')):
            error=link_error(root,source,target)
            if error:errors.append(source.relative_to(root).as_posix()+': '+error)
    return errors,len(actual),sum(p.is_file() for p in files)

class LinkTests(unittest.TestCase):
    def test_fenced_and_inline_examples_are_not_links(self):
        self.assertEqual(list(targets('```md\n[x](missing.md)\n```\n`[x](also-missing.md)`\n[x](real.md)')),['real.md'])
    def test_local_target_and_heading_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);file=root/'guide.md';file.write_text('# 表示契約\n## 状態と停止\n',encoding='utf-8')
            self.assertIsNone(link_error(root,file,'#状態と停止'))
            self.assertIn('missing heading',link_error(root,file,'#ない見出し'))
            self.assertIn('missing target',link_error(root,file,'missing.md'))
    def test_heading_code_text_is_preserved_and_fenced_titles_ignored(self):
        self.assertEqual(anchors('# `goal.state` の契約\n```sh\n# example\n```'),{'goalstate-の契約'})

    def test_nested_documents_resolve_parent_links_and_images(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'docs/games/minecraft/task.md'
            source.parent.mkdir(parents=True)
            source.write_text('# Task',encoding='utf-8')
            guide=root/'docs/project/policy.md';guide.parent.mkdir(parents=True)
            guide.write_text('# Policy',encoding='utf-8')
            picture=root/'docs/assets/example.png';picture.parent.mkdir(parents=True)
            picture.write_bytes(b'image')
            self.assertIsNone(link_error(root,source,'../../project/policy.md#policy'))
            self.assertIsNone(link_error(root,source,'../../assets/example.png'))
            self.assertIn('missing target',link_error(root,source,'../project/policy.md'))

    def test_external_links_are_not_fetched(self):
        self.assertIsNone(link_error(Path('.'),Path('x.md'),'https://example.com/missing#any'))
    def test_duplicate_headings_have_distinct_anchors(self):
        self.assertEqual(anchors('# 表示\n## 停止\n## 停止'),{'表示','停止','停止-1'})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(LinkTests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    errors,count,scanned=check(ROOT)
    for error in errors:print(error)
    print(f'DOCS_CHECK {"FAILED" if errors else "OK"}: {count} current documents, {scanned} Markdown files scanned, {len(errors)} errors')
    raise SystemExit(1 if errors else 0)
