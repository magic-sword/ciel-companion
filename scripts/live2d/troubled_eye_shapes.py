"""Fit the troubled eyelids to the approved reference while retaining gaze keys."""
from pathlib import Path
import json
import numpy as np
PLACEMENT=json.loads((Path(__file__).resolve().parents[2]/'assets/ciel/generated/v37/placement.json').read_text())
def eye_delta(side,part,absolute):
    cx=1285 if side=='L' else 920;u=np.clip((absolute[:,0]-cx)/145,-1,1)
    upper=np.polyval(PLACEMENT['eye_profiles'][side]['coefficients'],u)
    if part in ('Iris','Highlight'):
        delta=(1070+(absolute[:,1]-1070)*.95+18)-absolute[:,1]
        if part=='Iris':delta-=18*np.clip((1045-absolute[:,1])/65,0,1)
        return delta
    if part in ('LashUpper','LidSkin_Upper','Crease'):return upper
    if part in ('LashLower','LidSkin_Lower'):return np.zeros(len(u))
    ty=np.clip((absolute[:,1]-985)/145,0,1);return (1-ty)*upper
