"""Convex polygon clipping helpers for the render-time holdout mesh."""
from mathutils import Vector

EPS = 1e-7

def clip(poly, a, b, inside):
    def distance(p):
        d=(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        return d if inside else -d
    result=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        dp,dq=distance(p),distance(q)
        if dp>=-EPS:result.append(p)
        if (dp>EPS and dq<-EPS) or (dp<-EPS and dq>EPS):
            t=dp/(dp-dq);result.append(tuple(p[i]+t*(q[i]-p[i]) for i in range(3)))
    clean=[]
    for p in result:
        if not clean or sum((p[i]-clean[-1][i])**2 for i in range(3))>EPS**2:clean.append(p)
    if len(clean)>1 and sum((clean[0][i]-clean[-1][i])**2 for i in range(3))<EPS**2:clean.pop()
    if len(clean)<3:return []
    normal=Vector((0,0,0))
    for p,q in zip(clean,clean[1:]+clean[:1]):normal+=Vector(p).cross(Vector(q))
    return clean if normal.length>EPS else []

def subtract(poly, triangle):
    left=poly;out=[]
    for a,b in zip(triangle,triangle[1:]+triangle[:1]):
        if not left:break
        exterior=clip(left,a,b,False)
        if exterior:out.append(exterior)
        left=clip(left,a,b,True)
    return out
