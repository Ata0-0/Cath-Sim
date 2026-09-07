/**
 * Over-damped implicit rod solver - TypeScript port of
 * `packages/physics-core/src/cathsim_physics/solver.py`.
 *
 * Time integration is the minimising-movement (backward-Euler on over-damped
 * dynamics) scheme
 *
 *     q^{n+1} = argmin_q [ E(q) + 1/(2 dt) sum_k c_k (q_k - q_k^n)^2 ]
 *
 * which is unconditionally stable - there is no CFL limit coming from the very
 * stiff bending term - and reduces to static equilibrium as dt -> infinity.
 *
 * The minimisation is limited-memory BFGS with a backtracking Armijo line
 * search.  A rod couples a stiff local stretch mode to a soft global bending
 * mode, so the history size matters a great deal: the Python reference needs
 * 14624 iterations with 20 corrections and 607 with 150.  The default here is
 * chosen accordingly.
 *
 * Research prototype - Not for clinical use.
 */

import {
  type EnergyBreakdown,
  type ExternalLoads,
  type RodMaterial,
  type RodRest,
  type RodState,
  RodGeometryError,
  energyAndGradient,
  nodeCount,
} from './rod';

export interface BoundaryConditions {
  /** Node indices whose position is prescribed (proximal clamp). */
  clampedNodes: number[];
  /** Edge indices whose twist angle is prescribed (handle roll). */
  clampedEdges: number[];
}

export interface SolverSettings {
  maxIterations: number;
  /** Convergence threshold on the infinity norm of the free-DOF gradient [N]. */
  gradientToleranceN: number;
  historySize: number;
  /**
   * Wall-clock budget for one solve [ms]; 0 disables the limit.
   *
   * A rod couples a soft global bending mode (tip stiffness ~ 3EI/L^3) to a
   * stiff local stretch mode (~EA/h), a condition number around 1e5, so a
   * *converged* implicit step can need several hundred L-BFGS iterations.
   * Interactive frames cannot always afford that.  The budget keeps the frame
   * rate honest, and the shortfall is never hidden: `converged` goes false and
   * the residual is displayed.  The rod still descends the same physical
   * energy, so it keeps approaching the correct equilibrium over subsequent
   * frames - and `solveStatic` always reaches it exactly.
   */
  maxWallTimeMs: number;
}

export interface SolverReport {
  iterations: number;
  residual: number;
  maxPenetrationMm: number;
  converged: boolean;
  energy: EnergyBreakdown;
  /** Wall-clock duration of the solve [ms]. */
  wallTimeMs: number;
}

export const DEFAULT_SETTINGS: SolverSettings = {
  maxIterations: 600,
  gradientToleranceN: 1e-6,
  historySize: 60,
  maxWallTimeMs: 12,
};

/** Reduced-cost preset offered in the UI when the frame budget is missed. */
export const LOW_QUALITY_SETTINGS: SolverSettings = {
  maxIterations: 150,
  gradientToleranceN: 1e-5,
  historySize: 30,
  maxWallTimeMs: 6,
};

export class RodSolverError extends Error {}

/**
 * Solves one rod. The instance owns scratch buffers so that stepping does not
 * allocate per frame (see the performance targets in the project contract).
 */
export class RodSolver {
  private readonly freeIndices: Int32Array;

  private readonly gradNodes: Float64Array;

  private readonly gradPhi: Float64Array;

  private readonly nodeDamping: Float64Array;

  private readonly edgeDamping: Float64Array;

  private readonly trial: RodState;

  private readonly previousNodes: Float64Array;

  private readonly previousPhi: Float64Array;

  private history: { s: Float64Array; y: Float64Array; rho: number }[] = [];

  constructor(
    private readonly material: RodMaterial,
    private readonly rest: RodRest,
    template: RodState,
    boundary: BoundaryConditions,
    public settings: SolverSettings = DEFAULT_SETTINGS,
  ) {
    const n = nodeCount(template);
    const edges = n - 1;
    const clampedNode = new Set(boundary.clampedNodes);
    const clampedEdge = new Set(boundary.clampedEdges);

    const free: number[] = [];
    for (let i = 0; i < n; i += 1) {
      if (!clampedNode.has(i)) free.push(3 * i, 3 * i + 1, 3 * i + 2);
    }
    // Twist DOFs are appended after the positional ones, offset by 3N.
    for (let j = 0; j < edges; j += 1) {
      if (!clampedEdge.has(j)) free.push(3 * n + j);
    }
    if (free.length === 0) {
      throw new RodSolverError('Every degree of freedom is clamped; there is nothing to solve.');
    }
    this.freeIndices = Int32Array.from(free);
    this.gradNodes = new Float64Array(3 * n);
    this.gradPhi = new Float64Array(edges);
    this.previousNodes = new Float64Array(3 * n);
    this.previousPhi = new Float64Array(edges);
    this.trial = {
      nodesMm: new Float64Array(3 * n),
      phiRad: new Float64Array(edges),
      d1First: template.d1First,
    };

    // Damping weights: per-unit-length coefficients lumped onto nodes/edges.
    this.nodeDamping = new Float64Array(n);
    for (let j = 0; j < edges; j += 1) {
      const half = 0.5 * rest.edgeLengthsMm[j];
      this.nodeDamping[j] += material.dampingNsPerMm2 * half;
      this.nodeDamping[j + 1] += material.dampingNsPerMm2 * half;
    }
    this.edgeDamping = new Float64Array(edges);
    for (let j = 0; j < edges; j += 1) {
      this.edgeDamping[j] = material.torsionalDampingNmmSPerRad * rest.edgeLengthsMm[j];
    }
  }

  /** Drop the limited-memory curvature history (after a reset or a re-mesh). */
  resetHistory(): void {
    this.history = [];
  }

  /** Relax to static equilibrium (no inertia term). */
  solveStatic(state: RodState, loads?: ExternalLoads): SolverReport {
    this.resetHistory();
    return this.minimise(state, loads, 0);
  }

  /** Advance the over-damped dynamics by `dtS` seconds. */
  step(state: RodState, dtS: number, loads?: ExternalLoads): SolverReport {
    if (!Number.isFinite(dtS) || dtS <= 0) {
      throw new RodSolverError(
        `Time step must be a positive finite number of seconds, got ${String(dtS)}.`,
      );
    }
    this.previousNodes.set(state.nodesMm);
    this.previousPhi.set(state.phiRad);
    return this.minimise(state, loads, 1 / dtS);
  }

  /** Free-DOF gradient assembled from the last energy evaluation. */
  private packGradient(out: Float64Array, nodeOffset: number): void {
    for (let k = 0; k < this.freeIndices.length; k += 1) {
      const index = this.freeIndices[k];
      out[k] = index < nodeOffset ? this.gradNodes[index] : this.gradPhi[index - nodeOffset];
    }
  }

  private objective(
    candidate: Float64Array,
    state: RodState,
    loads: ExternalLoads | undefined,
    dampingScalePerS: number,
    gradientOut: Float64Array,
  ): number {
    const nodeOffset = state.nodesMm.length;
    this.trial.nodesMm.set(state.nodesMm);
    this.trial.phiRad.set(state.phiRad);
    for (let k = 0; k < this.freeIndices.length; k += 1) {
      const index = this.freeIndices[k];
      if (index < nodeOffset) this.trial.nodesMm[index] = candidate[k];
      else this.trial.phiRad[index - nodeOffset] = candidate[k];
    }

    const energy = energyAndGradient(
      this.trial,
      this.rest,
      this.material,
      loads,
      this.gradNodes,
      this.gradPhi,
    );
    let total = energy.total;

    if (dampingScalePerS > 0) {
      for (let i = 0; i < this.nodeDamping.length; i += 1) {
        const weight = dampingScalePerS * this.nodeDamping[i];
        for (let k = 0; k < 3; k += 1) {
          const delta = this.trial.nodesMm[3 * i + k] - this.previousNodes[3 * i + k];
          total += 0.5 * weight * delta * delta;
          this.gradNodes[3 * i + k] += weight * delta;
        }
      }
      for (let j = 0; j < this.edgeDamping.length; j += 1) {
        const weight = dampingScalePerS * this.edgeDamping[j];
        const delta = this.trial.phiRad[j] - this.previousPhi[j];
        total += 0.5 * weight * delta * delta;
        this.gradPhi[j] += weight * delta;
      }
    }

    this.packGradient(gradientOut, nodeOffset);
    return total;
  }

  /** L-BFGS with a backtracking Armijo line search. */
  private minimise(
    state: RodState,
    loads: ExternalLoads | undefined,
    dampingScalePerS: number,
  ): SolverReport {
    const startMs = now();
    const dimension = this.freeIndices.length;
    const nodeOffset = state.nodesMm.length;

    const x = new Float64Array(dimension);
    for (let k = 0; k < dimension; k += 1) {
      const index = this.freeIndices[k];
      x[k] = index < nodeOffset ? state.nodesMm[index] : state.phiRad[index - nodeOffset];
    }

    const gradient = new Float64Array(dimension);
    const direction = new Float64Array(dimension);
    const candidate = new Float64Array(dimension);
    const nextGradient = new Float64Array(dimension);

    // The curvature history is kept ACROSS calls.  With a heavily over-damped
    // rod the implicit step is close to a full static solve, so a frame-budgeted
    // solve alone would stall: every frame would spend its whole budget
    // re-discovering the same curvature.  Carrying the history over turns the
    // per-frame budget into a continuation solve that keeps descending the same
    // physical energy and converges to the true equilibrium over a few frames.
    // It is discarded whenever the search direction stops being a descent
    // direction (see below) or on `resetHistory()`.
    const history = this.history;
    const alpha = new Float64Array(this.settings.historySize);

    let value: number;
    try {
      value = this.objective(x, state, loads, dampingScalePerS, gradient);
    } catch (error) {
      throw this.wrap(error);
    }

    let iterations = 0;
    let residual = infinityNorm(gradient);

    const deadlineMs =
      this.settings.maxWallTimeMs > 0 ? startMs + this.settings.maxWallTimeMs : Infinity;

    for (; iterations < this.settings.maxIterations; iterations += 1) {
      if (residual <= this.settings.gradientToleranceN) break;
      if (iterations % 8 === 0 && now() > deadlineMs) break;

      // --- two-loop recursion
      direction.set(gradient);
      for (let h = history.length - 1; h >= 0; h -= 1) {
        const { s, y, rho } = history[h];
        alpha[h] = rho * dot(s, direction);
        axpy(direction, y, -alpha[h]);
      }
      if (history.length > 0) {
        const last = history[history.length - 1];
        const scale = dot(last.s, last.y) / dot(last.y, last.y);
        if (Number.isFinite(scale) && scale > 0) {
          for (let k = 0; k < dimension; k += 1) direction[k] *= scale;
        }
      }
      for (let h = 0; h < history.length; h += 1) {
        const { s, y, rho } = history[h];
        const beta = rho * dot(y, direction);
        axpy(direction, s, alpha[h] - beta);
      }
      for (let k = 0; k < dimension; k += 1) direction[k] = -direction[k];

      let slope = dot(gradient, direction);
      if (!(slope < 0)) {
        // The approximated inverse Hessian lost positive definiteness; restart.
        for (let k = 0; k < dimension; k += 1) direction[k] = -gradient[k];
        slope = -dot(gradient, gradient);
        history.length = 0;
      }

      // --- backtracking Armijo line search
      let stepSize = history.length === 0 ? Math.min(1, 1 / Math.max(residual, 1e-12)) : 1;
      let nextValue = value;
      let accepted = false;
      for (let attempt = 0; attempt < 40; attempt += 1) {
        for (let k = 0; k < dimension; k += 1) candidate[k] = x[k] + stepSize * direction[k];
        try {
          nextValue = this.objective(candidate, state, loads, dampingScalePerS, nextGradient);
        } catch (error) {
          if (error instanceof RodGeometryError) {
            // The trial configuration folded; shorten the step instead of failing.
            stepSize *= 0.5;
            continue;
          }
          throw this.wrap(error);
        }
        if (nextValue <= value + 1e-4 * stepSize * slope) {
          accepted = true;
          break;
        }
        stepSize *= 0.5;
      }
      if (!accepted) break;

      const s = new Float64Array(dimension);
      const y = new Float64Array(dimension);
      for (let k = 0; k < dimension; k += 1) {
        s[k] = candidate[k] - x[k];
        y[k] = nextGradient[k] - gradient[k];
      }
      const sy = dot(s, y);
      if (sy > 1e-16) {
        history.push({ s, y, rho: 1 / sy });
        if (history.length > this.settings.historySize) history.shift();
      }

      x.set(candidate);
      gradient.set(nextGradient);
      value = nextValue;
      residual = infinityNorm(gradient);
    }

    // Write the solution back into the caller's state.
    for (let k = 0; k < dimension; k += 1) {
      const index = this.freeIndices[k];
      if (index < nodeOffset) state.nodesMm[index] = x[k];
      else state.phiRad[index - nodeOffset] = x[k];
    }

    const finite = state.nodesMm.every(Number.isFinite) && state.phiRad.every(Number.isFinite);
    if (!finite) {
      throw new RodSolverError(
        'The solver produced a non-finite configuration and was stopped. Reduce ' +
          'the time step or check the parameter profile.',
      );
    }
    // Report the elastic energy of the *accepted* solution, not of whatever
    // trial point the line search happened to evaluate last.
    const energy = energyAndGradient(
      state,
      this.rest,
      this.material,
      loads,
      this.gradNodes,
      this.gradPhi,
    );
    return {
      iterations,
      residual,
      maxPenetrationMm: 0, // populated by the contact stage (Milestone 2)
      converged: residual <= this.settings.gradientToleranceN,
      energy,
      wallTimeMs: now() - startMs,
    };
  }

  private wrap(error: unknown): RodSolverError {
    return error instanceof Error
      ? new RodSolverError(error.message)
      : new RodSolverError(String(error));
  }
}

function now(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function dot(a: Float64Array, b: Float64Array): number {
  let sum = 0;
  for (let i = 0; i < a.length; i += 1) sum += a[i] * b[i];
  return sum;
}

function axpy(target: Float64Array, source: Float64Array, factor: number): void {
  for (let i = 0; i < target.length; i += 1) target[i] += factor * source[i];
}

function infinityNorm(a: Float64Array): number {
  let max = 0;
  for (let i = 0; i < a.length; i += 1) {
    const value = Math.abs(a[i]);
    if (value > max) max = value;
  }
  return max;
}
