/**
 * Application state (Zustand).
 *
 * This store owns *UI and control* state only.  The rod state lives inside the
 * `GenericSteerableRF` instance held by the simulation loop, so that the
 * physics layer never depends on React and the UI never mutates centreline
 * points directly (all motion comes out of the solver).
 *
 * Research prototype - Not for clinical use.
 */

import { create } from 'zustand';
import type { CalibrationStatus, CatheterProfile } from '../physics/profile';

export interface SolverMetrics {
  iterations: number;
  residual: number;
  maxPenetrationMm: number;
  converged: boolean;
  wallTimeMs: number;
  bendEnergyNmm: number;
  twistEnergyNmm: number;
  stretchEnergyNmm: number;
}

export interface MetricSample {
  timeS: number;
  tipLateralMm: number;
  bendEnergyNmm: number;
  residual: number;
}

export interface SimulationState {
  // -- actuation (the only inputs the user can drive)
  insertionMm: number;
  axialRotationDeg: number;
  steerX: number;
  steerY: number;
  deployment: number;

  // -- run control
  running: boolean;
  stepRequested: boolean;
  resetRequested: boolean;
  solverHz: number;
  lowQualityMode: boolean;

  // -- display toggles
  showRodFrames: boolean;
  showNodes: boolean;
  showMesh: boolean;
  gravityEnabled: boolean;

  // -- profile / calibration
  profile: CatheterProfile | null;
  calibration: CalibrationStatus | null;
  demoParametersAccepted: boolean;
  profileError: string | null;

  // -- read-only outputs
  timeS: number;
  fps: number;
  metrics: SolverMetrics;
  history: MetricSample[];
  tipPositionMm: [number, number, number];
  solverError: string | null;

  setInsertion: (mm: number) => void;
  nudgeInsertion: (deltaMm: number) => void;
  setAxialRotationDeg: (deg: number) => void;
  nudgeAxialRotationDeg: (deltaDeg: number) => void;
  setSteer: (x: number, y: number) => void;
  nudgeSteer: (dx: number, dy: number) => void;
  setDeployment: (value: number) => void;
  setSolverHz: (hz: number) => void;
  toggleRunning: () => void;
  requestStep: () => void;
  consumeStepRequest: () => boolean;
  requestReset: () => void;
  consumeResetRequest: () => boolean;
  setLowQualityMode: (value: boolean) => void;
  setShowRodFrames: (value: boolean) => void;
  setShowNodes: (value: boolean) => void;
  setShowMesh: (value: boolean) => void;
  setGravityEnabled: (value: boolean) => void;
  loadProfile: (profile: CatheterProfile, calibration: CalibrationStatus) => void;
  acceptDemoParameters: (value: boolean) => void;
  setProfileError: (message: string | null) => void;
  publishFrame: (payload: {
    timeS: number;
    fps: number;
    metrics: SolverMetrics;
    tipPositionMm: [number, number, number];
  }) => void;
  setSolverError: (message: string | null) => void;
  clearHistory: () => void;
}

const MAX_HISTORY_SAMPLES = 600;
const clamp = (value: number, low: number, high: number) => Math.min(Math.max(value, low), high);

export const INSERTION_RANGE_MM: [number, number] = [20, 140];

export const useSimulationStore = create<SimulationState>((set, get) => ({
  insertionMm: 80,
  axialRotationDeg: 0,
  steerX: 0,
  steerY: 0,
  deployment: 0,

  running: true,
  stepRequested: false,
  resetRequested: false,
  solverHz: 30,
  lowQualityMode: false,

  showRodFrames: false,
  showNodes: false,
  showMesh: true,
  gravityEnabled: false,

  profile: null,
  calibration: null,
  demoParametersAccepted: false,
  profileError: null,

  timeS: 0,
  fps: 0,
  metrics: {
    iterations: 0,
    residual: 0,
    maxPenetrationMm: 0,
    converged: true,
    wallTimeMs: 0,
    bendEnergyNmm: 0,
    twistEnergyNmm: 0,
    stretchEnergyNmm: 0,
  },
  history: [],
  tipPositionMm: [0, 0, 0],
  solverError: null,

  setInsertion: (mm) =>
    set({ insertionMm: clamp(mm, INSERTION_RANGE_MM[0], INSERTION_RANGE_MM[1]) }),
  nudgeInsertion: (deltaMm) => get().setInsertion(get().insertionMm + deltaMm),
  setAxialRotationDeg: (deg) => set({ axialRotationDeg: clamp(deg, -360, 360) }),
  nudgeAxialRotationDeg: (deltaDeg) => get().setAxialRotationDeg(get().axialRotationDeg + deltaDeg),
  setSteer: (x, y) => set({ steerX: clamp(x, -1, 1), steerY: clamp(y, -1, 1) }),
  nudgeSteer: (dx, dy) => get().setSteer(get().steerX + dx, get().steerY + dy),
  setDeployment: (value) => set({ deployment: clamp(value, 0, 1) }),
  setSolverHz: (hz) => set({ solverHz: clamp(hz, 5, 60) }),

  toggleRunning: () => set((state) => ({ running: !state.running })),
  requestStep: () => set({ stepRequested: true }),
  consumeStepRequest: () => {
    if (!get().stepRequested) return false;
    set({ stepRequested: false });
    return true;
  },
  requestReset: () => set({ resetRequested: true }),
  consumeResetRequest: () => {
    if (!get().resetRequested) return false;
    set({ resetRequested: false });
    return true;
  },

  setLowQualityMode: (value) => set({ lowQualityMode: value }),
  setShowRodFrames: (value) => set({ showRodFrames: value }),
  setShowNodes: (value) => set({ showNodes: value }),
  setShowMesh: (value) => set({ showMesh: value }),
  setGravityEnabled: (value) => set({ gravityEnabled: value }),

  loadProfile: (profile, calibration) => set({ profile, calibration, profileError: null }),
  acceptDemoParameters: (value) => set({ demoParametersAccepted: value }),
  setProfileError: (message) => set({ profileError: message }),

  publishFrame: ({ timeS, fps, metrics, tipPositionMm }) =>
    set((state) => {
      const sample: MetricSample = {
        timeS,
        tipLateralMm: Math.hypot(tipPositionMm[0], tipPositionMm[1]),
        bendEnergyNmm: metrics.bendEnergyNmm,
        residual: metrics.residual,
      };
      const history = [...state.history, sample];
      if (history.length > MAX_HISTORY_SAMPLES) history.splice(0, history.length - MAX_HISTORY_SAMPLES);
      return { timeS, fps, metrics, tipPositionMm, history };
    }),
  setSolverError: (message) => set({ solverError: message }),
  clearHistory: () => set({ history: [], timeS: 0 }),
}));
