/**
 * Three.js scene: synthetic chamber, catheter shaft, electrodes and debug
 * overlays.  Rendering only - it reads the latest `SimulationFrame` and never
 * writes to it.
 *
 * Research prototype - Not for clinical use.
 */

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import type { SimulationFrame } from '../physics/catheter';
import { createSyntheticChamber, type TriangleMesh } from '../geometry/syntheticMesh';
import { useSimulationStore } from '../state/simulationStore';

export type ViewPreset = 'free' | 'sagittal' | 'coronal' | 'axial';

interface SceneViewProps {
  frameRef: React.MutableRefObject<SimulationFrame | null>;
  chamber: TriangleMesh;
}

const SHAFT_RADIAL_SEGMENTS = 12;
const TUBE_SEGMENTS = 96;

export function SceneView({ frameRef, chamber }: SceneViewProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitState | null>(null);
  const showMesh = useSimulationStore((state) => state.showMesh);
  const showNodes = useSimulationStore((state) => state.showNodes);
  const showRodFrames = useSimulationStore((state) => state.showRodFrames);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05070a);

    const camera = new THREE.PerspectiveCamera(45, 1, 1, 4000);
    cameraRef.current = camera;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      // Headless / software environments without WebGL: fail visibly but do not
      // take the whole application down.
      container.textContent = 'WebGL is not available in this browser context.';
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);
    renderer.domElement.setAttribute('data-testid', 'scene-canvas');

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
    keyLight.position.set(120, 160, 220);
    scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0x88bbff, 0.35);
    rimLight.position.set(-160, -80, -40);
    scene.add(rimLight);

    // --- anatomy (translucent, depth-correct via double-sided depth write off)
    const chamberGeometry = new THREE.BufferGeometry();
    chamberGeometry.setAttribute('position', new THREE.BufferAttribute(chamber.positionsMm, 3));
    chamberGeometry.setIndex(new THREE.BufferAttribute(chamber.indices, 1));
    chamberGeometry.computeVertexNormals();
    const chamberMesh = new THREE.Mesh(
      chamberGeometry,
      new THREE.MeshStandardMaterial({
        color: 0xc46a72,
        transparent: true,
        opacity: 0.22,
        side: THREE.DoubleSide,
        depthWrite: false,
        roughness: 0.85,
        metalness: 0.0,
      }),
    );
    chamberMesh.name = 'chamber';
    scene.add(chamberMesh);
    const chamberWire = new THREE.LineSegments(
      new THREE.WireframeGeometry(chamberGeometry),
      new THREE.LineBasicMaterial({ color: 0x6d3f45, transparent: true, opacity: 0.18 }),
    );
    scene.add(chamberWire);

    // --- sheath exit marker: the boundary condition must be visible
    const sheath = new THREE.Mesh(
      new THREE.CylinderGeometry(2.6, 2.6, 14, 20, 1, true),
      new THREE.MeshStandardMaterial({ color: 0x7a8798, side: THREE.DoubleSide, roughness: 0.6 }),
    );
    sheath.rotation.x = Math.PI / 2;
    sheath.position.set(0, 0, -7);
    scene.add(sheath);
    const sheathAxis = new THREE.ArrowHelper(
      new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(0, 0, 0),
      22,
      0x4aa3ff,
      6,
      3,
    );
    scene.add(sheathAxis);

    // --- catheter shaft (a tube swept along the solved centreline)
    const shaftMaterial = new THREE.MeshStandardMaterial({
      color: 0xe8eef6,
      roughness: 0.35,
      metalness: 0.1,
    });
    let shaftMesh: THREE.Mesh | null = null;

    // --- electrodes
    const electrodeGroup = new THREE.Group();
    scene.add(electrodeGroup);
    const tipMaterial = new THREE.MeshStandardMaterial({
      color: 0xffc857,
      roughness: 0.25,
      metalness: 0.6,
    });
    const ringMaterial = new THREE.MeshStandardMaterial({
      color: 0xa8b4c4,
      roughness: 0.3,
      metalness: 0.7,
    });

    // --- debug overlays
    const nodePoints = new THREE.Points(
      new THREE.BufferGeometry(),
      new THREE.PointsMaterial({ color: 0x4aa3ff, size: 1.6, sizeAttenuation: true }),
    );
    scene.add(nodePoints);
    const frameLines = new THREE.LineSegments(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ vertexColors: true }),
    );
    scene.add(frameLines);

    const orbit = createOrbitState(camera, renderer.domElement, new THREE.Vector3(0, 0, 75));
    controlsRef.current = orbit;
    applyPreset(orbit, 'free');

    let animationId = 0;
    const centrelinePoints: THREE.Vector3[] = [];

    const render = () => {
      animationId = requestAnimationFrame(render);
      const frame = frameRef.current;
      const state = useSimulationStore.getState();

      chamberMesh.visible = state.showMesh;
      chamberWire.visible = state.showMesh;
      nodePoints.visible = state.showNodes;
      frameLines.visible = state.showRodFrames;

      if (frame) {
        const nodeCount = frame.centerlineMm.length / 3;
        centrelinePoints.length = 0;
        for (let i = 0; i < nodeCount; i += 1) {
          centrelinePoints.push(
            new THREE.Vector3(
              frame.centerlineMm[3 * i],
              frame.centerlineMm[3 * i + 1],
              frame.centerlineMm[3 * i + 2],
            ),
          );
        }
        const curve = new THREE.CatmullRomCurve3(centrelinePoints, false, 'centripetal', 0.0);
        const tube = new THREE.TubeGeometry(
          curve,
          TUBE_SEGMENTS,
          frame.radiusMm,
          SHAFT_RADIAL_SEGMENTS,
          false,
        );
        if (shaftMesh) {
          shaftMesh.geometry.dispose();
          shaftMesh.geometry = tube;
        } else {
          shaftMesh = new THREE.Mesh(tube, shaftMaterial);
          shaftMesh.name = 'catheter-shaft';
          scene.add(shaftMesh);
        }

        // electrodes
        while (electrodeGroup.children.length < frame.electrodes.length) {
          const index = electrodeGroup.children.length;
          const sphere = new THREE.Mesh(
            new THREE.SphereGeometry(frame.radiusMm * 1.35, 16, 12),
            index === 0 ? tipMaterial : ringMaterial,
          );
          electrodeGroup.add(sphere);
        }
        frame.electrodes.forEach((electrode, index) => {
          const child = electrodeGroup.children[index] as THREE.Mesh;
          child.position.set(...electrode.positionMm);
        });

        if (state.showNodes) {
          const positions = new Float32Array(frame.centerlineMm);
          nodePoints.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
          nodePoints.geometry.attributes.position.needsUpdate = true;
        }
        if (state.showRodFrames) {
          updateFrameLines(frameLines, frame);
        }
      }

      orbit.update();
      renderer.render(scene, camera);
    };
    render();

    const resize = () => {
      const width = container.clientWidth || 1;
      const height = container.clientHeight || 1;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    return () => {
      cancelAnimationFrame(animationId);
      observer.disconnect();
      orbit.dispose();
      renderer.dispose();
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    };
    // The scene is created once; per-frame data flows through `frameRef`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chamber]);

  // Toggles are read inside the render loop; listing them keeps React honest.
  void showMesh;
  void showNodes;
  void showRodFrames;

  return (
    <div className="scene">
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} data-testid="scene-root" />
      <div className="view-presets" aria-label="Camera presets">
        {(['free', 'sagittal', 'coronal', 'axial'] as const).map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => controlsRef.current && applyPreset(controlsRef.current, preset)}
          >
            {preset[0].toUpperCase() + preset.slice(1)}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Draw the material directors m1 (red) and m2 (green) at every edge. */
function updateFrameLines(lines: THREE.LineSegments, frame: SimulationFrame): void {
  const edges = frame.orientationsXyzw.length / 4;
  const positions = new Float32Array(edges * 4 * 3);
  const colors = new Float32Array(edges * 4 * 3);
  const scale = frame.radiusMm * 4;
  const quaternion = new THREE.Quaternion();
  const axis = new THREE.Vector3();
  let cursor = 0;
  for (let j = 0; j < edges; j += 1) {
    const midX = 0.5 * (frame.centerlineMm[3 * j] + frame.centerlineMm[3 * j + 3]);
    const midY = 0.5 * (frame.centerlineMm[3 * j + 1] + frame.centerlineMm[3 * j + 4]);
    const midZ = 0.5 * (frame.centerlineMm[3 * j + 2] + frame.centerlineMm[3 * j + 5]);
    quaternion.set(
      frame.orientationsXyzw[4 * j],
      frame.orientationsXyzw[4 * j + 1],
      frame.orientationsXyzw[4 * j + 2],
      frame.orientationsXyzw[4 * j + 3],
    );
    for (const [localAxis, colour] of [
      [new THREE.Vector3(1, 0, 0), [1, 0.35, 0.35]],
      [new THREE.Vector3(0, 1, 0), [0.35, 1, 0.45]],
    ] as const) {
      axis.copy(localAxis).applyQuaternion(quaternion).multiplyScalar(scale);
      positions[cursor] = midX;
      positions[cursor + 1] = midY;
      positions[cursor + 2] = midZ;
      positions[cursor + 3] = midX + axis.x;
      positions[cursor + 4] = midY + axis.y;
      positions[cursor + 5] = midZ + axis.z;
      for (let k = 0; k < 2; k += 1) {
        colors[cursor + 3 * k] = colour[0];
        colors[cursor + 3 * k + 1] = colour[1];
        colors[cursor + 3 * k + 2] = colour[2];
      }
      cursor += 6;
    }
  }
  lines.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  lines.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  lines.geometry.attributes.position.needsUpdate = true;
  lines.geometry.attributes.color.needsUpdate = true;
}

// --------------------------------------------------------------------------
// Minimal orbit / pan / zoom controller (no external dependency).
// --------------------------------------------------------------------------

interface OrbitState {
  target: THREE.Vector3;
  radius: number;
  azimuth: number;
  polar: number;
  update: () => void;
  dispose: () => void;
}

function createOrbitState(
  camera: THREE.PerspectiveCamera,
  element: HTMLElement,
  target: THREE.Vector3,
): OrbitState {
  const state = {
    target: target.clone(),
    radius: 230,
    azimuth: -Math.PI / 2.2,
    polar: Math.PI / 2.6,
  };
  let dragging: 'orbit' | 'pan' | null = null;
  let lastX = 0;
  let lastY = 0;

  const onDown = (event: PointerEvent) => {
    dragging = event.button === 2 || event.shiftKey ? 'pan' : 'orbit';
    lastX = event.clientX;
    lastY = event.clientY;
    element.setPointerCapture(event.pointerId);
  };
  const onMove = (event: PointerEvent) => {
    if (!dragging) return;
    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    if (dragging === 'orbit') {
      state.azimuth -= dx * 0.006;
      state.polar = Math.min(Math.PI - 0.05, Math.max(0.05, state.polar - dy * 0.006));
    } else {
      const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
      const up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
      const scale = state.radius * 0.0016;
      state.target.addScaledVector(right, -dx * scale).addScaledVector(up, dy * scale);
    }
  };
  const onUp = () => {
    dragging = null;
  };
  const onWheel = (event: WheelEvent) => {
    event.preventDefault();
    state.radius = Math.min(1500, Math.max(25, state.radius * (1 + Math.sign(event.deltaY) * 0.12)));
  };
  const onContext = (event: Event) => event.preventDefault();

  element.addEventListener('pointerdown', onDown);
  element.addEventListener('pointermove', onMove);
  element.addEventListener('pointerup', onUp);
  element.addEventListener('wheel', onWheel, { passive: false });
  element.addEventListener('contextmenu', onContext);

  return {
    ...state,
    update() {
      const sinPolar = Math.sin(this.polar);
      camera.position.set(
        this.target.x + this.radius * sinPolar * Math.cos(this.azimuth),
        this.target.y + this.radius * sinPolar * Math.sin(this.azimuth),
        this.target.z + this.radius * Math.cos(this.polar),
      );
      camera.up.set(0, 0, 1);
      camera.lookAt(this.target);
    },
    dispose() {
      element.removeEventListener('pointerdown', onDown);
      element.removeEventListener('pointermove', onMove);
      element.removeEventListener('pointerup', onUp);
      element.removeEventListener('wheel', onWheel);
      element.removeEventListener('contextmenu', onContext);
    },
  };
}

/**
 * Standard radiological view presets.  The scene axes are: +Z along the sheath
 * (posterior -> anterior for the demo geometry), +X to the patient's left,
 * +Y superior.  The mapping is a convention of the synthetic demo scene and is
 * NOT derived from a patient coordinate system.
 */
function applyPreset(orbit: OrbitState, preset: ViewPreset): void {
  switch (preset) {
    case 'sagittal':
      orbit.azimuth = 0;
      orbit.polar = Math.PI / 2;
      break;
    case 'coronal':
      orbit.azimuth = -Math.PI / 2;
      orbit.polar = Math.PI / 2;
      break;
    case 'axial':
      orbit.azimuth = -Math.PI / 2;
      orbit.polar = 0.08;
      break;
    default:
      // Three-quarter view: the steering plane (X = 0 at zero handle roll) is
      // seen obliquely, so a deflection is immediately visible rather than
      // being foreshortened straight into the camera.
      orbit.azimuth = -0.55;
      orbit.polar = 1.35;
  }
  orbit.radius = 230;
}

export { createSyntheticChamber };
