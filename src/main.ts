import * as THREE from 'three';
import './style.css';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const app = document.querySelector<HTMLDivElement>('#app')!;
app.innerHTML = `
<div class="hud"><div class="panel"><div class="brand">🌸 SAKURA</div><div>Japanese Life RPG · Prototype</div></div><div class="panel stats"><span>¥ <b id="money">1200</b></span><span>⚡ <b id="energy">86</b>%</span><span>😊 <b id="mood">Хорошее</b></span><span id="clock">08:00</span></div></div>
<div class="hint" id="hint">WASD — движение · мышь — обзор · клик — захват мыши · Esc — отпустить</div>
<div class="interaction" id="interaction"></div>
<div class="rotate-notice"><div class="rotate-icon">↻</div><strong>Поверни телефон горизонтально</strong><span>Игра лучше работает в альбомной ориентации</span></div>
<div class="controls mobile-only"><div class="joystick-zone"><div class="joystick" id="joystick"><div class="stick" id="stick"></div></div><span class="control-label">ДВИЖЕНИЕ</span></div><div class="actions"><button class="btn" id="interact">E · ДЕЙСТВИЕ</button><button class="btn" id="camera">КАМЕРА</button></div></div>`;
const scene = new THREE.Scene(); scene.background = new THREE.Color(0xb8d4d2); scene.fog = new THREE.Fog(0xb8d4d2, 28, 85);
const camera = new THREE.PerspectiveCamera(65, innerWidth/innerHeight, .1, 150);
const renderer = new THREE.WebGLRenderer({antialias:true}); renderer.setPixelRatio(Math.min(devicePixelRatio,2)); renderer.setSize(innerWidth,innerHeight); renderer.shadowMap.enabled=true; renderer.shadowMap.type=THREE.PCFSoftShadowMap; app.prepend(renderer.domElement);
scene.add(new THREE.HemisphereLight(0xe8f5ff,0x71806c,2));
const sun = new THREE.DirectionalLight(0xffedcf,2.2); sun.position.set(-12,22,10); sun.castShadow=true; scene.add(sun);
const mat=(color:number)=>new THREE.MeshStandardMaterial({color,roughness:.88});
function box(x:number,y:number,z:number,w:number,h:number,d:number,color:number){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mat(color));m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;scene.add(m);return m}
const ground=new THREE.Mesh(new THREE.PlaneGeometry(140,140),mat(0x789b82));ground.rotation.x=-Math.PI/2;ground.receiveShadow=true;scene.add(ground);
box(0,.025,0,9,.05,100,0x555c60);box(0,.03,0,100,.05,9,0x555c60);
for(let i=-45;i<=45;i+=5){box(i,.06,0,.12,.02,3,0xe8dfb8);box(0,.06,i,3,.02,.12,0xe8dfb8)}
function building(x:number,z:number,w:number,d:number,h:number,color:number,label:string){box(x,h/2,z,w,h,d,color);box(x,h+.12,z,w+.3,.25,d+.3,0x394c53);box(x,h*.52,z-d/2-.025,w*.28,h*.42,.08,0x9dcbd0);box(x-w*.28,h*.52,z-d/2-.025,w*.22,h*.42,.08,0x9dcbd0);const sign=box(x,h*.82,z-d/2-.1,w*.7,.45,.12,0xf5e5ce);sign.userData.label=label}
building(-13, -13,10,9,7,0xe8d7c5,'ШКОЛА');building(15,-12,8,8,5,0xf1d9b9,'КОНБИНИ');building(-15,15,8,8,5,0xd8c6b9,'ДОМ');building(15,16,10,8,6,0xd8e1df,'СТАНЦИЯ');
function tree(x:number,z:number){const trunk=new THREE.Mesh(new THREE.CylinderGeometry(.18,.25,2,7),mat(0x75513b));trunk.position.set(x,1,z);scene.add(trunk);const crown=new THREE.Mesh(new THREE.IcosahedronGeometry(1.5,1),mat(0xf0a9bd));crown.position.set(x,3,z);crown.castShadow=true;scene.add(crown)}
for(let i=0;i<24;i++){const x=(i%6)*9-23,z=Math.floor(i/6)*13-19;tree(x,z)}
// Load the player's own GLB model from the repository. Keep its original mesh geometry.
const player = new THREE.Group();
player.position.set(0,0,4);
scene.add(player);
const characterLoader = new GLTFLoader();
// Cache-bust the model URL so mobile browsers do not keep an older GLB after deployment.
const characterUrl = `${import.meta.env.BASE_URL}models/player-rigged.glb?v=mobile-fix-20261018`;
let characterMixer: THREE.AnimationMixer | null = null;
const characterActions = new Map<string, THREE.AnimationAction>();
let activeCharacterAnimation = '';
let turnAnimationTimer = 0;
let previousPlayerYaw = player.rotation.y;
const animationAliases: Record<string, RegExp> = {
  Idle: /idle|stand|breath/,
  Walk: /walk|walking/,
  Run: /run|running|sprint/,
  Turn: /turn|rotate|pivot/
};
function playCharacterAnimation(name: string, playbackRate = 1) {
  // If the GLB uses different clip names, use the closest available locomotion clip.
  const resolved = characterActions.has(name) ? name
    : name === 'Run' && characterActions.has('Walk') ? 'Walk'
    : name === 'Walk' && characterActions.has('Run') ? 'Run'
    : name === 'Idle' && characterActions.has('Walk') ? 'Walk'
    : '';
  if (!resolved) return;
  const next = characterActions.get(resolved)!;
  if (activeCharacterAnimation === resolved) {
    next.setEffectiveTimeScale(playbackRate);
    return;
  }
  const previous = characterActions.get(activeCharacterAnimation);
  next.reset().setEffectiveTimeScale(playbackRate).setEffectiveWeight(1).play();
  if (previous) next.crossFadeFrom(previous, 0.22, true);
  else next.fadeIn(0.22);
  activeCharacterAnimation = resolved;
}
characterLoader.load(characterUrl, (gltf) => {
  const model = gltf.scene;
  model.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(model);
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z);
  if (maxDimension > 0) model.scale.setScalar(1.75 / maxDimension);
  model.position.set(-center.x * model.scale.x, -bounds.min.y * model.scale.y, -center.z * model.scale.z);
  model.traverse((object) => {
    if (object instanceof THREE.Mesh) {
      object.castShadow = true;
      object.receiveShadow = true;
      // Skinned meshes deform beyond their bind-pose bounds during animation.
      // Disable frustum culling so toes/fingers are never incorrectly clipped.
      object.frustumCulled = object instanceof THREE.SkinnedMesh ? false : true;
    }
  });
  player.add(model);
  characterMixer = new THREE.AnimationMixer(gltf.scene);
  for (const clip of gltf.animations) {
    const action = characterMixer.clipAction(clip);
    action.setLoop(THREE.LoopRepeat, Infinity);
    action.clampWhenFinished = false;
    const normalizedName = clip.name.toLowerCase().replace(/[^a-zа-я0-9]/gi, '');
    characterActions.set(clip.name, action);
    for (const [role, pattern] of Object.entries(animationAliases)) {
      if (!characterActions.has(role) && pattern.test(normalizedName)) {
        characterActions.set(role, action);
      }
    }
  }
  playCharacterAnimation('Idle');
  console.info('Персонаж загружен. Найдены клипы:', gltf.animations.map(clip => clip.name));
}, undefined, (error) => {
  console.error('Не удалось загрузить анимированную GLB-модель:', characterUrl, error);
  const hint = document.getElementById('hint');
  if (hint) hint.textContent = 'Анимированная модель пока не загрузилась. Проверь публикацию player-rigged.glb.';
});
const keys=new Set<string>();
// Minecraft-style desktop mouse look: pointer lock hides the system cursor while playing.
const isDesktop=()=>matchMedia('(hover: hover) and (pointer: fine)').matches;
let viewYaw=0,viewPitch=.22;
renderer.domElement.addEventListener('click',()=>{if(isDesktop()&&document.pointerLockElement!==renderer.domElement)renderer.domElement.requestPointerLock?.()});
document.addEventListener('pointerlockchange',()=>{document.body.classList.toggle('pointer-locked',document.pointerLockElement===renderer.domElement)});
document.addEventListener('mousemove',e=>{if(document.pointerLockElement!==renderer.domElement)return;viewYaw-=e.movementX*.0025;viewPitch=THREE.MathUtils.clamp(viewPitch-e.movementY*.002,-.75,1.05)});
// Use physical key positions (KeyboardEvent.code), so movement also works with a Russian or other keyboard layout.
const keyName=(e:KeyboardEvent)=>({KeyW:'w',KeyA:'a',KeyS:'s',KeyD:'d',KeyE:'e',KeyC:'c',ArrowUp:'arrowup',ArrowDown:'arrowdown',ArrowLeft:'arrowleft',ArrowRight:'arrowright',ShiftLeft:'shift',ShiftRight:'shift'} as Record<string,string>)[e.code] ?? e.key.toLowerCase();
addEventListener('keydown',e=>{const key=keyName(e);if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright'].includes(key))e.preventDefault();if(!keys.has(key)){keys.add(key);if(key==='c')toggleCamera();if(key==='e')interact()}});
addEventListener('keyup',e=>keys.delete(keyName(e)));
addEventListener('blur',()=>keys.clear());
let joyX=0,joyY=0,joyPointer:number|null=null;
const joystickZone=document.querySelector<HTMLElement>('.joystick-zone')!,joystick=document.getElementById('joystick')!,stick=document.getElementById('stick')!;
function updateJoystick(e:PointerEvent){const r=joystick.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;let x=e.clientX-cx,y=e.clientY-cy;const max=r.width*.34,len=Math.hypot(x,y);if(len>max){x=x/len*max;y=y/len*max}joyX=x/max;joyY=y/max;stick.style.transform=`translate(${x}px,${y}px)`}
joystickZone.addEventListener('pointerdown',e=>{e.preventDefault();if(joyPointer!==null)return;joyPointer=e.pointerId;joystickZone.setPointerCapture(e.pointerId);updateJoystick(e)});
joystickZone.addEventListener('pointermove',e=>{if(e.pointerId===joyPointer){e.preventDefault();updateJoystick(e)}});
function releaseJoystick(e:PointerEvent){if(e.pointerId!==joyPointer)return;joyPointer=null;joyX=0;joyY=0;stick.style.transform='translate(0,0)'}
joystickZone.addEventListener('pointerup',releaseJoystick);joystickZone.addEventListener('pointercancel',releaseJoystick);joystickZone.addEventListener('lostpointercapture',releaseJoystick);
let firstPerson=false;function toggleCamera(){firstPerson=!firstPerson;document.getElementById('hint')!.textContent=firstPerson?'Мышь — обзор · C — камера от третьего лица · Esc — отпустить':'WASD — движение · мышь — обзор · клик — захват мыши · Esc — отпустить'}
document.getElementById('camera')!.onclick=toggleCamera;document.getElementById('interact')!.onclick=interact;
const places=[{name:'Школа',x:-13,z:-13,desc:'Школа открыта. Уроки начинаются в 08:30.'},{name:'Конбини',x:15,z:-12,desc:'Ты зашёл в конбини. Здесь можно купить перекус.'},{name:'Дом',x:-15,z:15,desc:'Ты дома. Можно немного отдохнуть.'},{name:'Станция',x:15,z:16,desc:'Расписание поездов скоро появится.'}];
function interact(){const p=places.find(v=>Math.hypot(player.position.x-v.x,player.position.z-v.z)<6);const el=document.getElementById('interaction')!;el.textContent=p?p.desc:'Рядом нет места для взаимодействия.';el.style.display='block';setTimeout(()=>el.style.display='none',2600)}
const saved=localStorage.getItem('sakura-position');if(saved){try{const p=JSON.parse(saved);player.position.set(p.x,0,p.z)}catch{}}
let last=performance.now(),gameMinutes=480;const target=new THREE.Vector3();
function animate(now:number){requestAnimationFrame(animate);const dt=Math.min((now-last)/1000,.05);last=now;// Screen coordinates grow right/down, while game controls use left/forward as positive.
let dx=-joyX,dz=-joyY;if(keys.has('w')||keys.has('arrowup'))dz+=1;if(keys.has('s')||keys.has('arrowdown'))dz-=1;if(keys.has('a')||keys.has('arrowleft'))dx+=1;if(keys.has('d')||keys.has('arrowright'))dx-=1;const moving=Math.abs(dx)+Math.abs(dz)>.08;if(moving){const l=Math.hypot(dx,dz);if(l>1){dx/=l;dz/=l;}const sprinting=keys.has('shift');const moveSpeed=(sprinting?5:2.2)*Math.min(1,Math.hypot(dx,dz));const worldX=dx*Math.cos(viewYaw)+dz*Math.sin(viewYaw),worldZ=-dx*Math.sin(viewYaw)+dz*Math.cos(viewYaw);player.position.x+=worldX*moveSpeed*dt;player.position.z+=worldZ*moveSpeed*dt;player.rotation.y=Math.atan2(worldX,worldZ);player.position.x=THREE.MathUtils.clamp(player.position.x,-43,43);player.position.z=THREE.MathUtils.clamp(player.position.z,-43,43)}
if (moving) {
  const yawDelta = Math.atan2(Math.sin(player.rotation.y-previousPlayerYaw), Math.cos(player.rotation.y-previousPlayerYaw));
  if (Math.abs(yawDelta) > 0.9 && turnAnimationTimer <= 0 && characterActions.has('Turn')) turnAnimationTimer = 0.22;
  previousPlayerYaw = player.rotation.y;
  if (turnAnimationTimer > 0) {
    turnAnimationTimer -= dt;
    playCharacterAnimation('Turn');
  } else {
    const sprinting = keys.has('shift');
    // Match the animation cadence to the character's actual movement speed.
    playCharacterAnimation(sprinting ? 'Run' : 'Walk', sprinting ? 1.25 : 0.92);
  }
} else {
  turnAnimationTimer = 0;
  playCharacterAnimation('Idle');
}
characterMixer?.update(dt);
gameMinutes+=dt*1.5;const hh=String(Math.floor(gameMinutes/60)%24).padStart(2,'0'),mm=String(Math.floor(gameMinutes%60)).padStart(2,'0');document.getElementById('clock')!.textContent=hh+':'+mm;
if(firstPerson){camera.position.set(player.position.x,player.position.y+1.65,player.position.z);target.set(player.position.x+Math.sin(viewYaw)*Math.cos(viewPitch),1.65+Math.sin(viewPitch),player.position.z+Math.cos(viewYaw)*Math.cos(viewPitch))}else{const distance=8.5,horizontal=distance*Math.cos(viewPitch);const offset=new THREE.Vector3(-Math.sin(viewYaw)*horizontal,2.2+distance*Math.sin(viewPitch),-Math.cos(viewYaw)*horizontal);camera.position.lerp(new THREE.Vector3(player.position.x+offset.x,player.position.y+offset.y,player.position.z+offset.z),.16);target.set(player.position.x,1.15,player.position.z)}
camera.lookAt(target);renderer.render(scene,camera);if(Math.floor(now/3000)!==Math.floor((now-dt*1000)/3000))localStorage.setItem('sakura-position',JSON.stringify({x:player.position.x,z:player.position.z}))}
requestAnimationFrame(animate);addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight)});
