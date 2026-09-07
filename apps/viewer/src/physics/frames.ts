/**
 * Bishop (rotation-minimising) frame utilities - TypeScript port of
 * `packages/physics-core/src/cathsim_physics/frames.py`.
 *
 * A Bishop frame carries zero twist by construction, so the per-edge angle
 * `phi` is the material twist measured against a twist-free reference.
 *
 * Research prototype - Not for clinical use.
 */

import { nodeCount, type RodState } from './rod';

const EPSILON = 1e-12;

export interface RodFrames {
  /** Unit tangents, flat 3(N-1). */
  tangents: Float64Array;
  /** Bishop directors, flat 3(N-1). */
  d1: Float64Array;
  /** Material director m1 = cos(phi) d1 + sin(phi) d2, flat 3(N-1). */
  m1: Float64Array;
  /** Material director m2 = -sin(phi) d1 + cos(phi) d2, flat 3(N-1). */
  m2: Float64Array;
}

/** Rotate `v` from unit tangent `from` onto unit tangent `to` (Rodrigues). */
export function parallelTransport(
  v: readonly number[],
  from: readonly number[],
  to: readonly number[],
): number[] {
  const ax = from[1] * to[2] - from[2] * to[1];
  const ay = from[2] * to[0] - from[0] * to[2];
  const az = from[0] * to[1] - from[1] * to[0];
  const sin = Math.hypot(ax, ay, az);
  if (sin < EPSILON) return [v[0], v[1], v[2]];
  const cos = from[0] * to[0] + from[1] * to[1] + from[2] * to[2];
  const ux = ax / sin;
  const uy = ay / sin;
  const uz = az / sin;
  const cx = uy * v[2] - uz * v[1];
  const cy = uz * v[0] - ux * v[2];
  const cz = ux * v[1] - uy * v[0];
  const d = (ux * v[0] + uy * v[1] + uz * v[2]) * (1 - cos);
  return [v[0] * cos + cx * sin + ux * d, v[1] * cos + cy * sin + uy * d, v[2] * cos + cz * sin + uz * d];
}

/** Compute tangents, Bishop directors and the material frame of a rod state. */
export function computeFrames(state: RodState): RodFrames {
  const n = nodeCount(state);
  const edges = n - 1;
  const tangents = new Float64Array(3 * edges);
  const d1 = new Float64Array(3 * edges);
  const m1 = new Float64Array(3 * edges);
  const m2 = new Float64Array(3 * edges);
  const x = state.nodesMm;

  for (let j = 0; j < edges; j += 1) {
    const a = 3 * j;
    const b = 3 * (j + 1);
    const ex = x[b] - x[a];
    const ey = x[b + 1] - x[a + 1];
    const ez = x[b + 2] - x[a + 2];
    const len = Math.hypot(ex, ey, ez) || 1;
    tangents[a] = ex / len;
    tangents[a + 1] = ey / len;
    tangents[a + 2] = ez / len;
  }

  // Anchor: orthogonalise the requested director against the first tangent.
  let previous = orthonormalise(
    [state.d1First[0], state.d1First[1], state.d1First[2]],
    [tangents[0], tangents[1], tangents[2]],
  );
  d1.set(previous, 0);
  for (let j = 1; j < edges; j += 1) {
    const from = [tangents[3 * (j - 1)], tangents[3 * (j - 1) + 1], tangents[3 * (j - 1) + 2]];
    const to = [tangents[3 * j], tangents[3 * j + 1], tangents[3 * j + 2]];
    previous = orthonormalise(parallelTransport(previous, from, to), to);
    d1.set(previous, 3 * j);
  }

  for (let j = 0; j < edges; j += 1) {
    const a = 3 * j;
    const tx = tangents[a];
    const ty = tangents[a + 1];
    const tz = tangents[a + 2];
    const d1x = d1[a];
    const d1y = d1[a + 1];
    const d1z = d1[a + 2];
    // d2 = t x d1
    const d2x = ty * d1z - tz * d1y;
    const d2y = tz * d1x - tx * d1z;
    const d2z = tx * d1y - ty * d1x;
    const cos = Math.cos(state.phiRad[j]);
    const sin = Math.sin(state.phiRad[j]);
    m1[a] = cos * d1x + sin * d2x;
    m1[a + 1] = cos * d1y + sin * d2y;
    m1[a + 2] = cos * d1z + sin * d2z;
    m2[a] = -sin * d1x + cos * d2x;
    m2[a + 1] = -sin * d1y + cos * d2y;
    m2[a + 2] = -sin * d1z + cos * d2z;
  }

  return { tangents, d1, m1, m2 };
}

function orthonormalise(v: readonly number[], axis: readonly number[]): number[] {
  const projection = v[0] * axis[0] + v[1] * axis[1] + v[2] * axis[2];
  let px = v[0] - projection * axis[0];
  let py = v[1] - projection * axis[1];
  let pz = v[2] - projection * axis[2];
  let norm = Math.hypot(px, py, pz);
  if (norm < EPSILON) {
    // Degenerate: pick any perpendicular.
    const helper = Math.abs(axis[2]) > 0.9 ? [1, 0, 0] : [0, 0, 1];
    px = axis[1] * helper[2] - axis[2] * helper[1];
    py = axis[2] * helper[0] - axis[0] * helper[2];
    pz = axis[0] * helper[1] - axis[1] * helper[0];
    norm = Math.hypot(px, py, pz);
  }
  return [px / norm, py / norm, pz / norm];
}

/** Quaternion [x,y,z,w] of the frame whose columns are (m1, m2, tangent). */
export function frameToQuaternion(
  m1: readonly number[],
  m2: readonly number[],
  tangent: readonly number[],
): [number, number, number, number] {
  const m00 = m1[0];
  const m10 = m1[1];
  const m20 = m1[2];
  const m01 = m2[0];
  const m11 = m2[1];
  const m21 = m2[2];
  const m02 = tangent[0];
  const m12 = tangent[1];
  const m22 = tangent[2];
  const trace = m00 + m11 + m22;
  let q: [number, number, number, number];
  if (trace > 0) {
    const s = Math.sqrt(trace + 1) * 2;
    q = [(m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s];
  } else if (m00 > m11 && m00 > m22) {
    const s = Math.sqrt(1 + m00 - m11 - m22) * 2;
    q = [0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s];
  } else if (m11 > m22) {
    const s = Math.sqrt(1 + m11 - m00 - m22) * 2;
    q = [(m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s];
  } else {
    const s = Math.sqrt(1 + m22 - m00 - m11) * 2;
    q = [(m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s];
  }
  const norm = Math.hypot(q[0], q[1], q[2], q[3]);
  return [q[0] / norm, q[1] / norm, q[2] / norm, q[3] / norm];
}
