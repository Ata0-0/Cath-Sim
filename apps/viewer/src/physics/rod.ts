/**
 * Discrete elastic rod - real-time TypeScript port of the Python reference
 * implementation in `packages/physics-core/src/cathsim_physics/rod.py`.
 *
 * The two implementations share the same discrete energy, the same analytic
 * gradient and the same over-damped implicit time integration, so their
 * results can be compared node-by-node.  `rod.parity.test.ts` replays the
 * golden cases in `tests/reference-data/` against this code; that check is the
 * Python <-> TypeScript counterpart of the Python <-> C++ parity test planned
 * for Milestone 3.
 *
 * Units: mm, s, N, rad. Energy is in N mm.
 *
 * Research prototype - Not for clinical use.
 */

/** Constitutive parameters of the rod. See `RodMaterial` in the Python core. */
export interface RodMaterial {
  /** EI [N mm^2] */
  bendingStiffnessNmm2: number;
  /** GJ [N mm^2] */
  torsionalStiffnessNmm2: number;
  /** EA [N] */
  axialStiffnessN: number;
  /** Translational viscous damping per unit length [N s / mm^2]. */
  dampingNsPerMm2: number;
  /** Torsional viscous damping per unit length [N mm s / rad / mm]. */
  torsionalDampingNmmSPerRad: number;
}

/** Kinematic state: node positions [mm] and one twist angle per edge [rad]. */
export interface RodState {
  /** Flat array of length 3N. */
  nodesMm: Float64Array;
  /** Length N-1. */
  phiRad: Float64Array;
  /** Bishop anchor director of edge 0, length 3. */
  d1First: Float64Array;
}

/** Undeformed configuration. */
export interface RodRest {
  /** Length N-1 [mm]. */
  edgeLengthsMm: Float64Array;
  /** Rest curvature binormal at interior nodes, flat array of length 3(N-2). */
  kb0: Float64Array;
  /** Rest twist increment per interior node, length N-2 [rad]. */
  dphi0Rad: Float64Array;
}

/** Optional external loads. */
export interface ExternalLoads {
  /** Flat 3N array [N]. */
  nodeForcesN?: Float64Array;
  /** Length N-1 [N mm]. */
  edgeTorquesNmm?: Float64Array;
}

export interface EnergyBreakdown {
  stretch: number;
  bend: number;
  twist: number;
  external: number;
  total: number;
}

const EPSILON = 1e-12;

export class RodGeometryError extends Error {}

export function nodeCount(state: RodState): number {
  return state.nodesMm.length / 3;
}

/** Voronoi length of every interior node [mm], length N-2. */
export function voronoiLengths(rest: RodRest): Float64Array {
  const count = rest.edgeLengthsMm.length - 1;
  const out = new Float64Array(count);
  for (let i = 0; i < count; i += 1) {
    out[i] = 0.5 * (rest.edgeLengthsMm[i] + rest.edgeLengthsMm[i + 1]);
  }
  return out;
}

/**
 * Total energy [N mm] and its analytic gradient.
 *
 * `gradNodes` is filled with dE/dx [N] (flat 3N) and `gradPhi` with
 * dE/dphi [N mm] (length N-1). Both are overwritten, not accumulated.
 */
export function energyAndGradient(
  state: RodState,
  rest: RodRest,
  material: RodMaterial,
  loads: ExternalLoads | undefined,
  gradNodes: Float64Array,
  gradPhi: Float64Array,
): EnergyBreakdown {
  const x = state.nodesMm;
  const phi = state.phiRad;
  const n = nodeCount(state);
  const edges = n - 1;

  gradNodes.fill(0);
  gradPhi.fill(0);

  let stretchEnergy = 0;
  let bendEnergy = 0;
  let twistEnergy = 0;
  let externalEnergy = 0;

  // Edge vectors, lengths and unit tangents.
  const edgeVec = new Float64Array(3 * edges);
  const edgeLen = new Float64Array(edges);
  const tangent = new Float64Array(3 * edges);
  for (let j = 0; j < edges; j += 1) {
    const a = 3 * j;
    const b = 3 * (j + 1);
    const ex = x[b] - x[a];
    const ey = x[b + 1] - x[a + 1];
    const ez = x[b + 2] - x[a + 2];
    const len = Math.hypot(ex, ey, ez);
    if (!(len > EPSILON)) {
      throw new RodGeometryError(
        `Two neighbouring rod nodes collapsed at edge ${j} (zero length). ` +
          'Increase the axial stiffness EA or reduce the time step.',
      );
    }
    edgeVec[a] = ex;
    edgeVec[a + 1] = ey;
    edgeVec[a + 2] = ez;
    edgeLen[j] = len;
    tangent[a] = ex / len;
    tangent[a + 1] = ey / len;
    tangent[a + 2] = ez / len;

    // --- axial stretch: E = 1/2 EA (l/l0 - 1)^2 l0
    const strain = len / rest.edgeLengthsMm[j] - 1;
    stretchEnergy += 0.5 * material.axialStiffnessN * strain * strain * rest.edgeLengthsMm[j];
    const force = material.axialStiffnessN * strain; // [N]
    for (let k = 0; k < 3; k += 1) {
      const contribution = force * tangent[a + k];
      gradNodes[b + k] += contribution;
      gradNodes[a + k] -= contribution;
    }
  }

  // --- bending: E = EI / (2 lbar) |kb - kb0|^2
  const voronoi = voronoiLengths(rest);
  for (let i = 0; i < n - 2; i += 1) {
    const e0 = 3 * i;
    const e1 = 3 * (i + 1);
    const n0 = edgeLen[i];
    const n1 = edgeLen[i + 1];
    const dot =
      edgeVec[e0] * edgeVec[e1] +
      edgeVec[e0 + 1] * edgeVec[e1 + 1] +
      edgeVec[e0 + 2] * edgeVec[e1 + 2];
    const denominator = n0 * n1 + dot;
    if (!(denominator > EPSILON)) {
      throw new RodGeometryError(
        `Rod folded back on itself at node ${i + 1} (turning angle reached 180 deg). ` +
          'Reduce the time step or the steering input.',
      );
    }
    // kb = 2 e0 x e1 / denominator
    const cx = edgeVec[e0 + 1] * edgeVec[e1 + 2] - edgeVec[e0 + 2] * edgeVec[e1 + 1];
    const cy = edgeVec[e0 + 2] * edgeVec[e1] - edgeVec[e0] * edgeVec[e1 + 2];
    const cz = edgeVec[e0] * edgeVec[e1 + 1] - edgeVec[e0 + 1] * edgeVec[e1];
    const kbx = (2 * cx) / denominator;
    const kby = (2 * cy) / denominator;
    const kbz = (2 * cz) / denominator;

    const dkbx = kbx - rest.kb0[3 * i];
    const dkby = kby - rest.kb0[3 * i + 1];
    const dkbz = kbz - rest.kb0[3 * i + 2];

    const coefficient = material.bendingStiffnessNmm2 / voronoi[i]; // [N mm]
    bendEnergy += 0.5 * coefficient * (dkbx * dkbx + dkby * dkby + dkbz * dkbz);

    // w = dE/dkb
    const wx = coefficient * dkbx;
    const wy = coefficient * dkby;
    const wz = coefficient * dkbz;
    const wDotKb = wx * kbx + wy * kby + wz * kbz;

    // w^T dkb/de0 = (-2 (w x e1) - (w.kb) (n1 t0 + e1)) / denominator
    const wxe1x = wy * edgeVec[e1 + 2] - wz * edgeVec[e1 + 1];
    const wxe1y = wz * edgeVec[e1] - wx * edgeVec[e1 + 2];
    const wxe1z = wx * edgeVec[e1 + 1] - wy * edgeVec[e1];
    const a0x = (-2 * wxe1x - wDotKb * (n1 * tangent[e0] + edgeVec[e1])) / denominator;
    const a0y = (-2 * wxe1y - wDotKb * (n1 * tangent[e0 + 1] + edgeVec[e1 + 1])) / denominator;
    const a0z = (-2 * wxe1z - wDotKb * (n1 * tangent[e0 + 2] + edgeVec[e1 + 2])) / denominator;

    // w^T dkb/de1 = ( 2 (w x e0) - (w.kb) (n0 t1 + e0)) / denominator
    const wxe0x = wy * edgeVec[e0 + 2] - wz * edgeVec[e0 + 1];
    const wxe0y = wz * edgeVec[e0] - wx * edgeVec[e0 + 2];
    const wxe0z = wx * edgeVec[e0 + 1] - wy * edgeVec[e0];
    const a1x = (2 * wxe0x - wDotKb * (n0 * tangent[e1] + edgeVec[e0])) / denominator;
    const a1y = (2 * wxe0y - wDotKb * (n0 * tangent[e1 + 1] + edgeVec[e0 + 1])) / denominator;
    const a1z = (2 * wxe0z - wDotKb * (n0 * tangent[e1 + 2] + edgeVec[e0 + 2])) / denominator;

    const p0 = 3 * i;
    const p1 = 3 * (i + 1);
    const p2 = 3 * (i + 2);
    gradNodes[p0] -= a0x;
    gradNodes[p0 + 1] -= a0y;
    gradNodes[p0 + 2] -= a0z;
    gradNodes[p1] += a0x - a1x;
    gradNodes[p1 + 1] += a0y - a1y;
    gradNodes[p1 + 2] += a0z - a1z;
    gradNodes[p2] += a1x;
    gradNodes[p2 + 1] += a1y;
    gradNodes[p2 + 2] += a1z;

    // --- twist: E = GJ / (2 lbar) (dphi - dphi0)^2
    const twistIncrement = phi[i + 1] - phi[i] - rest.dphi0Rad[i];
    const twistCoefficient = material.torsionalStiffnessNmm2 / voronoi[i]; // [N mm]
    twistEnergy += 0.5 * twistCoefficient * twistIncrement * twistIncrement;
    const moment = twistCoefficient * twistIncrement;
    gradPhi[i + 1] += moment;
    gradPhi[i] -= moment;
  }

  // --- external loads
  if (loads?.nodeForcesN) {
    for (let index = 0; index < 3 * n; index += 1) {
      externalEnergy -= loads.nodeForcesN[index] * x[index];
      gradNodes[index] -= loads.nodeForcesN[index];
    }
  }
  if (loads?.edgeTorquesNmm) {
    for (let j = 0; j < edges; j += 1) {
      externalEnergy -= loads.edgeTorquesNmm[j] * phi[j];
      gradPhi[j] -= loads.edgeTorquesNmm[j];
    }
  }

  const total = stretchEnergy + bendEnergy + twistEnergy + externalEnergy;
  if (!Number.isFinite(total)) {
    throw new RodGeometryError(
      'Non-finite energy (NaN/Inf). The solver was stopped to avoid producing ' +
        'meaningless geometry. Check the parameter profile and the time step.',
    );
  }
  return { stretch: stretchEnergy, bend: bendEnergy, twist: twistEnergy, external: externalEnergy, total };
}

/** Build a straight, untwisted rod. Mirrors `straight_rod` in the Python core. */
export function straightRod(
  originMm: readonly number[],
  direction: readonly number[],
  totalLengthMm: number,
  nNodes: number,
  d1First?: readonly number[],
): { state: RodState; rest: RodRest } {
  if (nNodes < 3) throw new RodGeometryError('A discrete elastic rod needs at least 3 nodes.');
  if (!(totalLengthMm > 0)) throw new RodGeometryError('totalLengthMm must be positive.');
  const norm = Math.hypot(direction[0], direction[1], direction[2]);
  if (!(norm > EPSILON)) throw new RodGeometryError('direction must be a non-zero vector.');
  const unit = [direction[0] / norm, direction[1] / norm, direction[2] / norm];

  const nodesMm = new Float64Array(3 * nNodes);
  for (let i = 0; i < nNodes; i += 1) {
    const s = (totalLengthMm * i) / (nNodes - 1);
    nodesMm[3 * i] = originMm[0] + s * unit[0];
    nodesMm[3 * i + 1] = originMm[1] + s * unit[1];
    nodesMm[3 * i + 2] = originMm[2] + s * unit[2];
  }
  const edgeLengthsMm = new Float64Array(nNodes - 1).fill(totalLengthMm / (nNodes - 1));
  return {
    state: {
      nodesMm,
      phiRad: new Float64Array(nNodes - 1),
      d1First: Float64Array.from(d1First ?? anyPerpendicular(unit)),
    },
    rest: {
      edgeLengthsMm,
      kb0: new Float64Array(3 * (nNodes - 2)),
      dphi0Rad: new Float64Array(nNodes - 2),
    },
  };
}

/** An arbitrary unit vector perpendicular to `tangent`. */
export function anyPerpendicular(tangent: readonly number[]): number[] {
  const helper = Math.abs(tangent[2]) > 0.9 ? [1, 0, 0] : [0, 0, 1];
  const cx = tangent[1] * helper[2] - tangent[2] * helper[1];
  const cy = tangent[2] * helper[0] - tangent[0] * helper[2];
  const cz = tangent[0] * helper[1] - tangent[1] * helper[0];
  const norm = Math.hypot(cx, cy, cz);
  return [cx / norm, cy / norm, cz / norm];
}
