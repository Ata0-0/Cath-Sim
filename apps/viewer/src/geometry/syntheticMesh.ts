/**
 * Synthetic demo anatomy.
 *
 * The default scene must never ship patient data, so Milestone 0 uses a
 * procedurally generated chamber: a sphere with a short tubular "vein" stub, at
 * roughly left-atrium scale.  It is a SHAPE PLACEHOLDER, not an anatomical
 * model - no clinical conclusion may be drawn from it.  Milestone 2 adds STL /
 * OBJ import with mesh QA.
 *
 * Units: mm.
 *
 * Research prototype - Not for clinical use.
 */

export interface TriangleMesh {
  /** Flat vertex positions, 3 per vertex [mm]. */
  positionsMm: Float32Array;
  /** Triangle indices, 3 per face. */
  indices: Uint32Array;
  name: string;
  /** Where the geometry came from - shown in the UI so a demo is never mistaken for patient data. */
  provenance: string;
  triangleCount: number;
  boundsMm: { min: [number, number, number]; max: [number, number, number] };
}

export interface SyntheticChamberOptions {
  /** Chamber radius [mm]. Left atria are roughly 20-28 mm in radius. */
  radiusMm?: number;
  /** Latitude/longitude subdivisions. */
  segments?: number;
  /** Radius of the tubular stub representing a pulmonary-vein ostium [mm]. */
  veinRadiusMm?: number;
  /** Length of that stub [mm]. */
  veinLengthMm?: number;
}

/**
 * Build a closed sphere with a cylindrical stub, centred so that the sheath
 * entry at the origin points into the chamber along +Z.
 */
export function createSyntheticChamber(options: SyntheticChamberOptions = {}): TriangleMesh {
  const radiusMm = options.radiusMm ?? 26;
  const segments = options.segments ?? 48;
  const veinRadiusMm = options.veinRadiusMm ?? 9;
  const veinLengthMm = options.veinLengthMm ?? 22;
  const centreZmm = radiusMm + 55; // sits ahead of the sheath tip at the origin

  const positions: number[] = [];
  const indices: number[] = [];

  // --- sphere (latitude / longitude grid)
  const rings = Math.max(8, Math.round(segments / 2));
  for (let ring = 0; ring <= rings; ring += 1) {
    const theta = (Math.PI * ring) / rings;
    const sinTheta = Math.sin(theta);
    const cosTheta = Math.cos(theta);
    for (let segment = 0; segment <= segments; segment += 1) {
      const phi = (2 * Math.PI * segment) / segments;
      positions.push(
        radiusMm * sinTheta * Math.cos(phi),
        radiusMm * sinTheta * Math.sin(phi),
        centreZmm + radiusMm * cosTheta,
      );
    }
  }
  const stride = segments + 1;
  for (let ring = 0; ring < rings; ring += 1) {
    for (let segment = 0; segment < segments; segment += 1) {
      const a = ring * stride + segment;
      const b = a + stride;
      indices.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }

  // --- pulmonary-vein stub: a cylinder leaving the chamber along +X
  const base = positions.length / 3;
  const veinRings = 8;
  for (let ring = 0; ring <= veinRings; ring += 1) {
    const along = (veinLengthMm * ring) / veinRings;
    for (let segment = 0; segment <= segments; segment += 1) {
      const phi = (2 * Math.PI * segment) / segments;
      positions.push(
        radiusMm * 0.8 + along,
        veinRadiusMm * Math.cos(phi),
        centreZmm + veinRadiusMm * Math.sin(phi),
      );
    }
  }
  for (let ring = 0; ring < veinRings; ring += 1) {
    for (let segment = 0; segment < segments; segment += 1) {
      const a = base + ring * stride + segment;
      const b = a + stride;
      indices.push(a, a + 1, b, a + 1, b + 1, b);
    }
  }

  const positionsMm = new Float32Array(positions);
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positionsMm.length; i += 3) {
    for (let k = 0; k < 3; k += 1) {
      min[k] = Math.min(min[k], positionsMm[i + k]);
      max[k] = Math.max(max[k], positionsMm[i + k]);
    }
  }

  return {
    positionsMm,
    indices: new Uint32Array(indices),
    name: 'Synthetic demo chamber',
    provenance:
      'PROCEDURALLY GENERATED PLACEHOLDER - not anatomy, not patient data. ' +
      'Sphere + tubular stub at approximate left-atrium scale.',
    triangleCount: indices.length / 3,
    boundsMm: { min, max },
  };
}
