/**
 * Result export.  Frames are exported exactly as the solver produced them; no
 * smoothing, resampling or unit conversion happens on the way out.
 *
 * Research prototype - Not for clinical use.
 */

import type { SimulationFrame } from './physics/catheter';
import type { CatheterProfile } from './physics/profile';
import type { MetricSample } from './state/simulationStore';

export interface ExportPayload {
  frame: SimulationFrame | null;
  history: MetricSample[];
  profile: CatheterProfile | null;
  demoParametersAccepted: boolean;
}

const DISCLAIMER =
  'Research prototype - Not for clinical use. Values are numerical estimates from an ' +
  'uncalibrated model; geometric similarity is not mechanical accuracy.';

export function buildJsonExport(payload: ExportPayload): string {
  const { frame, history, profile, demoParametersAccepted } = payload;
  return `${JSON.stringify(
    {
      schema_version: '0.1.0',
      disclaimer: DISCLAIMER,
      exported_at: new Date().toISOString(),
      profile: profile
        ? {
            model_type: profile.model_type,
            display_name: profile.display_name,
            status: profile.status,
            is_demo_profile: Boolean(profile.is_demo_profile),
            demo_parameters_accepted: demoParametersAccepted,
            provenance: profile.provenance,
          }
        : null,
      frame: frame
        ? {
            time_s: frame.timeS,
            centerline_mm: toTriples(frame.centerlineMm),
            orientations_xyzw: toQuadruples(frame.orientationsXyzw),
            electrodes: frame.electrodes,
            contacts: frame.contacts,
            solver: frame.solver,
          }
        : null,
      history,
    },
    null,
    2,
  )}\n`;
}

export function buildCsvExport(payload: ExportPayload): string {
  const lines = [
    `# ${DISCLAIMER}`,
    `# profile=${payload.profile?.display_name ?? 'none'} demo_accepted=${payload.demoParametersAccepted}`,
    'node_index,x_mm,y_mm,z_mm',
  ];
  const centreline = payload.frame?.centerlineMm;
  if (centreline) {
    for (let i = 0; i < centreline.length / 3; i += 1) {
      lines.push(
        `${i},${centreline[3 * i].toFixed(6)},${centreline[3 * i + 1].toFixed(6)},${centreline[
          3 * i + 2
        ].toFixed(6)}`,
      );
    }
  }
  lines.push('', 'time_s,tip_lateral_mm,bend_energy_n_mm,residual_n');
  for (const sample of payload.history) {
    lines.push(
      `${sample.timeS.toFixed(4)},${sample.tipLateralMm.toFixed(6)},` +
        `${sample.bendEnergyNmm.toExponential(6)},${sample.residual.toExponential(6)}`,
    );
  }
  return `${lines.join('\n')}\n`;
}

function toTriples(flat: Float64Array): number[][] {
  const out: number[][] = [];
  for (let i = 0; i < flat.length; i += 3) out.push([flat[i], flat[i + 1], flat[i + 2]]);
  return out;
}

function toQuadruples(flat: Float64Array): number[][] {
  const out: number[][] = [];
  for (let i = 0; i < flat.length; i += 4) out.push([flat[i], flat[i + 1], flat[i + 2], flat[i + 3]]);
  return out;
}
