// 3D replay of the last swing: a simple mannequin driven by MediaPipe pose world landmarks (metres, hip-centred).
// three.js loads from the CDN only when the first replay is shown, so the page starts as fast as before.
// World landmarks come from the unmirrored camera frames (the page mirrors only the on-screen video with CSS),
// so landmark 16 is the golfer's right hand, where the glove is.

const THREE_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
const ORBIT_URL = "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js";
const BONES = [[11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24], [23, 25], [25, 27], [24, 26], [26, 28], [27, 31], [28, 32]];
const GLOVE = 16;

let THREE = null, Orbit = null;

async function loadThree() {
  if (!THREE) {
    THREE = await import(THREE_URL);
    ({ OrbitControls: Orbit } = await import(ORBIT_URL));
  }
}

// rows: [[phone_ms, 33 x (x, y, z)], ...] -> frames of THREE-space points (x right, y up, z toward the viewer)
function toFrames(rows) {
  return rows.filter((r) => r.length >= 1 + 33 * 3).map((r) => {
    const p = [];
    for (let i = 0; i < 33; i++) p.push([r[1 + i * 3], -r[2 + i * 3], -r[3 + i * 3]]);
    return { t: r[0], p };
  });
}

export function createReplay(host, labels) {
  let renderer, scene, camera, controls, joints = [], bones = [], gloveBall, frames = [], start = 0, raf = 0, speed = 0.35, impactMs = null;
  const info = document.createElement("div");
  info.style.cssText = "position:absolute;left:10px;bottom:8px;font-size:12px;color:#9aa5ad;pointer-events:none";
  host.style.position = "relative"; host.appendChild(info);

  async function init() {
    await loadThree();
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setClearColor(0x0f1214);
    host.insertBefore(renderer.domElement, info);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(40, 1, 0.05, 50);
    camera.position.set(0, 0.2, 3.2);
    controls = new Orbit(camera, renderer.domElement);
    controls.target.set(0, -0.1, 0); controls.enableDamping = true; controls.enablePan = false;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.2); sun.position.set(2, 3, 2); scene.add(sun);
    const grid = new THREE.GridHelper(4, 16, 0x3a454e, 0x252c32); grid.position.y = -1.0; scene.add(grid);
    const skin = new THREE.MeshStandardMaterial({ color: 0xc9ced3, roughness: 0.6 });
    const boneMat = new THREE.MeshStandardMaterial({ color: 0xffb74d, roughness: 0.5 });
    for (let i = 0; i < 33; i++) {
      const m = new THREE.Mesh(new THREE.SphereGeometry(i === 0 ? 0.11 : 0.028, 16, 12), skin);
      m.visible = i === 0 || i >= 11; scene.add(m); joints.push(m);
    }
    for (const _ of BONES) {
      const c = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 1, 10), boneMat); scene.add(c); bones.push(c);
    }
    gloveBall = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), new THREE.MeshStandardMaterial({ color: 0x4fc3f7, emissive: 0x1971c2, emissiveIntensity: 0.4 }));
    scene.add(gloveBall);
    new ResizeObserver(resize).observe(host); resize();
  }

  function resize() {
    if (!renderer) return;
    const w = host.clientWidth, h = host.clientHeight;
    renderer.setSize(w, h, false); renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
    camera.aspect = w / Math.max(1, h); camera.updateProjectionMatrix();
  }

  const up = () => new THREE.Vector3(0, 1, 0);
  function pose(p) {
    // ground the feet: lowest ankle/heel/toe sits on the grid
    const floor = Math.min(...[27, 28, 29, 30, 31, 32].map((i) => p[i][1]));
    const P = p.map(([x, y, z]) => new THREE.Vector3(x, y - floor - 1.0, z));
    P.forEach((v, i) => joints[i].position.copy(v));
    joints[0].position.copy(P[0]).add(new THREE.Vector3(0, 0.03, 0));
    BONES.forEach(([a, b], k) => {
      const A = P[a], B = P[b], mid = A.clone().add(B).multiplyScalar(0.5), len = A.distanceTo(B);
      bones[k].position.copy(mid); bones[k].scale.set(1, Math.max(0.001, len), 1);
      bones[k].quaternion.setFromUnitVectors(up(), B.clone().sub(A).normalize());
    });
    gloveBall.position.copy(P[GLOVE]);
  }

  function tick(now) {
    raf = requestAnimationFrame(tick);
    controls.update();
    if (frames.length) {
      const span = frames[frames.length - 1].t - frames[0].t;
      const tt = frames[0].t + (((now - start) * speed) % (span + 600));   // short pause at the end of each loop
      let k = frames.findIndex((f) => f.t >= tt); if (k < 0) k = frames.length - 1;
      pose(frames[k].p);
      if (impactMs != null) info.textContent = labels.fromImpact(((frames[k].t - impactMs) / 1000).toFixed(2));
    }
    renderer.render(scene, camera);
  }

  return {
    async show(rows, impact) {
      frames = toFrames(rows); impactMs = impact;
      if (!frames.length) { info.textContent = labels.noData; return false; }
      if (!renderer) await init();
      start = performance.now();
      if (!raf) raf = requestAnimationFrame(tick);
      return true;
    },
    replay() { start = performance.now(); },
    setSpeed(s) { speed = s; },
    stop() { if (raf) cancelAnimationFrame(raf); raf = 0; },
  };
}
