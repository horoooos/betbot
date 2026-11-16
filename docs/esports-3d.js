import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {loadCharacter} from './dota-character.js?v=1';

// Environment is a visual reconstruction. Unit/building positions stay in Valve's frame.
export function createArena(container,heroes={}) {
  const scene=new THREE.Scene();scene.background=new THREE.Color('#09121b');scene.fog=new THREE.FogExp2('#09121b',.003);
  const camera=new THREE.PerspectiveCamera(43,1,.1,420);
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'high-performance'});
  const mobile=matchMedia('(max-width:600px)').matches;
  renderer.setPixelRatio(Math.min(devicePixelRatio,mobile?1.5:2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;
  container.prepend(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.08;
  controls.minDistance=13;controls.maxDistance=190;controls.maxPolarAngle=Math.PI*.48;controls.target.set(0,0,0);camera.position.set(63,102,101);
  scene.add(new THREE.HemisphereLight(0xcbe8ff,0x2c3520,2));
  const sun=new THREE.DirectionalLight(0xffedd5,3.2);sun.position.set(-45,85,25);sun.castShadow=true;
  sun.shadow.mapSize.set(mobile?1024:2048,mobile?1024:2048);Object.assign(sun.shadow.camera,{left:-70,right:70,top:70,bottom:-70,near:1,far:190});sun.shadow.bias=-.0005;sun.shadow.normalBias=.12;scene.add(sun);
  const fill=new THREE.DirectionalLight(0x9cbcff,1.1);fill.position.set(50,30,-30);scene.add(fill);
  const mat=(color,extra={})=>new THREE.MeshStandardMaterial({color,roughness:.85,...extra});
  const stone=mat('#69736e'),darkStone=mat('#454955'),gold=mat('#aaa57b',{metalness:.35}),wood=mat('#5a4835'),red=mat('#f35d43',{emissive:'#c73816',emissiveIntensity:.65}),green=mat('#86e3c6',{emissive:'#35d7a1',emissiveIntensity:.55});
  const coord=p=>new THREE.Vector3(p.x*140,0,-p.y*140);
  const tint=t=>t===2?'#49e4b2':'#ff6e68';
  const add=(group,geo,material,x=0,y=0,z=0)=>{const mesh=new THREE.Mesh(geo,material);mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh;};
  const slab=add(scene,new THREE.BoxGeometry(112,4,112),mat('#25362e'),0,-2.2,0);
  const map=new THREE.TextureLoader().load('dota-terrain/map-740.webp');map.colorSpace=THREE.SRGBColorSpace;map.anisotropy=Math.min(8,renderer.capabilities.getMaxAnisotropy());
  const floor=add(scene,new THREE.PlaneGeometry(112,112),mat('#cfdbb5',{map,roughness:.92}),0,-.12,0);floor.rotation.x=-Math.PI/2;floor.castShadow=false;
  const ground=add(scene,new THREE.PlaneGeometry(230,230),mat('#111f23'),0,-4.3,0);ground.rotation.x=-Math.PI/2;ground.castShadow=false;
  let seed=78431;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  const treeGroups=[];
  function forest(centers,dire){
    const positions=[];for(const [cx,cz,r,count] of centers)for(let i=0;i<count;i++){const a=random()*Math.PI*2,d=Math.sqrt(random())*r;positions.push([cx+Math.cos(a)*d,cz+Math.sin(a)*d,.7+random()*.65]);}
    const trunk=new THREE.InstancedMesh(new THREE.CylinderGeometry(.18,.32,3,5),wood,positions.length);
    const crown=new THREE.InstancedMesh(dire?new THREE.ConeGeometry(1.2,4.8,6):new THREE.IcosahedronGeometry(1.65,1),mat(dire?'#435c60':'#3d7240'),positions.length);
    const top=new THREE.InstancedMesh(dire?new THREE.ConeGeometry(.9,3.5,5):new THREE.IcosahedronGeometry(1.3,1),mat(dire?'#506d70':'#608d4c'),positions.length);
    const dummy=new THREE.Object3D();positions.forEach(([x,z,s],i)=>{dummy.position.set(x,1.4*s,z);dummy.scale.set(s,s,s);dummy.rotation.set(0,random()*6.28,0);dummy.updateMatrix();trunk.setMatrixAt(i,dummy.matrix);dummy.position.y=3.5*s;dummy.updateMatrix();crown.setMatrixAt(i,dummy.matrix);dummy.position.set(x-.3*s,4.5*s,z+.2*s);dummy.updateMatrix();top.setMatrixAt(i,dummy.matrix);});
    for(const mesh of [trunk,crown,top]){mesh.castShadow=true;mesh.receiveShadow=true;scene.add(mesh);treeGroups.push(mesh);}
  }
  forest([[-31,1,7,28],[-22,15,5,22],[-5,28,6,25],[9,38,5,18],[31,38,5,17],[-46,17,3,10],[-33,47,5,16]],false);
  forest([[-34,-40,5,18],[-10,-34,5,22],[17,-19,7,32],[37,-8,5,22],[39,20,5,18],[40,-42,4,14]],true);
  const rockMesh=new THREE.InstancedMesh(new THREE.DodecahedronGeometry(1,0),mat('#5c6460'),75),dummy=new THREE.Object3D();
  for(let i=0;i<75;i++){const side=i%4,along=random()*108-54;dummy.position.set(side<2?(side?55:-55):along,-.3,side<2?along:(side===2?55:-55));dummy.scale.set(1+random()*2,1+random()*3,1+random()*1.5);dummy.rotation.set(random(),random()*6,random());dummy.updateMatrix();rockMesh.setMatrixAt(i,dummy.matrix);}rockMesh.castShadow=true;rockMesh.receiveShadow=true;scene.add(rockMesh);
  // Decorative embers and base lights are ambience, never interpreted as game events.
  const radiantLight=new THREE.PointLight('#64ffbe',30,25,2);radiantLight.position.set(-40,7,35);scene.add(radiantLight);
  const direLight=new THREE.PointLight('#ff5933',35,25,2);direLight.position.set(38,7,-35);scene.add(direLight);
  const structures=new Map(),units=new Map();let active=true,last=performance.now(),follow=null,top=false,gameId=null,modelLoaded=0,modelWanted=0;
  function structure(b){
    const group=new THREE.Group(),baseMat=b.team===2?stone:darkStone,glow=b.team===2?green:red;
    if(b.destroyed){for(let i=0;i<5;i++)add(group,new THREE.DodecahedronGeometry(.5+i*.09),baseMat,Math.sin(i*4)*1.1,.2,Math.cos(i*4)*1.1);return group;}
    if(b.type===2){
      add(group,new THREE.CylinderGeometry(3.8,4.2,.6,10),baseMat,0,.2,0);
      const crystal=add(group,new THREE.OctahedronGeometry(1.8,0),glow,0,3.7,0);crystal.scale.y=1.65;
      for(let i=0;i<6;i++){const a=i*Math.PI/3,x=Math.sin(a)*2.5,z=Math.cos(a)*2.5;add(group,new THREE.CylinderGeometry(.45,.8,3.3,5),baseMat,x,1.9,z);const tip=add(group,new THREE.ConeGeometry(.65,2.1,5),b.team===2?gold:baseMat,x,4.3,z);tip.rotation.z=Math.sin(a)*.18;}
      const halo=add(group,new THREE.TorusGeometry(2.4,.11,6,40),glow,0,.65,0);halo.rotation.x=-Math.PI/2;
    }else if(b.type===0){
      add(group,new THREE.CylinderGeometry(1.4,1.8,.65,8),baseMat,0,.3,0);add(group,new THREE.CylinderGeometry(.65,1.2,3.6,7),baseMat,0,2.3,0);
      add(group,new THREE.CylinderGeometry(1,.85,.45,8),gold,0,4.2,0);add(group,new THREE.OctahedronGeometry(.8,0),glow,0,5.2,0);
      for(let i=0;i<4;i++){const a=i*Math.PI/2;const p=add(group,new THREE.ConeGeometry(.4,1.5,4),baseMat,Math.sin(a)*.8,4.65,Math.cos(a)*.8);p.rotation.z=Math.sin(a)*.25;}
    }else{
      add(group,new THREE.BoxGeometry(2.2,1.5,2.7),baseMat,0,.8,0);const roof=add(group,new THREE.ConeGeometry(1.9,1.4,4),baseMat,0,2.25,0);roof.rotation.y=Math.PI/4;
      add(group,new THREE.BoxGeometry(.6,.7,.12),glow,0,1,1.4);
    }
    return group;
  }
  function billboard(text,team){
    const c=document.createElement('canvas');c.width=512;c.height=112;const g=c.getContext('2d');
    g.fillStyle='rgba(5,12,19,.85)';g.beginPath();g.roundRect(5,5,502,98,18);g.fill();g.fillStyle=tint(team);g.fillRect(10,10,8,88);g.fillStyle='#fff';g.font='bold 38px sans-serif';g.textAlign='center';g.fillText(text.slice(0,23),260,67);
    const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false}));sprite.scale.set(10,2.2,1);sprite.position.y=7;return sprite;
  }
  function fallback(p,team){
    const g=new THREE.Group(),bodyMat=mat(['#345b9e','#863b42','#466a45','#7b6190','#ad8246'][Number(p.hero)%5]);
    add(g,new THREE.CapsuleGeometry(.65,1.35,3,8),bodyMat,0,2,0);add(g,new THREE.SphereGeometry(.48,10,8),mat('#bba58f'),0,3.5,0);
    const legs=[];for(const side of [-1,1]){const leg=new THREE.Group();leg.position.set(side*.37,1.3,0);add(leg,new THREE.CapsuleGeometry(.22,.8,2,6),bodyMat,0,-.5,0);g.add(leg);legs.push(leg);add(g,new THREE.CapsuleGeometry(.23,.9,2,6),bodyMat,side*.9,2.15,0);}
    const staff=add(g,new THREE.CylinderGeometry(.09,.12,3.6,6),gold,1.15,2.1,.25);add(g,new THREE.OctahedronGeometry(.35),team===2?green:red,1.15,4,.25);
    return {root:g,animate(dt,speed){const t=performance.now()/1000;legs[0].rotation.x=Math.sin(t*9)*Math.min(.6,speed*.2);legs[1].rotation.x=-legs[0].rotation.x;},dispose(){g.traverse(n=>{n.geometry?.dispose();});bodyMat.dispose();}};
  }
  const modelState=document.getElementById('modelState');
  function modelStatus(){if(modelState)modelState.textContent=`3D-модели героев: ${modelLoaded}/${modelWanted}`;container.dataset.models=String(modelLoaded);}
  function clearUnit(u){scene.remove(u.group);u.dead=true;u.visual.dispose();u.ring.geometry.dispose();u.ring.material.dispose();u.label.material.map.dispose();u.label.material.dispose();}
  function unit(p,team){
    const key=team+':'+p.id,group=new THREE.Group(),ring=add(group,new THREE.TorusGeometry(1.65,.1,6,32),new THREE.MeshBasicMaterial({color:tint(team)}),0,.05,0);ring.rotation.x=-Math.PI/2;
    const label=billboard(heroes[p.hero]?.name||String(p.hero),team);group.add(label);const visual=fallback(p,team);group.add(visual.root);
    group.position.copy(coord(p));scene.add(group);const u={key,group,ring,label,visual,hero:p.hero,target:coord(p),dead:false,heading:0};group.userData.unitKey=key;
    modelWanted++;modelStatus();
    loadCharacter(p.hero).then(real=>{if(u.dead){real.dispose();return;}group.remove(u.visual.root);u.visual.dispose();u.visual=real;group.add(real.root);modelLoaded++;modelStatus();}).catch(error=>{console.warn('Dota model unavailable',p.hero,error.message);});
    return u;
  }
  function update(frame){
    if(gameId!==frame.match_id){for(const u of units.values())clearUnit(u);units.clear();for(const b of structures.values())scene.remove(b);structures.clear();follow=null;gameId=frame.match_id;modelLoaded=0;modelWanted=0;}
    const keys=new Set();for(const team of frame.teams||[])for(const p of team.players||[]){const key=team.team+':'+p.id;keys.add(key);let u=units.get(key);if(u&&u.hero!==p.hero){clearUnit(u);units.delete(key);u=null;}if(!u){u=unit(p,team.team);units.set(key,u);}u.target.copy(coord(p));}
    for(const [key,u] of units)if(!keys.has(key)){clearUnit(u);units.delete(key);}
    for(const b of frame.buildings||[]){const key=[b.team,b.type,b.x,b.y].join(':'),old=structures.get(key);if(old?.userData.destroyed===b.destroyed)continue;if(old)scene.remove(old);const mesh=structure(b);mesh.position.copy(coord(b));mesh.userData.destroyed=b.destroyed;structures.set(key,mesh);scene.add(mesh);}
    active=true;
  }
  function overview(){follow=null;controls.target.set(0,0,0);camera.position.set(63,102,101);controls.update();}
  function focus(team,id){const u=units.get(team+':'+id);if(!u)return;follow=u.key;controls.target.copy(u.group.position).add(new THREE.Vector3(0,2,0));camera.position.copy(controls.target).add(new THREE.Vector3(12,15,20));controls.update();}
  const raycaster=new THREE.Raycaster();let down=null;
  renderer.domElement.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY];});renderer.domElement.addEventListener('pointerup',e=>{
    if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>6)return;const rect=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);
    const hit=raycaster.intersectObjects([...units.values()].map(u=>u.group),true)[0];if(hit){let node=hit.object;while(node&&!node.userData.unitKey)node=node.parent;if(node){const [team,id]=node.userData.unitKey.split(':');focus(team,id);}}
  });
  function resize(){const w=container.clientWidth,h=container.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}
  const observer=new ResizeObserver(resize);observer.observe(container);resize();
  renderer.setAnimationLoop(()=>{
    const now=performance.now(),dt=Math.min(.07,(now-last)/1000);last=now;if(document.hidden)return;
    for(const u of units.values()){
      const before=u.group.position.clone();if(active)u.group.position.lerp(u.target,1-Math.exp(-dt*.8));const movement=u.group.position.clone().sub(before),speed=movement.length()/Math.max(.001,dt);
      if(speed>.12){const wanted=Math.atan2(movement.x,movement.z),diff=Math.atan2(Math.sin(wanted-u.heading),Math.cos(wanted-u.heading));u.heading+=diff*(1-Math.exp(-dt*9));u.visual.root.rotation.y=u.heading;}
      if(active)u.visual.animate(dt,speed);u.label.visible=!follow||u.key===follow;u.ring.material.opacity=u.key===follow?1:.8;
    }
    if(follow&&units.has(follow)){const next=units.get(follow).group.position.clone().add(new THREE.Vector3(0,2,0)),delta=next.clone().sub(controls.target);camera.position.add(delta);controls.target.copy(next);}
    controls.update();renderer.render(scene,camera);
  });
  return {update,focus,overview,freeze(){active=false;},camera(){top=!top;const target=controls.target;camera.position.copy(target).add(top?new THREE.Vector3(0,follow?28:145,.01):new THREE.Vector3(follow?12:63,follow?15:102,follow?20:101));controls.update();},rotate(){const offset=camera.position.clone().sub(controls.target).applyAxisAngle(new THREE.Vector3(0,1,0),Math.PI/4);camera.position.copy(controls.target).add(offset);controls.update();},zoom(){const offset=camera.position.clone().sub(controls.target);offset.multiplyScalar(offset.length()>30?.65:2);camera.position.copy(controls.target).add(offset);controls.update();},dispose(){renderer.setAnimationLoop(null);observer.disconnect();controls.dispose();for(const u of units.values())clearUnit(u);renderer.dispose();}};
}
