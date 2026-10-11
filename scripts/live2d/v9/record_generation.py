"""Record the four manually requested tool calls, including rejected candidates."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build import *

rows=[
    (1,'Hair_Front-01.png','rejected','中央束の長さは戻ったが、外側の巻き込みと別の頬髪が重なり過多。候補01/02で合成して不採用。'),
    (2,'Hair_Side_R_Inner-01.png','rejected','原本に広いハロー。手動輪郭マスク後も全体では毛先が多く、候補02/03で不採用。左側はこの原本を反転して試したが最終稿には使用していない。'),
    (3,'Hair_Side_R_LongFront-01.png','rejected','細い長束。幅補正も試したが頬から胸のまとまりで一続きの候補04に劣る。左反転を含め最終稿に不使用。'),
    (4,'Hair_FrontAssembly-01.png','adopted_for_review_A','前髪・頬・胸の髪の一続きの形を候補04で合成確認。候補05で縁・影、候補06で両目と間隔を確認して採用。動作用の分割は段階3。')
]
calls=[]
for ident,name,status,reason in rows:
    prompt_file=next((GEN/'prompts').glob('%02d-*'%ident))
    p=read_json(prompt_file)
    p.update(status=status,reason=reason,result='parts/'+name,sha256=sha(GEN/'parts'/name),transparent_background=True)
    write_json(prompt_file,p)
    calls.append(dict(id=ident,prompt=prompt_file.relative_to(GEN).as_posix(),original='parts/'+name,sha256=p['sha256'],status=status,reason=reason))
write_json(GEN/'generation-log.json',dict(limit=30,attempted_calls=4,successful_calls=4,calls=calls,notes='画像生成ツールは管理する自動キャッシュにも原本を保存する。制作側の原本コピー・作業物・採用品・スクリプトはユーザー指定の3つのv9ディレクトリ内。'))
print('Recorded 4/30 generation calls, 1 adopted original')
