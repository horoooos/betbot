import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
export const terrainScaleX=140/(.0254*20416),terrainScaleZ=140/(.0254*20928);
export function sampleGround(field,x,z){
  if(!field)return 0;
  const u=Math.max(0,Math.min(field.width-1,(x-field.minX)/(field.maxX-field.minX)*(field.width-1)));
  const v=Math.max(0,Math.min(field.height-1,(z-field.minZ)/(field.maxZ-field.minZ)*(field.height-1)));
  const a=Math.floor(u),b=Math.floor(v),c=Math.min(a+1,field.width-1),d=Math.min(b+1,field.height-1),fx=u-a,fz=v-b;
  const value=(field.values[b*field.width+a]*(1-fx)+field.values[b*field.width+c]*fx)*(1-fz)+(field.values[d*field.width+a]*(1-fx)+field.values[d*field.width+c]*fx)*fz;
  return Number.isFinite(value)?value:0;
}
export function createEnvironment(scene,onReady){
  const loader=new GLTFLoader(),root=new THREE.Group(),templates=new Map(),loaded=[];let disposed=false,field=null,ready=false;
  const status=document.getElementById('environmentState');let count=0,treeCount=0;
  root.matrixAutoUpdate=false;root.matrix.set(0,0,-terrainScaleX,0,0,terrainScaleX,0,0,-terrainScaleZ,0,0,-256*140/20928,0,0,0,1);root.visible=false;scene.add(root);
  const progress=()=>{if(status)status.textContent=ready?'Оригинальный рельеф Dota 2':`Загрузка рельефа: ${count}/10`;};progress();
  function tune(object){object.traverse(n=>{if(!n.isMesh)return;n.castShadow=false;n.receiveShadow=true;for(const m of Array.isArray(n.material)?n.material:[n.material]){m.roughness=Math.max(.65,m.roughness||0);m.metalness=Math.min(.25,m.metalness||0);if(m.map)m.map.anisotropy=4;}});return object;}
  function terrainMaterial(object,layer0){object.traverse(n=>{if(!n.isMesh)return;for(const m of Array.isArray(n.material)?n.material:[n.material]){const params=m.userData.vmat?.VectorParams||{},tint=i=>{const v=params['g_vColorTint'+i]||[1,1,1];return new THREE.Color().setRGB(v[0],v[1],v[2],THREE.SRGBColorSpace);};m.onBeforeCompile=shader=>{shader.uniforms.viewerLayer0={value:layer0};shader.uniforms.viewerTint0={value:tint(0)};shader.uniforms.viewerTint1={value:tint(1)};shader.vertexShader='attribute vec4 _texcoord_1; varying vec4 viewerBlend;\n'+shader.vertexShader;shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nviewerBlend = _texcoord_1;');shader.fragmentShader='uniform sampler2D viewerLayer0; uniform vec3 viewerTint0; uniform vec3 viewerTint1; varying vec4 viewerBlend;\n'+shader.fragmentShader;shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>','vec4 layerA = texture2D(viewerLayer0, vMapUv); vec4 layerB = texture2D(map, vMapUv); diffuseColor *= mix(layerA * vec4(viewerTint0, 1.0), layerB * vec4(viewerTint1, 1.0), clamp(viewerBlend.g, 0.0, 1.0));');};m.customProgramCacheKey=()=> 'dota-terrain-blend-1';m.needsUpdate=true;}});}
  const pending=fetch('dota-terrain/environment.json?v=1').then(r=>{if(!r.ok)throw Error('Environment catalog');return r.json();});
  const heights=fetch('dota-terrain/height.json?v=1').then(r=>{if(!r.ok)throw Error('Terrain height');return r.json();});
  pending.then(async catalog=>{
    field=await heights;let cursor=0;
    async function worker(){while(cursor<catalog.ground.length){const path=catalog.ground[cursor++],g=await loader.loadAsync('dota-terrain/'+path);if(disposed)return;terrainMaterial(g.scene,await g.parser.getDependency('texture',0));root.add(tune(g.scene));loaded.push(g.scene);count++;progress();}}
    await Promise.all([worker(),worker()]);if(disposed)return;ready=true;root.visible=true;progress();onReady();
    if(catalog.trees){const trees=await fetch('dota-terrain/trees.json?v=1').then(r=>r.json());
      for(const [key,path] of Object.entries(catalog.trees)){if(disposed)return;const g=await loader.loadAsync('dota-terrain/'+path);g.scene.updateMatrixWorld(true);const rows=trees.filter(t=>t.model===key),transform=new THREE.Matrix4(),position=new THREE.Vector3(),rotation=new THREE.Quaternion(),scale=new THREE.Vector3();
        treeCount+=rows.length;g.scene.traverse(n=>{if(!n.isMesh||!rows.length)return;const geometry=n.geometry.clone();geometry.morphAttributes={};const inst=new THREE.InstancedMesh(geometry,n.material,rows.length);rows.forEach((t,i)=>{position.set(t.origin[1]*.0254,t.origin[2]*.0254,-t.origin[0]*.0254);rotation.setFromAxisAngle(new THREE.Vector3(0,1,0),-t.angle*Math.PI/180);scale.setScalar(t.scale);transform.compose(position,rotation,scale).multiply(n.matrixWorld);inst.setMatrixAt(i,transform);});inst.receiveShadow=true;inst.castShadow=false;inst.computeBoundingSphere();root.add(inst);loaded.push(inst);});
      }
    }
  }).catch(e=>{if(status)status.textContent='Облегчённая карта';console.warn('Dota environment:',e.message);});
  return{height(x,z){return ready?sampleGround(field,x,z):0;},get ready(){return ready;},async building(team,type){
    const catalog=await pending,key=(team===2?'radiant':'dire')+'-'+(type===0?'tower':type===2?'ancient':'barracks');
    if(!templates.has(key))templates.set(key,loader.loadAsync('dota-terrain/'+catalog.buildings[key]).then(g=>tune(g.scene)));
    const template=await templates.get(key);if(disposed)return null;const result=template.clone(true),box=new THREE.Box3().setFromObject(result),size=box.getSize(new THREE.Vector3());
    const factor=Math.min((type===2?9:type===0?6:4.5)/Math.max(.1,size.y),(type===2?10:type===0?4:6)/Math.max(.1,size.x,size.z));result.scale.setScalar(factor);result.position.y=-box.min.y*factor;return result;
  },inspect(){return{ready,groundMeshes:count,trees:treeCount};},dispose(){disposed=true;scene.remove(root);for(const item of loaded)item.traverse(n=>{n.geometry?.dispose();});}};
}
