/**
 * Python <-> TypeScript parity and analytical validation of the real-time rod
 * solver.  Golden data comes from `tests/reference-data/rod-reference-cases.json`,
 * produced by the Python reference implementation
 * (`scripts/generate_reference_data.py`).  Tolerances are justified in
 * `docs/validation-plan.md`.
 */

import { describe, expect, it } from 'vitest';
import referenceData from '../../../../tests/reference-data/rod-reference-cases.json';
import demoProfileJson from '../../../../configs/demo-steerable-rf.json';
import uncalibratedProfileJson from '../../../../configs/generic-steerable-rf.json';
import { GenericSteerableRF } from './catheter';
import { type CatheterProfile, ProfileError, calibrationStatus, materialFromProfile } from './profile';
import { energyAndGradient, straightRod, type RodMaterial } from './rod';
import { RodSolver } from './solver';

const demoProfile = demoProfileJson as unknown as CatheterProfile;
const uncalibratedProfile = uncalibratedProfileJson as unknown as CatheterProfile;

// Budget for the validation runs.  The TypeScript L-BFGS reaches the same
// equilibrium as the SciPy reference in far fewer iterations (302 vs 6455 on
// the cantilever), so a 3000-iteration cap is generous rather than tight.
const FINE = { maxIterations: 3000, gradientToleranceN: 1e-8, historySize: 150, maxWallTimeMs: 0 };
/** Fixed-point passes for the rest-curvature loop, and its tolerance. */
const OUTER_PASSES = 14;
const OUTER_TOLERANCE_MM = 1e-5;
/** Vitest timeout for the slow equilibrium runs [ms]. */
const SLOW_MS = 120_000;

interface ReferenceCase {
  name: string;
  input: Record<string, number | number[] | string>;
  expected: Record<string, number | number[] | number[][]>;
}
const cases = referenceData.cases as unknown as ReferenceCase[];
const findCase = (name: string): ReferenceCase => {
  const found = cases.find((entry) => entry.name === name);
  if (!found) throw new Error(`Reference case "${name}" is missing. Regenerate the golden data.`);
  return found;
};

function rmsDifferenceMm(actual: Float64Array, expected: number[][]): number {
  let sum = 0;
  for (let i = 0; i < expected.length; i += 1) {
    const dx = actual[3 * i] - expected[i][0];
    const dy = actual[3 * i + 1] - expected[i][1];
    const dz = actual[3 * i + 2] - expected[i][2];
    sum += dx * dx + dy * dy + dz * dz;
  }
  return Math.sqrt(sum / expected.length);
}

describe('analytic gradient', () => {
  it('matches central finite differences', () => {
    const { state, rest } = straightRod([0, 0, 0], [1, 0, 0], 50, 12);
    // Deterministic pseudo-random perturbation (fixed seed, no RNG dependency).
    let seed = 20260907;
    const next = () => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed / 2147483648 - 0.5;
    };
    for (let i = 0; i < state.nodesMm.length; i += 1) state.nodesMm[i] += next() * 2;
    for (let i = 0; i < state.phiRad.length; i += 1) state.phiRad[i] += next() * 0.6;
    for (let i = 0; i < rest.kb0.length; i += 1) rest.kb0[i] = next() * 0.1;

    const material: RodMaterial = {
      bendingStiffnessNmm2: 120,
      torsionalStiffnessNmm2: 90,
      axialStiffnessN: 4000,
      dampingNsPerMm2: 1,
      torsionalDampingNmmSPerRad: 1,
    };
    const gradNodes = new Float64Array(state.nodesMm.length);
    const gradPhi = new Float64Array(state.phiRad.length);
    energyAndGradient(state, rest, material, undefined, gradNodes, gradPhi);
    const scale = Math.max(...Array.from(gradNodes, Math.abs), ...Array.from(gradPhi, Math.abs));

    const scratchA = new Float64Array(gradNodes.length);
    const scratchB = new Float64Array(gradPhi.length);
    const step = 1e-6;
    let maxError = 0;
    for (let i = 0; i < state.nodesMm.length; i += 1) {
      const original = state.nodesMm[i];
      state.nodesMm[i] = original + step;
      const plus = energyAndGradient(state, rest, material, undefined, scratchA, scratchB).total;
      state.nodesMm[i] = original - step;
      const minus = energyAndGradient(state, rest, material, undefined, scratchA, scratchB).total;
      state.nodesMm[i] = original;
      maxError = Math.max(maxError, Math.abs((plus - minus) / (2 * step) - gradNodes[i]) / scale);
    }
    for (let j = 0; j < state.phiRad.length; j += 1) {
      const original = state.phiRad[j];
      state.phiRad[j] = original + step;
      const plus = energyAndGradient(state, rest, material, undefined, scratchA, scratchB).total;
      state.phiRad[j] = original - step;
      const minus = energyAndGradient(state, rest, material, undefined, scratchA, scratchB).total;
      state.phiRad[j] = original;
      maxError = Math.max(maxError, Math.abs((plus - minus) / (2 * step) - gradPhi[j]) / scale);
    }
    expect(maxError).toBeLessThan(1e-6);
  });
});

describe('cantilever beam (V1)', () => {
  it('reproduces the Euler-Bernoulli tip deflection and the Python reference', () => {
    const reference = findCase('cantilever_tip_load');
    const input = reference.input as unknown as {
      length_mm: number;
      n_nodes: number;
      bending_stiffness_n_mm2: number;
      torsional_stiffness_n_mm2: number;
      axial_stiffness_n: number;
      tip_force_n: number[];
    };
    const { state, rest } = straightRod([0, 0, 0], [1, 0, 0], input.length_mm, input.n_nodes);
    const material: RodMaterial = {
      bendingStiffnessNmm2: input.bending_stiffness_n_mm2,
      torsionalStiffnessNmm2: input.torsional_stiffness_n_mm2,
      axialStiffnessN: input.axial_stiffness_n,
      dampingNsPerMm2: 1e-6,
      torsionalDampingNmmSPerRad: 1e-6,
    };
    const nodeForcesN = new Float64Array(3 * input.n_nodes);
    nodeForcesN[3 * (input.n_nodes - 1) + 2] = input.tip_force_n[2];

    const solver = new RodSolver(material, rest, state, { clampedNodes: [0, 1], clampedEdges: [0] }, FINE);
    const report = solver.solveStatic(state, { nodeForcesN });

    const tipMm = state.nodesMm[3 * input.n_nodes - 1];
    const analyticMm = reference.expected.analytic_tip_deflection_mm as number;
    const pythonMm = reference.expected.tip_deflection_mm as number;
    const elementMm = input.length_mm / (input.n_nodes - 1);
    const correctedAnalyticMm =
      (input.tip_force_n[2] * (input.length_mm - 0.5 * elementMm) ** 3) /
      (3 * input.bending_stiffness_n_mm2);

    // eslint-disable-next-line no-console
    console.log(
      `[V1 cantilever, TS] delta=${tipMm.toFixed(6)} mm  Euler-Bernoulli=${analyticMm.toFixed(6)} mm  ` +
        `raw_err=${((Math.abs(tipMm - analyticMm) / analyticMm) * 100).toFixed(3)} %  ` +
        `clamp_corrected_err=${((Math.abs(tipMm - correctedAnalyticMm) / correctedAnalyticMm) * 100).toFixed(3)} %  ` +
        `residual=${report.residual.toExponential(2)} N`,
    );

    expect(Math.abs(tipMm - correctedAnalyticMm) / correctedAnalyticMm).toBeLessThan(5e-3);
    // Parity with the Python reference on the same discretisation: 1e-4 mm on a
    // ~1 mm deflection, i.e. 0.01 % - far below any modelling uncertainty.
    expect(Math.abs(tipMm - pythonMm)).toBeLessThan(1e-4);
    expect(rmsDifferenceMm(state.nodesMm, reference.expected.centerline_mm as number[][])).toBeLessThan(1e-4);
  }, SLOW_MS);
});

describe('Python <-> TypeScript parity of GenericSteerableRF (V9 analogue)', () => {
  const parityCases = [
    { name: 'steer_x0_y0_roll0_ins80', steerX: 0, steerY: 0, roll: 0, insertion: 80 },
    { name: 'steer_x1_y0_roll0_ins100', steerX: 1, steerY: 0, roll: 0, insertion: 100 },
    { name: 'steer_x0_y-0.6_roll0_ins90', steerX: 0, steerY: -0.6, roll: 0, insertion: 90 },
    { name: 'steer_x1_y0_roll1.5708_ins100', steerX: 1, steerY: 0, roll: Math.PI / 2, insertion: 100 },
  ];

  it.each(parityCases)('matches the reference centreline for $name', (testCase) => {
    const reference = findCase(testCase.name);
    const catheter = new GenericSteerableRF(
      demoProfile,
      true,
      { positionMm: [0, 0, 0], direction: [0, 0, 1], rollReference: [0, 1, 0] },
      FINE,
    );
    catheter.setInsertion(testCase.insertion);
    catheter.setAxialRotation(testCase.roll);
    catheter.setSteering(testCase.steerX, testCase.steerY);
    catheter.solveStatic(OUTER_PASSES, OUTER_TOLERANCE_MM);

    const expected = reference.expected.centerline_mm as number[][];
    expect(catheter.nodes).toBe(expected.length);
    const rms = rmsDifferenceMm(catheter.getRenderGeometry().centerlineMm, expected);
    const tip = expected[expected.length - 1];
    // eslint-disable-next-line no-console
    console.log(
      `[parity] ${testCase.name}: RMS centreline difference = ${rms.toExponential(3)} mm ` +
        `(reference tip = [${tip.map((v) => v.toFixed(3)).join(', ')}] mm)`,
    );
    // Tolerance: 0.01 mm RMS.  The two implementations use different line
    // searches (SciPy's More-Thuente vs the Armijo backtracking here), so they
    // stop at slightly different points on the same very flat energy minimum.
    // The observed differences are 1e-15 .. 1e-4 mm, i.e. three orders of
    // magnitude inside this bound and far below any resolution this prototype
    // could ever be validated against.
    expect(rms).toBeLessThan(0.01);
  }, SLOW_MS);
});

describe('actuation behaviour', () => {
  const BEHAVIOUR = { maxIterations: 1500, gradientToleranceN: 1e-7, historySize: 150, maxWallTimeMs: 0 };
  const makeCatheter = () =>
    new GenericSteerableRF(
      demoProfile,
      true,
      { positionMm: [0, 0, 0], direction: [0, 0, 1], rollReference: [0, 1, 0] },
      BEHAVIOUR,
    );

  it('keeps an unsteered catheter straight', () => {
    const catheter = makeCatheter();
    catheter.setInsertion(80);
    catheter.solveStatic();
    const nodes = catheter.getRenderGeometry().centerlineMm;
    let maxLateral = 0;
    for (let i = 0; i < catheter.nodes; i += 1) {
      maxLateral = Math.max(maxLateral, Math.hypot(nodes[3 * i], nodes[3 * i + 1]));
    }
    expect(maxLateral).toBeLessThan(1e-6);
  });

  it('bends only the distal active length', () => {
    const catheter = makeCatheter();
    catheter.setInsertion(100);
    catheter.setSteering(1, 0);
    catheter.solveStatic();
    const nodes = catheter.getRenderGeometry().centerlineMm;
    const elementMm = 100 / (catheter.nodes - 1);
    const passiveNodes = Math.floor((100 - demoProfile.geometry.active_length_mm) / elementMm) - 2;
    let maxProximalLateral = 0;
    for (let i = 0; i <= passiveNodes; i += 1) {
      maxProximalLateral = Math.max(maxProximalLateral, Math.hypot(nodes[3 * i], nodes[3 * i + 1]));
    }
    const tipLateral = Math.hypot(nodes[3 * catheter.nodes - 3], nodes[3 * catheter.nodes - 2]);
    expect(maxProximalLateral).toBeLessThan(1e-6);
    expect(tipLateral).toBeGreaterThan(0.1 * demoProfile.geometry.active_length_mm);
  });

  it('reaches the tip turn angle implied by the configured steering gain', () => {
    const catheter = makeCatheter();
    catheter.setInsertion(100);
    catheter.setSteering(1, 0);
    catheter.solveStatic();
    const nodes = catheter.getRenderGeometry().centerlineMm;
    const n = catheter.nodes;
    const tangent = [
      nodes[3 * n - 3] - nodes[3 * n - 6],
      nodes[3 * n - 2] - nodes[3 * n - 5],
      nodes[3 * n - 1] - nodes[3 * n - 4],
    ];
    const norm = Math.hypot(...tangent);
    const turnRad = Math.acos(tangent[2] / norm);
    const expectedRad =
      (demoProfile.actuation.steer_gain_rad_per_mm as number) *
      demoProfile.geometry.active_length_mm;
    expect(Math.abs(turnRad - expectedRad) / expectedRad).toBeLessThan(0.05);
  });

  it('conserves arclength when the insertion changes', () => {
    const catheter = makeCatheter();
    for (const insertionMm of [40, 80, 120]) {
      catheter.setInsertion(insertionMm);
      catheter.solveStatic();
      const nodes = catheter.getRenderGeometry().centerlineMm;
      let arclengthMm = 0;
      for (let i = 1; i < catheter.nodes; i += 1) {
        arclengthMm += Math.hypot(
          nodes[3 * i] - nodes[3 * i - 3],
          nodes[3 * i + 1] - nodes[3 * i - 2],
          nodes[3 * i + 2] - nodes[3 * i - 1],
        );
      }
      expect(arclengthMm).toBeCloseTo(insertionMm, 1);
    }
  });

  it('rejects non-finite actuation input', () => {
    const catheter = makeCatheter();
    expect(() => catheter.setInsertion(Number.NaN)).toThrow(/NaN or Inf/);
  });

  it('clamps steering input to the configured range', () => {
    const catheter = makeCatheter();
    catheter.setActuation({ steerX: 5, steerY: -3, deployment: 2 });
    expect(catheter.actuationInput.steerX).toBe(1);
    expect(catheter.actuationInput.steerY).toBe(-1);
    expect(catheter.actuationInput.deployment).toBe(1);
  });

  it('rejects an invalid time step', () => {
    const catheter = makeCatheter();
    expect(() => catheter.step(0)).toThrow(/positive finite/);
    expect(() => catheter.step(Number.NaN)).toThrow(/positive finite/);
  });

  it('emits unit quaternions and the full SimulationFrame contract', () => {
    const catheter = makeCatheter();
    catheter.setInsertion(80);
    catheter.step(1 / 60);
    const frame = catheter.getRenderGeometry();
    expect(frame.centerlineMm.length).toBe(3 * catheter.nodes);
    expect(frame.orientationsXyzw.length).toBe(4 * (catheter.nodes - 1));
    expect(frame.electrodes).toHaveLength(demoProfile.electrodes?.count ?? 0);
    expect(frame.solver).toHaveProperty('maxPenetrationMm');
    for (let j = 0; j < catheter.nodes - 1; j += 1) {
      const norm = Math.hypot(
        frame.orientationsXyzw[4 * j],
        frame.orientationsXyzw[4 * j + 1],
        frame.orientationsXyzw[4 * j + 2],
        frame.orientationsXyzw[4 * j + 3],
      );
      expect(norm).toBeCloseTo(1, 9);
    }
  });
});

describe('calibration gate', () => {
  it('blocks simulation on an uncalibrated profile', () => {
    const status = calibrationStatus(uncalibratedProfile);
    expect(status.readyForSimulation).toBe(false);
    expect(status.materialSource).toBe('CALIBRATION_REQUIRED');
    expect(() => materialFromProfile(uncalibratedProfile, true)).toThrow(ProfileError);
  });

  it('requires explicit consent for a demo profile', () => {
    expect(() => materialFromProfile(demoProfile, false)).toThrow(/DEMO/);
    expect(materialFromProfile(demoProfile, true).bendingStiffnessNmm2).toBeGreaterThan(0);
  });

  it('rejects an unknown schema version', () => {
    const bad = { ...demoProfile, schema_version: '9.9.9' };
    expect(() => materialFromProfile(bad, true)).toThrow(/schema_version/);
  });
});
