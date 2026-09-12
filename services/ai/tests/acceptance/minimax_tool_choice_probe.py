"""Direct M3 tool-choice capability probe; no domain commit or reasoning capture."""
import json,os,time,urllib.request,urllib.error
from pathlib import Path

def run(output):
    rows=[]
    for choice in ('auto','none','none','auto'):
     payload={'model':'MiniMax-M3','reasoning_split':True,'messages':[{'role':'system','content':'Use lookup_page for facts. Without a tool result do not guess a page. When unable to use tools, return exactly {"status":"needs_verification"}.'},{'role':'user','content':'Call lookup_page to find the first page of chapter I.'}],'tools':[{'type':'function','function':{'name':'lookup_page','description':'Return the first page of a chapter.','parameters':{'type':'object','properties':{'chapter':{'type':'string'}},'required':['chapter'],'additionalProperties':False}}}],'tool_choice':choice,'temperature':0.2,'max_tokens':512}
     started=time.monotonic();row={'scope':'Direct HTTP capability probe, no Harness admission or commit','tool_choice':choice}
     try:
      req=urllib.request.Request('https://api.minimax.cn/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['K3_API_KEY']})
      with urllib.request.urlopen(req,timeout=90) as response:r=json.load(response);row['http_status']=response.status
      msg=r['choices'][0]['message'];row.update(usage=r.get('usage'),finish_reason=r['choices'][0].get('finish_reason'),tool_names=[t.get('function',{}).get('name') for t in msg.get('tool_calls') or []])
      try:parsed=json.loads(msg.get('content') or '')
      except (ValueError,TypeError):parsed=None
      row['strict_needs_verification']=parsed=={'status':'needs_verification'}
     except urllib.error.HTTPError as e:row.update(http_status=e.code,error_class=type(e).__name__)
     except Exception as e:row['error_class']=type(e).__name__
     row['elapsed_ms']=round((time.monotonic()-started)*1000);rows.append(row)
     output.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
     print(json.dumps(row),flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    run(args.output)
