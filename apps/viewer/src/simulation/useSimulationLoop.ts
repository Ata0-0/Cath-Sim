/**
 * Simulation loop: owns the `GenericSteerableRF` instance and drives it.
 *
 * Layer separation (see `docs/architecture.md`): React never touches the rod
 * state, and nothing outside the physics core ever moves a centreline point.
 * The UI writes *actuation* into the store; this hook forwards it to the model
 * and publishes the resulting `SimulationFrame` back.
 *
 * The physics update runs on its own fixed-rate timer at `solverHz` and is
 * therefore decoupled from the render rate.  Both currently share the browser
 * main thread; moving the solver into a Web Worker is Milestone 3 work and is
 * recorded in `docs/assumptions.md`.
 *
 * Research prototype - Not for clinical use.
 */

import { useEffect, useMemo, useRef } from 'react';
import { GenericSteerableRF, type SimulationFrame } from '../physics/catheter';
import { calibrationStatus, type CatheterProfile } from '../physics/profile';
import { DEFAULT_SETTINGS, LOW_QUALITY_SETTINGS } from '../physics/solver';
import { useSimulationStore } from '../state/simulationStore';

const DEGREES_TO_RADIANS = Math.PI / 180;

export interface SimulationHandle {
  /** Latest solved frame; mutated in place, read by the renderer each rAF. */
  readonly frameRef: React.MutableRefObject<SimulationFrame | null>;
  readonly catheter: GenericSteerableRF | null;
}

export function useSimulationLoop(
  profile: CatheterProfile | null,
  acceptDemoParameters: boolean,
): SimulationHandle {
  const frameRef = useRef<SimulationFrame | null>(null);
  const catheterRef = useRef<GenericSteerableRF | null>(null);
  const setProfileError = useSimulationStore((state) => state.setProfileError);
  const setSolverError = useSimulationStore((state) => state.setSolverError);
  const loadProfile = useSimulationStore((state) => state.loadProfile);

  // Construction is pure: it must not touch the store, or React would see a
  // state update while another component is still rendering.
  const built = useMemo((): { model: GenericSteerableRF | null; error: string | null } => {
    if (!profile) return { model: null, error: null };
    try {
      return { model: new GenericSteerableRF(profile, acceptDemoParameters), error: null };
    } catch (error) {
      return { model: null, error: error instanceof Error ? error.message : String(error) };
    }
  }, [profile, acceptDemoParameters]);
  const catheter = built.model;
  catheterRef.current = catheter;

  useEffect(() => {
    if (!profile) return;
    loadProfile(profile, calibrationStatus(profile));
    setProfileError(built.error);
  }, [profile, built, loadProfile, setProfileError]);

  // ---- physics timer ------------------------------------------------------
  useEffect(() => {
    if (!catheter) {
      frameRef.current = null;
      return undefined;
    }
    // Solve once so that the scene is populated before the first tick.
    catheter.solveStatic(4, 1e-3);
    frameRef.current = catheter.getRenderGeometry();

    let cancelled = false;
    let timer: number | undefined;
    let framesSinceSample = 0;
    let lastSampleMs = performance.now();

    const tick = () => {
      if (cancelled) return;
      const store = useSimulationStore.getState();
      const dtS = 1 / store.solverHz;
      catheter.setSolverSettings(store.lowQualityMode ? LOW_QUALITY_SETTINGS : DEFAULT_SETTINGS);

      if (store.consumeResetRequest()) {
        catheter.reset();
        store.clearHistory();
      }

      // Push the UI's actuation into the model. Motion always comes out of the
      // solver; nothing here displaces a node directly.
      catheter.setActuation({
        insertionMm: store.insertionMm,
        axialRotationRad: store.axialRotationDeg * DEGREES_TO_RADIANS,
        steerX: store.steerX,
        steerY: store.steerY,
        deployment: store.deployment,
      });

      const shouldAdvance = store.running || store.consumeStepRequest();
      if (shouldAdvance) {
        try {
          catheter.step(dtS);
          setSolverError(null);
        } catch (error) {
          // Safe stop: pause instead of continuing with unusable geometry.
          setSolverError(error instanceof Error ? error.message : String(error));
          if (store.running) store.toggleRunning();
        }
      }

      const frame = catheter.getRenderGeometry();
      frameRef.current = frame;

      framesSinceSample += 1;
      const nowMs = performance.now();
      if (nowMs - lastSampleMs >= 500) {
        const hz = (framesSinceSample * 1000) / (nowMs - lastSampleMs);
        framesSinceSample = 0;
        lastSampleMs = nowMs;
        const tip = frame.centerlineMm;
        const last = tip.length - 3;
        store.publishFrame({
          timeS: frame.timeS,
          fps: hz,
          metrics: {
            iterations: frame.solver.iterations,
            residual: frame.solver.residual,
            maxPenetrationMm: frame.solver.maxPenetrationMm,
            converged: frame.solver.converged,
            wallTimeMs: frame.solver.wallTimeMs,
            bendEnergyNmm: frame.solver.energyNmm.bend,
            twistEnergyNmm: frame.solver.energyNmm.twist,
            stretchEnergyNmm: frame.solver.energyNmm.stretch,
          },
          tipPositionMm: [tip[last], tip[last + 1], tip[last + 2]],
        });
      }

      timer = window.setTimeout(tick, Math.max(1, 1000 / useSimulationStore.getState().solverHz));
    };

    timer = window.setTimeout(tick, 0);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [catheter, setSolverError]);

  return { frameRef, catheter };
}
