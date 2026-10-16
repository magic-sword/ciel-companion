"""Collect the opt-in Unity playback check after successful editor playback."""
from pathlib import Path
import hashlib
import json
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT/'.local/tail-play-check'
OUT = ROOT/'assets/ciel/rig/proofs/tail-v63'

def main():
    result = json.loads((SOURCE/'result.json').read_text(encoding='utf-8'))
    assert result['passed'] and result['screen'] == '540x1170'
    camera_path = SOURCE/'camera.json'
    camera = json.loads(camera_path.read_text(encoding='utf-8'))
    assert 0 < result['follow_max'] < .95 and 0 < result['tip_max'] < .95
    assert not (SOURCE/'request').exists(), 'Playback check has not finished'
    with Image.open(SOURCE/'neutral.png') as picture:assert picture.size == (540, 1170)
    shutil.copy2(SOURCE/'neutral.png', OUT/'unity-neutral.png')
    shutil.copy2(SOURCE/'samples.csv', OUT/'unity-physics-samples.csv')
    result.update(capture='Unity Conversation scene in Play mode; live SDK physics',
                  portrait_camera=camera,
                  moc_sha256=hashlib.sha256((ROOT/'assets/ciel/runtime/Ciel.moc3').read_bytes()).hexdigest(),
                  physics_sha256=hashlib.sha256((ROOT/'assets/ciel/runtime/Ciel.physics3.json').read_bytes()).hexdigest())
    (OUT/'unity-play-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('UNITY_TAIL_PLAYBACK_VERIFIED', camera)

if __name__ == '__main__':main()
