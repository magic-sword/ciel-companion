"""Reference-led eye adjustment in canvas pixels, evaluated at open-eye keys."""
import numpy as np
def eye_delta(side,part,absolute):
    cx=1285 if side=='L' else 920
    u=np.clip((absolute[:,0]-cx)/145,-1,1)
    outward=u if side=='L' else -u
    upper=28*(1-u*u)+9*outward
    # Fit the additional correction to the registered reference lash top edge.
    # Side R samples x=820..970; side L samples x=1235..1385, every 25 px.
    coefficients=(-5.20619048,-18.57380952,24.42857143) if side=='R' else (-10.41238095,30.51904762,28.14285714)
    upper+=np.polyval(coefficients,u)
    lower=-3*(1-.5*u*u)+4*outward
    if part in ('Iris','Highlight'):
        delta=(1070+(absolute[:,1]-1070)*.90+28)-absolute[:,1]
        if part=='Iris':delta-=38*np.clip((1045-absolute[:,1])/65,0,1)
        return delta
    if part in ('LashUpper','LidSkin_Upper','Crease'):return upper
    if part in ('LashLower','LidSkin_Lower'):return lower
    ty=np.clip((absolute[:,1]-985)/145,0,1)
    return (1-ty)*upper+ty*lower
