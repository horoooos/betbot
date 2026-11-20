"""Prepare small browser assets from the owner's local, unmodified Dota install.
Input: Source 2 Viewer glTF exports in work/dota-ground and work/dota-export.
No live game state is synthesized. Valve retains ownership of game assets.
"""
from pathlib import Path
import json, shutil, re
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'docs/dota-terrain'

def textures(g, source, target):
    for i, im in enumerate(g.get('images', [])):
        img=Image.open(source/im['uri']); img.thumbnail((512,512))
        alpha='A' in img.getbands() and img.getchannel('A').getextrema()[0]<255
        name=f'texture-{i}.'+('png' if alpha else 'jpg')
        img.convert('RGBA' if alpha else 'RGB').save(target/name, **({'optimize':True} if alpha else {'quality':85,'optimize':True}))
        im['uri']=name

def read_accessor(g, blob, index):
    a=g['accessors'][index];v=g['bufferViews'][a['bufferView']]
    dtype={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
    components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
    assert not v.get('byteStride'), 'Interleaved input requires an explicit conversion'
    return np.frombuffer(blob,dtype=dtype,count=a['count']*components,offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,components)

def main():
    manifest={'ground':[],'buildings':{},'trees':{}}
    for f in (ROOT/'work/dota-export').glob('*/*.gltf'):
        g=json.loads(f.read_text()); target=DEST/'buildings'/f.parent.name;target.mkdir(parents=True,exist_ok=True)
        for b in g['buffers']:shutil.copyfile(f.parent/b['uri'],target/b['uri'])
        textures(g,f.parent,target)
        (target/'model.gltf').write_text(json.dumps(g,separators=(',',':')))
        if f.parent.name.startswith('trees-'):
            manifest['trees']['models/props_tree/'+f.parent.name[6:]+'.vmdl']=f'buildings/{f.parent.name}/model.gltf'
        else:manifest['buildings'][f.parent.name]=f'buildings/{f.parent.name}/model.gltf'
    width,height=256,272
    minx,maxx=-8192*140/20416,8192*140/20416
    minz,maxz=-(8704+256)*140/20928,-(-8704+256)*140/20928
    heights=np.full((height,width),-np.inf,dtype=np.float32)
    for number,f in enumerate(sorted((ROOT/'work/dota-ground').rglob('*.gltf'))):
        g=json.loads(f.read_text());blob=(f.parent/g['buffers'][0]['uri']).read_bytes()
        target=DEST/'ground'/str(number);target.mkdir(parents=True,exist_ok=True)
        packed=bytearray();accessors=[];views=[];mapping={}
        for mesh in g['meshes']:
            for prim in mesh['primitives']:
                positions=read_accessor(g,blob,prim['attributes']['POSITION'])
                triangles=read_accessor(g,blob,prim['indices']).ravel().reshape(-1,3)
                # VRF glTF is Y-up: Dota world X=-Z/metres, world Y=X/metres.
                world=np.stack((-positions[:,2]*140/(.0254*20416),positions[:,1]*140/(.0254*20416),-(positions[:,0]/.0254+256)*140/20928),axis=1)
                gx=(world[:,0]-minx)/(maxx-minx)*(width-1); gz=(world[:,2]-minz)/(maxz-minz)*(height-1)
                for tri in triangles:
                    x=gx[tri];z=gz[tri];y=world[tri,1]
                    left=max(0,int(np.ceil(x.min())));right=min(width-1,int(np.floor(x.max())))
                    top=max(0,int(np.ceil(z.min())));bottom=min(height-1,int(np.floor(z.max())))
                    det=(z[1]-z[2])*(x[0]-x[2])+(x[2]-x[1])*(z[0]-z[2])
                    if left>right or top>bottom or abs(det)<1e-8:continue
                    xx,zz=np.meshgrid(np.arange(left,right+1),np.arange(top,bottom+1))
                    a=((z[1]-z[2])*(xx-x[2])+(x[2]-x[1])*(zz-z[2]))/det
                    b=((z[2]-z[0])*(xx-x[2])+(x[0]-x[2])*(zz-z[2]))/det
                    valid=(a>=-1e-5)&(b>=-1e-5)&(a+b<=1.00001)
                    tile=heights[top:bottom+1,left:right+1]
                    np.maximum(tile,np.where(valid,a*y[0]+b*y[1]+(1-a-b)*y[2],-np.inf),out=tile)
                prim['attributes']={k:v for k,v in prim['attributes'].items() if k in ('POSITION','NORMAL','TEXCOORD_0')}
                for key,index in list(prim['attributes'].items())+[('indices',prim['indices'])]:
                    if index not in mapping:
                        a=dict(g['accessors'][index]);v=g['bufferViews'][a['bufferView']];data=read_accessor(g,blob,index)
                        while len(packed)%4:packed.append(0)
                        views.append({'buffer':0,'byteOffset':len(packed),'byteLength':data.nbytes,'target':v.get('target',34962)})
                        packed.extend(data.tobytes());a['bufferView']=len(views)-1;a.pop('byteOffset',None)
                        mapping[index]=len(accessors);accessors.append(a)
                    if key=='indices':prim[key]=mapping[index]
                    else:prim['attributes'][key]=mapping[index]
        g['buffers']=[{'uri':'mesh.bin','byteLength':len(packed)}];g['bufferViews']=views;g['accessors']=accessors
        textures(g,f.parent,target);(target/'mesh.bin').write_bytes(packed);(target/'model.gltf').write_text(json.dumps(g,separators=(',',':')))
        manifest['ground'].append(f'ground/{number}/model.gltf')
    # Uncovered border cells use the nearest measured terrain sample, never zeros inside cliffs.
    from scipy.ndimage import distance_transform_edt
    missing=~np.isfinite(heights);nearest=distance_transform_edt(missing,return_distances=False,return_indices=True);heights[missing]=heights[tuple(nearest[:,missing])]
    (DEST/'height.json').write_text(json.dumps({'width':width,'height':height,'minX':minx,'maxX':maxx,'minZ':minz,'maxZ':maxz,'values':np.round(heights,4).ravel().tolist()},separators=(',',':')))
    shutil.copyfile(ROOT/'work/dota-trees.json',DEST/'trees.json')
    (DEST/'environment.json').write_text(json.dumps(manifest,separators=(',',':')))
    print('Prepared authentic terrain and buildings:',len(manifest['ground']),len(manifest['buildings']),flush=True)
if __name__=='__main__':main()
