/**
 * Catheter parameter profiles and their calibration status - TypeScript
 * counterpart of `cathsim_physics/config.py`.
 *
 * A profile may leave physical values as `null`.  Such a value is
 * CALIBRATION_REQUIRED and blocks simulation; a clearly labelled demo profile
 * may only be used after explicit consent.  Geometric similarity is not
 * mechanical accuracy.
 *
 * Research prototype - Not for clinical use.
 */

import type { RodMaterial } from './rod';

export const SCHEMA_VERSION = '0.1.0';
export const CALIBRATION_REQUIRED = 'CALIBRATION_REQUIRED';

export interface CatheterProfile {
  schema_version: string;
  model_type: string;
  display_name: string;
  status: string;
  is_demo_profile?: boolean;
  notes?: string[];
  geometry: {
    total_length_mm: number;
    working_length_mm?: number;
    outer_diameter_mm: number;
    tip_length_mm: number;
    active_length_mm: number;
    node_spacing_mm: number;
  };
  material: {
    youngs_modulus_mpa: number | null;
    poisson_ratio: number | null;
    bending_stiffness_n_mm2: number | null;
    torsional_stiffness_n_mm2: number | null;
    axial_stiffness_n: number | null;
    damping_n_s_per_mm: number | null;
    torsional_damping_n_mm_s_per_rad?: number | null;
    density_kg_per_mm3?: number | null;
  };
  actuation: {
    steer_gain_rad_per_mm: number | null;
    max_steering_input?: number;
    bidirectional?: boolean;
    hysteresis_model?: string;
  };
  contact: {
    friction_coefficient: number | null;
    compliance_mm_per_n: number | null;
    catheter_collision_radius_mm: number;
  };
  electrodes?: {
    count: number;
    arclength_from_tip_mm: number[];
    length_mm?: number[];
    source?: string;
  };
  provenance: {
    geometry_source: string;
    material_source: string;
    last_calibrated_at: string | null;
  };
  units?: Record<string, string>;
}

/** Physics fields the rod solver cannot run without. */
export const REQUIRED_PHYSICS_FIELDS = [
  'material.youngs_modulus_mpa',
  'material.poisson_ratio',
  'material.damping_n_s_per_mm',
  'actuation.steer_gain_rad_per_mm',
] as const;

export interface CalibrationStatus {
  missingFields: string[];
  isDemoProfile: boolean;
  materialSource: string;
  geometrySource: string;
  readyForSimulation: boolean;
}

export class ProfileError extends Error {}

function getPath(profile: CatheterProfile, dotted: string): unknown {
  let node: unknown = profile;
  for (const key of dotted.split('.')) {
    if (typeof node !== 'object' || node === null || !(key in node)) return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return node;
}

export function calibrationStatus(profile: CatheterProfile): CalibrationStatus {
  const missingFields = REQUIRED_PHYSICS_FIELDS.filter(
    (field) => getPath(profile, field) === null || getPath(profile, field) === undefined,
  );
  return {
    missingFields: [...missingFields],
    isDemoProfile: Boolean(profile.is_demo_profile),
    materialSource: profile.provenance?.material_source ?? CALIBRATION_REQUIRED,
    geometrySource: profile.provenance?.geometry_source ?? CALIBRATION_REQUIRED,
    readyForSimulation: missingFields.length === 0,
  };
}

export function assertSchemaVersion(profile: CatheterProfile): void {
  if (profile.schema_version !== SCHEMA_VERSION) {
    throw new ProfileError(
      `Parameter profile declares schema_version=${String(profile.schema_version)} but this ` +
        `build understands ${SCHEMA_VERSION}. Migrate the profile instead of ` +
        'editing the schema silently.',
    );
  }
}

/** Section properties of a solid circular cross-section. */
const area = (diameterMm: number) => (Math.PI * diameterMm ** 2) / 4;
const secondMoment = (diameterMm: number) => (Math.PI * diameterMm ** 4) / 64;
const polarMoment = (diameterMm: number) => (Math.PI * diameterMm ** 4) / 32;
const shearModulus = (youngsMpa: number, poisson: number) => youngsMpa / (2 * (1 + poisson));

/**
 * Build the rod constitutive parameters from a profile.
 *
 * @throws ProfileError when a required value is still CALIBRATION_REQUIRED, or
 *   when a demo profile is used without explicit consent.
 */
export function materialFromProfile(
  profile: CatheterProfile,
  acceptDemoParameters: boolean,
): RodMaterial {
  assertSchemaVersion(profile);
  const status = calibrationStatus(profile);
  if (!status.readyForSimulation) {
    throw new ProfileError(
      `Cannot start a simulation: the following physical parameters are still ` +
        `${CALIBRATION_REQUIRED} in profile "${profile.display_name}": ` +
        `${status.missingFields.join(', ')}. Either calibrate them against bench ` +
        'measurements (see docs/validation-plan.md) or select the clearly ' +
        'labelled demo profile.',
    );
  }
  if (status.isDemoProfile && !acceptDemoParameters) {
    throw new ProfileError(
      'This is a DEMO parameter profile with invented, uncalibrated values. It ' +
        'may only be used after explicitly accepting demo parameters. Demo ' +
        'values must never be reported as catheter specifications.',
    );
  }

  const diameterMm = profile.geometry.outer_diameter_mm;
  const youngsMpa = profile.material.youngs_modulus_mpa as number;
  const poisson = profile.material.poisson_ratio as number;
  const dampingPerLength = profile.material.damping_n_s_per_mm as number;

  return {
    bendingStiffnessNmm2:
      profile.material.bending_stiffness_n_mm2 ?? youngsMpa * secondMoment(diameterMm),
    torsionalStiffnessNmm2:
      profile.material.torsional_stiffness_n_mm2 ??
      shearModulus(youngsMpa, poisson) * polarMoment(diameterMm),
    axialStiffnessN: profile.material.axial_stiffness_n ?? youngsMpa * area(diameterMm),
    dampingNsPerMm2: dampingPerLength,
    torsionalDampingNmmSPerRad:
      profile.material.torsional_damping_n_mm_s_per_rad ??
      // Documented fallback: scale by the polar radius of gyration squared.
      (dampingPerLength * polarMoment(diameterMm)) / area(diameterMm),
  };
}
