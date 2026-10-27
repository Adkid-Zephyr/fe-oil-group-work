from pathlib import Path
import json,re,html
root=Path(__file__).resolve().parent
repository=root.parents[1]
report=(root/'source/report.html').read_text(encoding='utf-8')
words=len(re.findall(r"\b[\w]+(?:[’'-][\w]+)*\b",html.unescape(re.sub('<[^>]+>',' ',report))))
template=(root/'source/template.html').read_text(encoding='utf-8').replace('\n+@','\n@')
assert '__DATA__' in template
payload=json.loads((repository/'data/results/Benchmark/analysis.json').read_text(encoding='utf-8'))
result=template.replace('__DATA__',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('</','<\\/')).replace('__CODE__',json.dumps((root/'analyze.py').read_text()).replace('</','<\\/')).replace('__REPORT__',report).replace('__WORDCOUNT__',str(words))
assert not re.search(r'__(DATA|REPORT|CODE|WORDCOUNT)__',result)
(root/'dist/index.html').write_text(result,encoding='utf-8')
print('Report word count:',words,'HTML bytes:',len(result.encode()))
