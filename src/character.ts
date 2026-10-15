import * as THREE from 'three';

export type SakuraCharacter = {
  root: THREE.Group;
  update: (dt: number, moving: boolean, elapsed: number) => void;
};

export function createCharacter(): SakuraCharacter {
  const root = new THREE.Group();
  root.name = 'SAKURA_Player_Character';

  const navy = new THREE.MeshStandardMaterial({ color: 0x202f4a, roughness: 0.82 });
  const navyLight = new THREE.MeshStandardMaterial({ color: 0x344967, roughness: 0.84 });
  const shirt = new THREE.MeshStandardMaterial({ color: 0xf4f1e9, roughness: 0.9 });
  const skin = new THREE.MeshStandardMaterial({ color: 0xe8b99b, roughness: 0.92 });
  const hair = new THREE.MeshStandardMaterial({ color: 0x171b27, roughness: 0.94 });
  const hairLight = new THREE.MeshStandardMaterial({ color: 0x292e3d, roughness: 0.9 });
  const trousers = new THREE.MeshStandardMaterial({ color: 0x26364e, roughness: 0.9 });
  const shoes = new THREE.MeshStandardMaterial({ color: 0x171b22, roughness: 0.82 });
  const burgundy = new THREE.MeshStandardMaterial({ color: 0x783e55, roughness: 0.9 });
  const eye = new THREE.MeshStandardMaterial({ color: 0x252333, roughness: 0.45 });
  const gold = new THREE.MeshStandardMaterial({ color: 0xc5a46b, metalness: 0.35, roughness: 0.5 });

  const makeMesh = (geometry: THREE.BufferGeometry, material: THREE.Material, parent: THREE.Object3D, name: string) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = name;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  };
  const capsule = (radius: number, length: number, material: THREE.Material, parent: THREE.Object3D, name: string) =>
    makeMesh(new THREE.CapsuleGeometry(radius, length, 4, 8), material, parent, name);
  const box = (w: number, h: number, d: number, material: THREE.Material, parent: THREE.Object3D, name: string) =>
    makeMesh(new THREE.BoxGeometry(w, h, d), material, parent, name);

  // Backpack sits behind the torso and follows the body.
  const backpack = new THREE.Group();
  backpack.name = 'Backpack';
  backpack.position.set(0, 1.02, -0.255);
  root.add(backpack);
  const bag = box(0.43, 0.52, 0.2, burgundy, backpack, 'Backpack_Main');
  bag.position.y = 0.02;
  const pocket = box(0.3, 0.18, 0.025, navyLight, backpack, 'Backpack_Pocket');
  pocket.position.set(0, -0.12, 0.115);
  const bagTop = makeMesh(new THREE.SphereGeometry(0.22, 12, 8), burgundy, backpack, 'Backpack_Top');
  bagTop.scale.set(1, 0.45, 0.48);
  bagTop.position.set(0, 0.28, 0);

  // Legs are built as hinged upper/lower segments for a simple walk cycle.
  const hips = new THREE.Group();
  hips.position.y = 0.91;
  hips.name = 'Hips';
  root.add(hips);
  const pelvis = box(0.42, 0.24, 0.29, trousers, hips, 'Pelvis');
  pelvis.position.y = -0.02;

  const legs: THREE.Group[] = [];
  const shins: THREE.Group[] = [];
  for (const side of [-1, 1]) {
    const leg = new THREE.Group();
    leg.position.set(side * 0.13, -0.12, 0);
    leg.name = side < 0 ? 'Left_Thigh' : 'Right_Thigh';
    hips.add(leg);
    const thigh = capsule(0.105, 0.31, trousers, leg, 'Thigh');
    thigh.position.y = -0.2;
    const knee = new THREE.Group();
    knee.position.y = -0.43;
    knee.name = side < 0 ? 'Left_Knee' : 'Right_Knee';
    leg.add(knee);
    const shin = capsule(0.085, 0.34, trousers, knee, 'Shin');
    shin.position.y = -0.2;
    const shoe = box(0.19, 0.12, 0.31, shoes, knee, 'School_Shoe');
    shoe.position.set(0, -0.30, 0.075);
    const sole = box(0.195, 0.035, 0.315, gold, knee, 'Shoe_Sole');
    sole.position.set(0, -0.365, 0.075);
    legs.push(leg);
    shins.push(knee);
  }

  // Jacket and shirt form a layered school uniform.
  const torso = new THREE.Group();
  torso.position.y = 1.14;
  torso.name = 'Torso';
  root.add(torso);
  const jacket = capsule(0.255, 0.38, navy, torso, 'School_Blazer');
  jacket.scale.set(1.05, 1.0, 0.72);
  jacket.position.y = 0.04;
  const shirtFront = box(0.18, 0.43, 0.035, shirt, torso, 'White_Shirt');
  shirtFront.position.set(0, 0.02, 0.19);
  const tie = makeMesh(new THREE.ConeGeometry(0.055, 0.27, 4), burgundy, torso, 'Tie');
  tie.rotation.x = Math.PI;
  tie.position.set(0, -0.015, 0.218);
  const collarL = makeMesh(new THREE.ConeGeometry(0.075, 0.14, 3), shirt, torso, 'Collar_Left');
  collarL.rotation.set(Math.PI / 2, 0, 0.38);
  collarL.position.set(-0.075, 0.24, 0.19);
  const collarR = collarL.clone();
  collarR.name = 'Collar_Right';
  collarR.position.x = 0.075;
  collarR.rotation.z = -0.38;
  torso.add(collarR);
  for (let i = 0; i < 3; i++) {
    const button = makeMesh(new THREE.SphereGeometry(0.018, 8, 6), gold, torso, 'Blazer_Button');
    button.position.set(0.09, 0.02 - i * 0.105, 0.205);
  }

  const arms: THREE.Group[] = [];
  const forearms: THREE.Group[] = [];
  for (const side of [-1, 1]) {
    const arm = new THREE.Group();
    arm.position.set(side * 0.29, 0.2, 0);
    arm.name = side < 0 ? 'Left_Shoulder' : 'Right_Shoulder';
    torso.add(arm);
    const upper = capsule(0.09, 0.27, navy, arm, 'Upper_Arm');
    upper.position.y = -0.16;
    const elbow = new THREE.Group();
    elbow.position.y = -0.34;
    elbow.name = side < 0 ? 'Left_Elbow' : 'Right_Elbow';
    arm.add(elbow);
    const lower = capsule(0.075, 0.25, navyLight, elbow, 'Forearm');
    lower.position.y = -0.15;
    const cuff = makeMesh(new THREE.CylinderGeometry(0.076, 0.076, 0.055, 10), shirt, elbow, 'Cuff');
    cuff.position.y = -0.31;
    const hand = makeMesh(new THREE.SphereGeometry(0.075, 10, 8), skin, elbow, 'Hand');
    hand.position.y = -0.38;
    arms.push(arm);
    forearms.push(elbow);
  }

  // Neck and head.
  const neck = makeMesh(new THREE.CylinderGeometry(0.075, 0.085, 0.13, 10), skin, root, 'Neck');
  neck.position.y = 1.48;
  const head = new THREE.Group();
  head.position.set(0, 1.68, 0.005);
  head.name = 'Head';
  root.add(head);
  const face = makeMesh(new THREE.SphereGeometry(0.245, 20, 16), skin, head, 'Face');
  face.scale.set(0.88, 1.12, 0.92);
  const hairCap = makeMesh(new THREE.SphereGeometry(0.255, 20, 14), hair, head, 'Hair_Cap');
  hairCap.scale.set(1.02, 0.7, 1.0);
  hairCap.position.set(0, 0.13, -0.015);
  for (const side of [-1, 0, 1]) {
    const bang = makeMesh(new THREE.SphereGeometry(0.105, 12, 8), side === 0 ? hair : hairLight, head, 'Hair_Fringe');
    bang.scale.set(0.85, 1.55, 0.75);
    bang.position.set(side * 0.115, 0.105 - Math.abs(side) * 0.025, 0.19);
    bang.rotation.z = -side * 0.22;
  }
  const backHair = makeMesh(new THREE.SphereGeometry(0.22, 16, 12), hair, head, 'Back_Hair');
  backHair.scale.set(1.02, 1.05, 0.68);
  backHair.position.set(0, -0.035, -0.13);
  for (const side of [-1, 1]) {
    const eyeMesh = makeMesh(new THREE.SphereGeometry(0.027, 10, 8), eye, head, 'Eye');
    eyeMesh.position.set(side * 0.085, 0.005, 0.238);
    const highlight = makeMesh(new THREE.SphereGeometry(0.008, 8, 6), shirt, head, 'Eye_Highlight');
    highlight.position.set(side * 0.085 - 0.006, 0.015, 0.258);
  }
  const mouth = makeMesh(new THREE.BoxGeometry(0.055, 0.009, 0.008), burgundy, head, 'Mouth');
  mouth.position.set(0, -0.09, 0.246);

  root.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.castShadow = true;
      obj.receiveShadow = true;
    }
  });

  let walkPhase = 0;
  const update = (dt: number, moving: boolean, elapsed: number) => {
    const blend = 1 - Math.exp(-dt * 12);
    if (moving) walkPhase += dt * 10;
    const swing = moving ? Math.sin(walkPhase) * 0.48 : 0;
    const kneeBend = moving ? Math.max(0, Math.sin(walkPhase + Math.PI / 2)) * 0.52 : 0;
    legs[0].rotation.x = THREE.MathUtils.lerp(legs[0].rotation.x, swing, blend);
    legs[1].rotation.x = THREE.MathUtils.lerp(legs[1].rotation.x, -swing, blend);
    shins[0].rotation.x = THREE.MathUtils.lerp(shins[0].rotation.x, kneeBend, blend);
    shins[1].rotation.x = THREE.MathUtils.lerp(shins[1].rotation.x, Math.max(0, -Math.sin(walkPhase + Math.PI / 2)) * 0.52, blend);
    arms[0].rotation.x = THREE.MathUtils.lerp(arms[0].rotation.x, -swing * 0.72, blend);
    arms[1].rotation.x = THREE.MathUtils.lerp(arms[1].rotation.x, swing * 0.72, blend);
    forearms[0].rotation.x = THREE.MathUtils.lerp(forearms[0].rotation.x, moving ? -0.18 : 0, blend);
    forearms[1].rotation.x = THREE.MathUtils.lerp(forearms[1].rotation.x, moving ? -0.18 : 0, blend);
    torso.rotation.z = THREE.MathUtils.lerp(torso.rotation.z, moving ? Math.sin(walkPhase) * 0.035 : 0, blend);
    head.rotation.z = THREE.MathUtils.lerp(head.rotation.z, moving ? -Math.sin(walkPhase) * 0.018 : 0, blend);
    root.position.y = moving ? Math.abs(Math.sin(walkPhase * 2)) * 0.035 : Math.sin(elapsed * 1.8) * 0.008;
  };

  return { root, update };
}
