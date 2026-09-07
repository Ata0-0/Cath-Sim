/* eslint-disable */
/**
 * GENERATED FILE - do not edit by hand.
 *
 * Source: packages/shared-schema/schemas/simulation.schema.json
 * Regenerate: python scripts/generate_types.py
 *
 * Research prototype - Not for clinical use.
 */


export const SCHEMA_VERSION = "0.1.0";

/**
 * Constitutive parameters.
 * A null value is CALIBRATION_REQUIRED and blocks simulation.
 */
export interface MaterialParameters {
  /** Unit: MPa */
  youngs_modulus_mpa: number | null;
  /** Unit: - */
  poisson_ratio: number | null;
  /** Unit: N mm^2 */
  bending_stiffness_n_mm2?: number | null;
  /** Unit: N mm^2 */
  torsional_stiffness_n_mm2?: number | null;
  /** Unit: N */
  axial_stiffness_n?: number | null;
  /** Unit: N s / mm^2 (per unit length) */
  damping_n_s_per_mm: number | null;
  /** Unit: N mm s / rad per mm */
  torsional_damping_n_mm_s_per_rad?: number | null;
  /** Unit: kg/mm^3 */
  density_kg_per_mm3?: number | null;
}

/**
 * A complete catheter parameter profile.
 */
export interface CatheterParameters {
  schema_version: string;
  model_type: "GenericSteerableRF" | "GenericBalloon" | "GenericLoop" | "GenericLatticeSphere" | "GenericPentasplinePFA";
  display_name: string;
  status: string;
  is_demo_profile?: boolean;
  geometry: Record<string, unknown>;
  material: MaterialParameters;
  actuation: Record<string, unknown>;
  contact: Record<string, unknown>;
  electrodes?: Record<string, unknown>;
  provenance: Record<string, unknown>;
}

/**
 * Normalised handle inputs.
 * Commands carry a sequence number and a timestamp so that late-arriving commands are handled deterministically.
 */
export interface ActuationInput {
  /** Unit: mm */
  insertion_mm: number;
  /** Unit: rad */
  axial_rotation_rad: number;
  /** Unit: - */
  steer_x: number;
  /** Unit: - */
  steer_y: number;
  /** Unit: - */
  deployment: number;
  sequence?: number;
  /** Unit: s */
  client_timestamp_s?: number;
}

export interface SimulationSettings {
  /** Unit: s */
  dt_s: number;
  max_iterations?: number;
  /** Unit: N */
  gradient_tolerance_n?: number;
  gravity_enabled?: boolean;
  accept_demo_parameters?: boolean;
}

/**
 * Anatomy provenance and QA result.
 * Never carries patient identifiers.
 */
export interface MeshMetadata {
  name: string;
  provenance: string;
  units: "mm" | "cm" | "UNKNOWN_ASK_USER";
  vertex_count?: number;
  triangle_count: number;
  is_watertight?: boolean | null;
  issues?: string[];
}

export interface ElectrodePose {
  index: number;
  /** Unit: mm */
  arclength_mm: number;
  /** Unit: mm */
  position_mm: [number, number, number];
  orientation_xyzw: [number, number, number, number];
}

/**
 * One contact between the rod and the anatomy.
 * Force is a NUMERICAL ESTIMATE from an uncalibrated model, not a clinical contact-force reading.
 */
export interface ContactSample {
  node_index: number;
  /** Unit: mm */
  position_mm: [number, number, number];
  normal: [number, number, number];
  /** Unit: mm */
  penetration_mm: number;
  /** Unit: N */
  estimated_force_n: number;
}

export interface ContactMetrics {
  available: boolean;
  reason?: string;
  contact_count: number;
  /** Unit: mm */
  max_penetration_mm: number;
  /** Unit: N */
  total_estimated_force_n?: number;
}

export interface SolverReport {
  iterations: number;
  /** Unit: N */
  residual: number;
  /** Unit: mm */
  max_penetration_mm: number;
  converged: boolean;
}

export interface SimulationFrame {
  /** Unit: s */
  time_s: number;
  /** Unit: mm */
  centerline_mm: [number, number, number][];
  orientations_xyzw: [number, number, number, number][];
  electrodes: ElectrodePose[];
  contacts: ContactSample[];
  solver: SolverReport;
}

export interface ValidationResult {
  test_id: string;
  description?: string;
  measured: number;
  expected: number;
  relative_error: number;
  tolerance: number;
  passed: boolean;
  tolerance_rationale?: string;
}
