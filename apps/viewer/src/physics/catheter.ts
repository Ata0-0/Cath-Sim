/**
 * GenericSteerableRF - TypeScript port of the Python reference catheter model.
 *
 * NOT a model of any specific commercial device.  All geometry, material and
 * actuation numbers come from the parameter profile that is loaded at runtime;
 * a profile with uncalibrated (`null`) physics values is refused.
 *
 * Research prototype - Not for clinical use.
 */

import { computeFrames, frameToQuaternion } from './frames';
import {
  type RodMaterial,
  type RodRest,
  type RodState,
  nodeCount,
  straightRod,
  voronoiLengths,
} from './rod';
import { DEFAULT_SETTINGS, RodSolver, type SolverReport, type SolverSettings } from './solver';
import { type CatheterProfile, materialFromProfile } from './profile';

export interface EntryPose {
  positionMm: [number, number, number];
  direction: [number, number, number];
  rollReference: [number, number, number];
}

export interface ActuationInput {
  insertionMm: number;
  axialRotationRad: number;
  steerX: number;
  steerY: number;
  deployment: number;
}

export interface ElectrodePose {
  index: number;
  arclengthMm: number;
  positionMm: [number, number, number];
  orientationXyzw: [number, number, number, number];
}

/** One simulation frame, matching the shared `SimulationFrame` schema. */
export interface SimulationFrame {
  timeS: number;
  centerlineMm: Float64Array;
  orientationsXyzw: Float64Array;
  radiusMm: number;
  electrodes: ElectrodePose[];
  contacts: never[];
  solver: {
    iterations: number;
    residual: number;
    maxPenetrationMm: number;
    converged: boolean;
    wallTimeMs: number;
    energyNmm: { stretch: number; bend: number; twist: number; total: number };
  };
}

export const DEFAULT_ENTRY_POSE: EntryPose = {
  positionMm: [0, 0, 0],
  direction: [0, 0, 1],
  rollReference: [0, 1, 0],
};

export class GenericSteerableRF {
  private state: RodState;

  private rest: RodRest;

  private solver: RodSolver;

  private timeS = 0;

  private lastReport: SolverReport | null = null;

  private actuation: ActuationInput = {
    insertionMm: 80,
    axialRotationRad: 0,
    steerX: 0,
    steerY: 0,
    deployment: 0,
  };

  readonly material: RodMaterial;

  constructor(
    readonly profile: CatheterProfile,
    acceptDemoParameters: boolean,
    private entry: EntryPose = DEFAULT_ENTRY_POSE,
    settings: SolverSettings = DEFAULT_SETTINGS,
  ) {
    this.material = materialFromProfile(profile, acceptDemoParameters);
    const spacingMm = profile.geometry.node_spacing_mm;
    const workingMm = profile.geometry.working_length_mm ?? profile.geometry.active_length_mm * 2;
    const nNodes = Math.max(5, Math.round(workingMm / spacingMm) + 1);
    const built = straightRod(
      entry.positionMm,
      entry.direction,
      Math.max(this.actuation.insertionMm, 1),
      nNodes,
      entry.rollReference,
    );
    this.state = built.state;
    this.rest = built.rest;
    this.solver = new RodSolver(
      this.material,
      this.rest,
      this.state,
      { clampedNodes: [0, 1], clampedEdges: [0] },
      settings,
    );
    this.applyBoundaryAndRest();
  }

  /** Swap the solver budget (e.g. the low-quality preset) at run time. */
  setSolverSettings(settings: SolverSettings): void {
    this.solver.settings = settings;
  }

  get nodes(): number {
    return nodeCount(this.state);
  }

  get simulationTimeS(): number {
    return this.timeS;
  }

  get actuationInput(): Readonly<ActuationInput> {
    return this.actuation;
  }

  /** Clamp and validate an actuation record, then apply it. */
  setActuation(next: Partial<ActuationInput>): void {
    const limit = this.profile.actuation.max_steering_input ?? 1;
    const merged = { ...this.actuation, ...next };
    const values = [
      merged.insertionMm,
      merged.axialRotationRad,
      merged.steerX,
      merged.steerY,
      merged.deployment,
    ];
    if (values.some((value) => !Number.isFinite(value))) {
      throw new Error(
        'Actuation input contains NaN or Inf. Check the control that produced ' +
          'the insertion / rotation / steering value.',
      );
    }
    this.actuation = {
      insertionMm: Math.max(0, merged.insertionMm),
      axialRotationRad: merged.axialRotationRad,
      steerX: clamp(merged.steerX, -limit, limit),
      steerY: clamp(merged.steerY, -limit, limit),
      deployment: clamp(merged.deployment, 0, 1),
    };
    this.applyBoundaryAndRest();
  }

  setInsertion(mm: number): void {
    this.setActuation({ insertionMm: mm });
  }

  setAxialRotation(rad: number): void {
    this.setActuation({ axialRotationRad: rad });
  }

  setSteering(x: number, y: number): void {
    this.setActuation({ steerX: x, steerY: y });
  }

  setDeployment(value: number): void {
    this.setActuation({ deployment: value });
  }

  /** Advance the over-damped rod dynamics by `dtS` seconds. */
  step(dtS: number): void {
    this.applyBoundaryAndRest();
    this.lastReport = this.solver.step(this.state, dtS);
    this.timeS += dtS;
  }

  /**
   * Relax to equilibrium, iterating the rest-curvature fixed point.
   * Returns the number of passes performed.
   */
  solveStatic(maxOuterIterations = 12, toleranceMm = 1e-4): number {
    const previous = new Float64Array(this.state.nodesMm.length);
    for (let iteration = 1; iteration <= maxOuterIterations; iteration += 1) {
      this.applyBoundaryAndRest();
      const kb0Used = Float64Array.from(this.rest.kb0);
      previous.set(this.state.nodesMm);
      this.lastReport = this.solver.solveStatic(this.state);
      let movementMm = 0;
      for (let i = 0; i < previous.length; i += 1) {
        movementMm = Math.max(movementMm, Math.abs(this.state.nodesMm[i] - previous[i]));
      }
      this.updateRestCurvature();
      let curvatureChange = 0;
      for (let i = 0; i < kb0Used.length; i += 1) {
        curvatureChange = Math.max(curvatureChange, Math.abs(this.rest.kb0[i] - kb0Used[i]));
      }
      if (movementMm <= toleranceMm && curvatureChange <= 1e-6) return iteration;
    }
    return maxOuterIterations;
  }

  reset(): void {
    const built = straightRod(
      this.entry.positionMm,
      this.entry.direction,
      Math.max(this.actuation.insertionMm, 1),
      this.nodes,
      this.entry.rollReference,
    );
    this.state.nodesMm.set(built.state.nodesMm);
    this.state.phiRad.set(built.state.phiRad);
    this.rest.edgeLengthsMm.set(built.rest.edgeLengthsMm);
    this.timeS = 0;
    this.lastReport = null;
    this.solver.resetHistory();
    this.applyBoundaryAndRest();
  }

  // -- boundary conditions and rest curvature ---------------------------

  /**
   * Refresh rest lengths (insertion), the proximal clamp (rotation) and the
   * rest curvature (steering).  See the Python reference for the derivation.
   */
  private applyBoundaryAndRest(): void {
    const spacingMm = this.profile.geometry.node_spacing_mm;
    const deployedMm = Math.max(this.actuation.insertionMm, 2 * spacingMm);
    const edges = this.rest.edgeLengthsMm.length;
    const edgeLengthMm = deployedMm / edges;
    if (Math.abs(edgeLengthMm - this.rest.edgeLengthsMm[0]) > 1e-12) {
      this.feedThroughSheath(deployedMm);
      this.rest.edgeLengthsMm.fill(edgeLengthMm);
    }

    const direction = normalise(this.entry.direction);
    this.state.nodesMm[0] = this.entry.positionMm[0];
    this.state.nodesMm[1] = this.entry.positionMm[1];
    this.state.nodesMm[2] = this.entry.positionMm[2];
    this.state.nodesMm[3] = this.entry.positionMm[0] + edgeLengthMm * direction[0];
    this.state.nodesMm[4] = this.entry.positionMm[1] + edgeLengthMm * direction[1];
    this.state.nodesMm[5] = this.entry.positionMm[2] + edgeLengthMm * direction[2];
    this.state.phiRad[0] = this.actuation.axialRotationRad;

    this.updateRestCurvature();
  }

  /**
   * Arclength re-parameterisation for insert / retract.  New material appears
   * beyond the tip along the tip tangent; retraction pulls the tip back along
   * the path the catheter already occupies.  Leaving the nodes in place and
   * only changing the rest lengths would inject a large artificial axial
   * strain and fold the solver.
   */
  private feedThroughSheath(deployedMm: number): void {
    const n = this.nodes;
    const x = this.state.nodesMm;
    const arclength = new Float64Array(n);
    for (let i = 1; i < n; i += 1) {
      arclength[i] =
        arclength[i - 1] +
        Math.hypot(x[3 * i] - x[3 * i - 3], x[3 * i + 1] - x[3 * i - 2], x[3 * i + 2] - x[3 * i - 1]);
    }
    const currentMm = arclength[n - 1];

    // Source polyline, extended straight along the tip tangent if needed.
    const sourceS: number[] = Array.from(arclength);
    const sourceX: number[] = Array.from(x);
    if (deployedMm > currentMm) {
      const tip = [x[3 * n - 3], x[3 * n - 2], x[3 * n - 1]];
      const previousNode = [x[3 * n - 6], x[3 * n - 5], x[3 * n - 4]];
      const tangent = normalise([
        tip[0] - previousNode[0],
        tip[1] - previousNode[1],
        tip[2] - previousNode[2],
      ]);
      const extra = deployedMm - currentMm;
      sourceX.push(tip[0] + extra * tangent[0], tip[1] + extra * tangent[1], tip[2] + extra * tangent[2]);
      sourceS.push(deployedMm);
    }

    const targets = new Float64Array(n);
    for (let i = 0; i < n; i += 1) targets[i] = (deployedMm * i) / (n - 1);
    for (let i = 0; i < n; i += 1) {
      const [lower, fraction] = locate(sourceS, targets[i]);
      for (let k = 0; k < 3; k += 1) {
        x[3 * i + k] =
          (1 - fraction) * sourceX[3 * lower + k] + fraction * sourceX[3 * (lower + 1) + k];
      }
    }

    // Resample the per-edge twist angle at the new edge midpoints.
    const oldMid: number[] = [];
    for (let j = 0; j + 1 < sourceS.length; j += 1) oldMid.push(0.5 * (sourceS[j] + sourceS[j + 1]));
    const oldPhi = Array.from(this.state.phiRad);
    while (oldPhi.length < oldMid.length) oldPhi.push(oldPhi[oldPhi.length - 1] ?? 0);
    for (let j = 0; j + 1 < n; j += 1) {
      const mid = 0.5 * (targets[j] + targets[j + 1]);
      const [lower, fraction] = locate(oldMid, mid);
      this.state.phiRad[j] = (1 - fraction) * oldPhi[lower] + fraction * oldPhi[lower + 1];
    }
  }

  /**
   * Write the steering command into the rest curvature `kb0`.
   *
   *   curvature0 [1/mm] = steer_gain_rad_per_mm * |steer|
   *   bend direction    = cos(psi) m1 + sin(psi) m2,  psi = atan2(steerY, steerX)
   *   kb0_i             = curvature0 * lbar_i * (t_i x bendDirection)
   *
   * Only the distal `active_length_mm` is actuated.  The knob never moves the
   * tip directly - it changes the rod's rest state and the solver decides the
   * resulting shape.
   */
  private updateRestCurvature(): void {
    this.rest.kb0.fill(0);
    this.rest.dphi0Rad.fill(0);
    const gain = this.profile.actuation.steer_gain_rad_per_mm;
    if (gain === null || gain === undefined) {
      throw new Error(
        'actuation.steer_gain_rad_per_mm is CALIBRATION_REQUIRED; the steering ' +
          'command cannot be converted into a rest curvature.',
      );
    }
    const magnitude = Math.hypot(this.actuation.steerX, this.actuation.steerY);
    if (magnitude <= 0) return;

    const frames = computeFrames(this.state);
    const psi = Math.atan2(this.actuation.steerY, this.actuation.steerX);
    const cos = Math.cos(psi);
    const sin = Math.sin(psi);
    const voronoi = voronoiLengths(this.rest);
    const edgeLengthMm = this.rest.edgeLengthsMm[0];
    const activeMm = this.profile.geometry.active_length_mm;
    const n = this.nodes;
    const curvature0 = gain * magnitude;

    // Binormal per edge: t x (cos psi m1 + sin psi m2)
    const binormal = new Float64Array(frames.tangents.length);
    for (let j = 0; j < frames.tangents.length / 3; j += 1) {
      const a = 3 * j;
      const bx = cos * frames.m1[a] + sin * frames.m2[a];
      const by = cos * frames.m1[a + 1] + sin * frames.m2[a + 1];
      const bz = cos * frames.m1[a + 2] + sin * frames.m2[a + 2];
      binormal[a] = frames.tangents[a + 1] * bz - frames.tangents[a + 2] * by;
      binormal[a + 1] = frames.tangents[a + 2] * bx - frames.tangents[a] * bz;
      binormal[a + 2] = frames.tangents[a] * by - frames.tangents[a + 1] * bx;
    }

    for (let i = 1; i <= n - 2; i += 1) {
      const arclengthFromTipMm = (n - 1 - i) * edgeLengthMm;
      if (arclengthFromTipMm > activeMm) continue;
      const scale = curvature0 * voronoi[i - 1];
      for (let k = 0; k < 3; k += 1) {
        this.rest.kb0[3 * (i - 1) + k] =
          scale * 0.5 * (binormal[3 * (i - 1) + k] + binormal[3 * i + k]);
      }
    }
  }

  // -- outputs ----------------------------------------------------------

  getRenderGeometry(): SimulationFrame {
    const frames = computeFrames(this.state);
    const edges = this.nodes - 1;
    const orientations = new Float64Array(4 * edges);
    for (let j = 0; j < edges; j += 1) {
      const a = 3 * j;
      const q = frameToQuaternion(
        [frames.m1[a], frames.m1[a + 1], frames.m1[a + 2]],
        [frames.m2[a], frames.m2[a + 1], frames.m2[a + 2]],
        [frames.tangents[a], frames.tangents[a + 1], frames.tangents[a + 2]],
      );
      orientations.set(q, 4 * j);
    }
    const report = this.lastReport;
    return {
      timeS: this.timeS,
      centerlineMm: this.state.nodesMm,
      orientationsXyzw: orientations,
      radiusMm: this.profile.contact.catheter_collision_radius_mm,
      electrodes: this.getElectrodePoses(orientations),
      contacts: [],
      solver: {
        iterations: report?.iterations ?? 0,
        residual: report?.residual ?? 0,
        maxPenetrationMm: report?.maxPenetrationMm ?? 0,
        converged: report?.converged ?? true,
        wallTimeMs: report?.wallTimeMs ?? 0,
        energyNmm: {
          stretch: report?.energy.stretch ?? 0,
          bend: report?.energy.bend ?? 0,
          twist: report?.energy.twist ?? 0,
          total: report?.energy.total ?? 0,
        },
      },
    };
  }

  getElectrodePoses(orientations?: Float64Array): ElectrodePose[] {
    const offsets = this.profile.electrodes?.arclength_from_tip_mm ?? [];
    if (offsets.length === 0) return [];
    const quaternions = orientations ?? this.getRenderGeometry().orientationsXyzw;
    const n = this.nodes;
    const edgeLengthMm = this.rest.edgeLengthsMm[0];
    const totalMm = edgeLengthMm * (n - 1);
    return offsets.map((offsetMm, index) => {
      const arclengthMm = clamp(totalMm - offsetMm, 0, totalMm);
      const position = arclengthMm / edgeLengthMm;
      const lower = Math.min(Math.max(Math.floor(position), 0), n - 2);
      const fraction = position - lower;
      const x = this.state.nodesMm;
      const point: [number, number, number] = [0, 0, 0];
      for (let k = 0; k < 3; k += 1) {
        point[k] = (1 - fraction) * x[3 * lower + k] + fraction * x[3 * (lower + 1) + k];
      }
      return {
        index,
        arclengthMm,
        positionMm: point,
        orientationXyzw: [
          quaternions[4 * lower],
          quaternions[4 * lower + 1],
          quaternions[4 * lower + 2],
          quaternions[4 * lower + 3],
        ],
      };
    });
  }

  /** Contact metrics. Empty until Milestone 2 adds the mesh contact stage. */
  getContactMetrics(): { available: false; reason: string; maxPenetrationMm: 0; contactCount: 0 } {
    return {
      available: false,
      reason: 'Mesh contact is implemented in Milestone 2.',
      maxPenetrationMm: 0,
      contactCount: 0,
    };
  }
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), high);
}

function normalise(v: readonly number[]): [number, number, number] {
  const norm = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / norm, v[1] / norm, v[2] / norm];
}

/** Index of the interval containing `target` in the sorted array, plus the local fraction. */
function locate(sorted: readonly number[], target: number): [number, number] {
  let lower = 0;
  let upper = sorted.length - 1;
  while (upper - lower > 1) {
    const middle = (lower + upper) >> 1;
    if (sorted[middle] <= target) lower = middle;
    else upper = middle;
  }
  const span = sorted[lower + 1] - sorted[lower];
  const fraction = span > 0 ? (target - sorted[lower]) / span : 0;
  return [lower, Math.min(Math.max(fraction, 0), 1)];
}
