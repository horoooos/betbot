import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js';

// Schematic terrain; every hero position comes from Valve, with no roaming animation.
export function createArena(container, heroes={}) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#0b1223');
  const camera = new THREE.PerspectiveCamera(43, 1, .1, 300);
  const renderer = new THREE.WebGLRenderer({antialias:true,alpha:false});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  container.prepend(renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xcbdfff,0x132116,2.4));
  const sun = new THREE.DirectionalLight(0xffffff,2); sun.position.set(-20,40,10); scene.add(sun);
  const land = new THREE.Mesh(new THREE.BoxGeometry(100,2,100),new THREE.MeshStandardMaterial({color:0x153d35,roughness:.95}));
  land.position.y=-1.5;scene.add(land);
  const river = new THREE.Mesh(new THREE.BoxGeometry(9,.12,140),new THREE.MeshStandardMaterial({color:0x235b76,metalness:.4,roughness:.3}));
  river.rotation.y=-Math.PI/4;river.position.y=-.36;scene.add(river);
  const grid=new THREE.GridHelper(100,20,0x3f6c64,0x204f45);grid.position.y=-.4;scene.add(grid);
  function path(points,color) {const geometry=new THREE.BufferGeometry().setFromPoints(points.map(([x,z])=>new THREE.Vector3(x,-.27,z))); scene.add(new THREE.Line(geometry,new THREE.LineBasicMaterial({color,transparent:true,opacity:.65})));}
  path([[-40,40],[-40,-37],[40,-40]],0x9d9771);path([[-40,40],[40,40],[40,-40]],0x9d9771);path([[-40,40],[40,-40]],0x9d9771);
  const units=new Map(), buildings=new THREE.Group();scene.add(buildings);
  let targets=new Map(),angle=0, top=false, zoom=1, last=performance.now(),active=true;
  const color = t => t===2 ? 0x42e6a4 : 0xff626f;
  const locate = p => new THREE.Vector3(p.x*100,.5,-p.y*100);
  function label(text) {const c=document.createElement('canvas');c.width=128;c.height=64;const ctx=c.getContext('2d');ctx.fillStyle='#f6f8ff';ctx.font='bold 35px sans-serif';ctx.textAlign='center';ctx.fillText(String(text),64,43);const tex=new THREE.CanvasTexture(c);const s=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,depthTest:false}));s.scale.set(6,3,1);s.position.y=4.2;return s;}
  function update(frame) {
    targets=new Map();
    for(const team of frame.teams||[]) for(const p of team.players||[]) {
      const key=team.team+':'+p.id;targets.set(key,locate(p));
      if(!units.has(key)) {const group=new THREE.Group();const body=new THREE.Mesh(new THREE.CylinderGeometry(.75,1.15,2.5,8),new THREE.MeshStandardMaterial({color:color(team.team),emissive:color(team.team),emissiveIntensity:.2}));body.position.y=1.25;group.add(body);const ring=new THREE.Mesh(new THREE.TorusGeometry(1.5,.13,6,24),new THREE.MeshBasicMaterial({color:color(team.team)}));ring.rotation.x=Math.PI/2;group.add(ring);if(heroes[p.hero]?.image){const tex=new THREE.TextureLoader().load(heroes[p.hero].image);tex.colorSpace=THREE.SRGBColorSpace;const portrait=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,depthTest:false}));portrait.position.y=5;portrait.scale.set(6.4,3.6,1);group.add(portrait);}else group.add(label(p.hero));group.position.copy(locate(p));scene.add(group);units.set(key,group);}
    }
    for(const [key,unit] of units) if(!targets.has(key)){scene.remove(unit);unit.traverse(o=>{o.geometry?.dispose();if(o.material){o.material.map?.dispose();o.material.dispose();}});units.delete(key);}
    while(buildings.children.length){const b=buildings.children[0];buildings.remove(b);b.geometry.dispose();b.material.dispose();}
    for(const b of frame.buildings||[]) {if(b.destroyed)continue;const mesh=new THREE.Mesh(new THREE.CylinderGeometry(b.type===2?2:1,1.6,b.type===2?5:3.5,6),new THREE.MeshStandardMaterial({color:color(b.team),roughness:.7}));mesh.position.copy(locate(b));mesh.position.y=1;buildings.add(mesh);}
    active=true;
  }
  function resize(){const w=container.clientWidth,h=container.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}
  const observer=new ResizeObserver(resize);observer.observe(container);resize();
  renderer.setAnimationLoop(()=>{const now=performance.now(),dt=Math.min(.1,(now-last)/1000);last=now;if(document.hidden)return; if(active) for(const [key,p] of targets) units.get(key)?.position.lerp(p,1-Math.exp(-dt*1.7)); const r=112*zoom;camera.position.set(top?0:Math.sin(angle+.35)*r,top?135*zoom:94*zoom,top?.01:Math.cos(angle+.35)*r);camera.lookAt(0,0,0);renderer.render(scene,camera);});
  return {update,freeze(){active=false;},camera(){top=!top;},rotate(){angle+=Math.PI/4;},zoom(){zoom=zoom===1?.78:1;}};
}
