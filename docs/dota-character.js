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
    const bones=new Map(),inverses=new Map();body.scene.traverse(node=>{if(node.isBone)bones.set(node.name.toLowerCase(),node);if(node.isSkinnedMesh)node.skeleton.bones.forEach((b,i)=>inverses.set(b.name.toLowerCase(),node.skeleton.boneInverses[i]));});
    const mats=new Map(),textureJobs=[];let rejected=0;
    function material(source){
      const name=source.name;if(mats.has(name))return mats.get(name);
      const info=definition.materials[name],mat=new THREE.MeshStandardMaterial({color:0xffffff,roughness:.76,metalness:.08,side:THREE.DoubleSide,visible:!!info});
      // Unmapped additive FX/smear planes are not opaque pieces of the character.
      if(info?.color)textureJobs.push(textures.loadAsync(base+'textures/'+info.color).then(t=>{t.flipY=false;t.colorSpace=THREE.SRGBColorSpace;mat.map=t;mat.alphaTest=info.alphaTest||0;mat.needsUpdate=true;}));
      if(info?.normal)textureJobs.push(textures.loadAsync(base+'textures/'+info.normal).then(t=>{t.flipY=false;mat.normalMap=t;mat.normalScale.set(.55,.55);mat.needsUpdate=true;}));
      mats.set(name,mat);return mat;
    }
    function prepare(scene){scene.traverse(node=>{if(node.isMesh){node.material=Array.isArray(node.material)?node.material.map(material):material(node.material);node.castShadow=true;node.receiveShadow=true;node.frustumCulled=false;}});}
    prepare(body.scene);
    const parts=await Promise.allSettled(Object.entries(definition.models).filter(([slot])=>slot!=='hero').map(async([,file])=>{
      const part=await gltf(base+file);prepare(part.scene);
      const meshes=[];part.scene.traverse(node=>{if(node.isSkinnedMesh)meshes.push(node);});
      for(const mesh of meshes){const source=mesh.skeleton,local=new Map();source.bones.forEach((b,i)=>local.set(b,i));
        const mapBone=(b,visiting=new Set())=>{const name=b.name.toLowerCase();if(bones.has(name))return bones.get(name);if(visiting.has(b)||!b.parent?.isBone)return null;visiting.add(b);const parent=mapBone(b.parent,visiting),index=local.get(b);if(!parent||index===undefined)return null;const inverse=inverses.get(parent.name.toLowerCase());if(!inverse)return null;const clone=new THREE.Bone();clone.name=b.name;const rest=inverse.clone().multiply(source.boneInverses[index].clone().invert());rest.decompose(clone.position,clone.quaternion,clone.scale);parent.add(clone);bones.set(name,clone);inverses.set(name,source.boneInverses[index]);return clone;};
        const mapped=source.bones.map(b=>mapBone(b));if(mapped.every(Boolean))mesh.bind(new THREE.Skeleton(mapped,source.boneInverses.map(m=>m.clone())),mesh.bindMatrix);else{mesh.visible=false;rejected++;}
      }
      model.add(part.scene);
    }));
    const mixer=new THREE.AnimationMixer(body.scene),idle=THREE.AnimationClip.findByName(body.animations,definition.idle),run=THREE.AnimationClip.findByName(body.animations,definition.run);
    const idleAction=idle?mixer.clipAction(idle):null,runAction=run?mixer.clipAction(run):null;
    idleAction?.play();if(runAction){runAction.play();runAction.setEffectiveWeight(0);}
    await Promise.race([Promise.allSettled(textureJobs),new Promise(resolve=>setTimeout(resolve,18000))]);mixer.update(0);model.updateMatrixWorld(true);
    // Sample the skinned idle pose, rather than a rest-pose box with detached props.
    const box=new THREE.Box3(),point=new THREE.Vector3();let visibleMeshes=0;
    model.traverse(node=>{if(!node.isMesh||!node.visible||!(Array.isArray(node.material)?node.material:[node.material]).some(m=>m.visible))return;visibleMeshes++;node.skeleton?.update();const count=node.geometry.attributes.position.count,step=Math.max(1,Math.ceil(count/600));for(let i=0;i<count;i+=step){node.getVertexPosition(i,point).applyMatrix4(node.matrixWorld);box.expandByPoint(point);}});
    if(!visibleMeshes||box.isEmpty())throw Error('No visible character geometry');const size=box.getSize(new THREE.Vector3()),height=size.y;
    // Preserve proportions, while keeping a readable tactical scale on the map.
    const scale=Math.min(4.2/Math.max(.2,height),7/Math.max(.2,size.x),7/Math.max(.2,size.z));model.scale.setScalar(scale);model.position.y=-box.min.y*scale;
    const rootBone=[...bones.values()].find(b=>!b.parent?.isBone),anchor=new THREE.Vector3();if(rootBone){root.updateWorldMatrix(true,true);rootBone.getWorldPosition(anchor);model.worldToLocal(anchor);}const ground=model.position.y;let blend=0;
    return {root,slug:definition.slug,parts:parts.filter(p=>p.status==='fulfilled').length,
      animate(dt,speed){blend=THREE.MathUtils.damp(blend,speed>.25?1:0,9,dt);idleAction?.setEffectiveWeight(1-blend);runAction?.setEffectiveWeight(blend);if(runAction)runAction.timeScale=THREE.MathUtils.clamp(speed/4,.5,1.6);mixer.update(dt);if(rootBone){root.updateWorldMatrix(true,true);rootBone.getWorldPosition(point);model.worldToLocal(point);point.sub(anchor);model.position.set(-point.x*scale,ground-point.y*scale,-point.z*scale);}},
      diagnostics(){return{slug:definition.slug,rejected,visibleMeshes,offset:model.position.toArray(),scale,animated:!!idleAction,run:!!runAction,pose:[...bones.values()].slice(0,20).flatMap(b=>b.quaternion.toArray())};},
      dispose(){mixer.stopAllAction();root.traverse(n=>{if(n.geometry)n.geometry.dispose();});for(const m of mats.values()){m.map?.dispose();m.normalMap?.dispose();m.dispose();}}
    };
  });
}
