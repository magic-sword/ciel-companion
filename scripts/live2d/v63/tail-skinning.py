"""Skinning math used by the adopted Samoyed tail rig."""
import math
import numpy as np

ANCHOR = np.array([1115., 2650.])

PATH = np.array([[260, 850], [540, 1020], [850, 1000],
                 [1070, 820], [1085, 560], [980, 460]], float)

SCALE = 1.55

def progress(points):
    starts, segments = PATH[:-1], np.diff(PATH, axis=0)
    lengths = np.linalg.norm(segments, axis=1)
    u = np.clip(np.sum((points[:, None]-starts)*segments, axis=2)/lengths**2, 0, 1)
    projections = starts + u[..., None]*segments
    nearest = np.argmin(np.sum((points[:, None]-projections)**2, axis=2), axis=1)
    cumulative = np.r_[0, np.cumsum(lengths)]
    return (cumulative[nearest] + u[np.arange(len(points)), nearest]*lengths[nearest])/lengths.sum()

def rotate(degrees):
    theta = math.radians(degrees)
    return np.array([[math.cos(theta), -math.sin(theta)],
                     [math.sin(theta), math.cos(theta)]])

def skin(points, angles):
    """Three linked rigid transforms with smooth weights along the tail path."""
    centers = PATH[[0, 2, 4]]
    mats, shifts = [], []
    mat = np.eye(2)
    shift = np.zeros(2)
    for center, angle in zip(centers, angles):
        local = rotate(angle)
        # Compose a local rotation about the rest-space joint with its parent.
        shift = shift + mat @ (center-local @ center)
        mat = mat @ local
        mats.append(mat.copy())
        shifts.append(shift.copy())
    t = progress(points)
    t1 = np.clip((t-.25)/.24, 0, 1)
    t2 = np.clip((t-.66)/.23, 0, 1)
    t1 = t1*t1*(3-2*t1)
    t2 = t2*t2*(3-2*t2)
    weights = np.stack([1-t1, t1*(1-t2), t1*t2], axis=1)
    posed = sum(weights[:, i, None]*(points @ mats[i].T + shifts[i]) for i in range(3))
    return (posed-PATH[0])*SCALE+ANCHOR
