"""Publish a verified export as the one current Unity update package."""
from pathlib import Path
import sys,json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(Path(__file__).resolve().parent))
import cubism_core as cc
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def safe(base,name):
    p=(base/name).resolve()
    if not p.is_relative_to(base.resolve()):raise ValueError(name)
    return p
def main():
    source=Path(sys.argv[1]).resolve();out=ROOT/'assets/ciel/runtime'
    approved=json.loads((ROOT/'assets/ciel/current/approved.json').read_text())
    assert sha(ROOT/approved['rig'])==approved['rig_sha256'],'Rig changed since approval'
    proof=ROOT/approved['latest_proofs']
    assert json.loads((proof/'adoption.json').read_text())['rig_sha256']==approved['rig_sha256']
    assert json.loads((proof/'verification.json').read_text())['reset_passed']
    layers=json.loads((ROOT/approved['materials']).read_text())['layers']
    assert len(layers)==len({e['name'] for e in layers})==approved['material_count']
    assert {Path(e['path']).name for e in layers}=={p.name for p in (ROOT/'assets/ciel/current/layers').glob('*.png')}
    model=cc.Model(source/'Ciel.model3.json')
    controls={'happy':'ParamHappy','relaxed':'ParamRelaxed','surprised':'ParamSurprised'}
    assert all(controls[n] in model.param_range for n in approved['approved_expressions'])
    for entry in approved['export_files']:
        assert sha(safe(source,entry['path']))==entry['sha256'],entry['path']
    exported=json.loads((source/'Ciel.model3.json').read_text())
    unity=ROOT/'unity/Assets/Characters/Ciel'
    doc=json.loads((unity/'Ciel.model3.json').read_text())
    refs=doc['FileReferences'];newrefs=exported['FileReferences']
    sources={}
    for key in ('Moc','DisplayInfo'):
        refs[key]=newrefs[key];sources[refs[key]]=safe(source,refs[key])
    refs['Textures']=newrefs['Textures']
    for name in refs['Textures']:sources[name]=safe(source,name)
    # Keep the existing physics, nod motion, blink and lip-sync groups.
    for key in ('Physics','Pose','UserData'):
        if key in refs:sources[refs[key]]=safe(unity,refs[key])
    for motions in refs.get('Motions',{}).values():
        for motion in motions:sources[motion['File']]=safe(unity,motion['File'])
    for name in ['neutral',*approved['approved_expressions']]:
        sources[f'Expressions/{name}.exp3.json']=ROOT/'assets/ciel/rig/expressions'/(name+'.exp3.json')
    assert all(p.is_file() for p in sources.values())
    out.mkdir(parents=True,exist_ok=True)
    previous=json.loads((out/'manifest.json').read_text()) if (out/'manifest.json').exists() else {'files':[]}
    for name,src in sources.items():
        dst=safe(out,name);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    (out/'Ciel.model3.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    names=set(sources)|{'Ciel.model3.json'}
    for item in previous['files']:
        if item['path'] not in names:safe(out,item['path']).unlink(missing_ok=True)
    manifest={'approved_date':approved['approved_date'],'source_rig':approved['rig'],
              'source_rig_sha256':approved['rig_sha256'],'material_count':len(layers),
              'approved_expressions':approved['approved_expressions'],
              'files':[{'path':name,'sha256':sha(out/name)} for name in sorted(names)],
              'materials':[{'path':e['path'],'sha256':sha(ROOT/e['path'])} for e in layers]}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('CURRENT_RUNTIME_READY',len(names),'files',out)
if __name__=='__main__':main()
