import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {MeshoptDecoder} from 'three/addons/libs/meshopt_decoder.module.js';

const loader=new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
const textures=new THREE.TextureLoader(), manifest=fetch('dota-models.json?v=1').then(r=>{if(!r.ok)throw Error('Model catalog unavailable');return r.json();});
let jobs=0;const queue=[];
async function limited(fn){if(jobs>=2)await new Promise(resolve=>queue.push(resolve));jobs++;try{return await fn();}finally{jobs--;queue.shift()?.();}}
async function gltf(url){
  const r=await fetch(url,{signal:AbortSignal.timeout(25000)});if(!r.ok)throw Error('Model HTTP '+r.status);
  return loader.parseAsync(await r.arrayBuffer(),url.slice(0,url.lastIndexOf('/')+1));
}

// Each character is loaded only when present in the selected live game.
// The body supplies the skeleton; default armour/weapons share its animated bones.
export async function loadCharacter(heroId){
  return limited(async()=>{
    const catalog=await manifest,definition=catalog.heroes[heroId];
    if(!definition?.models?.hero)throw Error('Character unavailable');
    const base=catalog.base+definition.slug+'/',body=await gltf(base+definition.models.hero);
    const root=new THREE.Group(),model=new THREE.Group();root.add(model);model.add(body.scene);
    const bones=new Map();body.scene.traverse(node=>{if(node.isBone)bones.set(node.name,node);});
    const mats=new Map();
    function material(source){
      const name=source.name;if(mats.has(name))return mats.get(name);
      const info=definition.materials[name],mat=new THREE.MeshStandardMaterial({color:info?.color?0xffffff:0x8799aa,roughness:.76,metalness:.12,side:THREE.DoubleSide});
      if(info?.color){const t=textures.load(base+'textures/'+info.color);t.flipY=false;t.colorSpace=THREE.SRGBColorSpace;mat.map=t;mat.alphaTest=info.alphaTest||0;}
      if(info?.normal){const t=textures.load(base+'textures/'+info.normal);t.flipY=false;mat.normalMap=t;mat.normalScale.set(.55,.55);}
      mats.set(name,mat);return mat;
    }
    function prepare(scene){scene.traverse(node=>{if(node.isMesh){node.material=Array.isArray(node.material)?node.material.map(material):material(node.material);node.castShadow=true;node.receiveShadow=true;node.frustumCulled=false;}});}
    prepare(body.scene);
    const parts=await Promise.allSettled(Object.entries(definition.models).filter(([slot])=>slot!=='hero').map(async([,file])=>{
      const part=await gltf(base+file);prepare(part.scene);
      part.scene.traverse(node=>{if(node.isSkinnedMesh){const names=node.skeleton.bones.map(b=>bones.get(b.name));if(names.every(Boolean))node.bind(new THREE.Skeleton(names,node.skeleton.boneInverses),node.bindMatrix);}});
      model.add(part.scene);
    }));
    const mixer=new THREE.AnimationMixer(body.scene),idle=THREE.AnimationClip.findByName(body.animations,definition.idle),run=THREE.AnimationClip.findByName(body.animations,definition.run);
    const idleAction=idle?mixer.clipAction(idle):null,runAction=run?mixer.clipAction(run):null;
    idleAction?.play();if(runAction){runAction.play();runAction.setEffectiveWeight(0);}
    model.updateMatrixWorld(true);const box=new THREE.Box3().setFromObject(model),size=box.getSize(new THREE.Vector3()),height=size.y;
    // Preserve proportions, while keeping a readable tactical scale on the map.
    const scale=Math.min(4.2/Math.max(.2,height),7/Math.max(.2,size.x),7/Math.max(.2,size.z));model.scale.setScalar(scale);model.position.y=-box.min.y*scale;
    let blend=0;
    return {root,slug:definition.slug,parts:parts.filter(p=>p.status==='fulfilled').length,
      animate(dt,speed){blend=THREE.MathUtils.damp(blend,speed>.25?1:0,9,dt);idleAction?.setEffectiveWeight(1-blend);runAction?.setEffectiveWeight(blend);if(runAction)runAction.timeScale=THREE.MathUtils.clamp(speed/4,.5,1.6);mixer.update(dt);},
      dispose(){mixer.stopAllAction();root.traverse(n=>{if(n.geometry)n.geometry.dispose();});for(const m of mats.values()){m.map?.dispose();m.normalMap?.dispose();m.dispose();}}
    };
  });
}
