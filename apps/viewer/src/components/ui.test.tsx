/**
 * UI behaviour tests: the research-only label, the calibration gate, the
 * keyboard shortcuts and the export payload.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import demoProfileJson from '../../../../configs/demo-steerable-rf.json';
import uncalibratedProfileJson from '../../../../configs/generic-steerable-rf.json';
import { BottomPanel, LeftPanel, ResearchBanner } from './Panels';
import { isFormControlFocused } from './useKeyboardControls';
import { createSyntheticChamber } from '../geometry/syntheticMesh';
import { calibrationStatus, type CatheterProfile } from '../physics/profile';
import { useSimulationStore } from '../state/simulationStore';
import { buildCsvExport, buildJsonExport } from '../export';

const demoProfile = demoProfileJson as unknown as CatheterProfile;
const uncalibratedProfile = uncalibratedProfileJson as unknown as CatheterProfile;
const chamber = createSyntheticChamber({ segments: 12 });

beforeEach(() => {
  useSimulationStore.setState({
    profile: null,
    calibration: null,
    demoParametersAccepted: false,
    profileError: null,
    running: true,
    insertionMm: 80,
    axialRotationDeg: 0,
    steerX: 0,
    steerY: 0,
    history: [],
  });
});

describe('research-only labelling', () => {
  it('is always visible', () => {
    render(<ResearchBanner />);
    expect(screen.getByTestId('research-banner')).toHaveTextContent(
      'Research prototype - Not for clinical use.',
    );
  });
});

describe('calibration status panel', () => {
  it('shows every CALIBRATION_REQUIRED field for an uncalibrated profile', () => {
    useSimulationStore
      .getState()
      .loadProfile(uncalibratedProfile, calibrationStatus(uncalibratedProfile));
    render(<LeftPanel chamber={chamber} />);
    expect(screen.getByText('BLOCKED')).toBeInTheDocument();
    expect(screen.getByTestId('material-source')).toHaveTextContent('CALIBRATION_REQUIRED');
    expect(screen.getByText('material.youngs_modulus_mpa')).toBeInTheDocument();
    expect(screen.getByText('actuation.steer_gain_rad_per_mm')).toBeInTheDocument();
  });

  it('labels the demo profile as uncalibrated placeholder values', () => {
    useSimulationStore.getState().loadProfile(demoProfile, calibrationStatus(demoProfile));
    render(<LeftPanel chamber={chamber} />);
    expect(screen.getByTestId('demo-warning')).toHaveTextContent(
      /arbitrary placeholder|must never be quoted/i,
    );
    expect(screen.getByText('YES')).toBeInTheDocument();
  });

  it('shows the parameter units next to every value', () => {
    useSimulationStore.getState().loadProfile(demoProfile, calibrationStatus(demoProfile));
    render(<LeftPanel chamber={chamber} />);
    expect(screen.getByText('outer_diameter_mm')).toBeInTheDocument();
    expect(screen.getAllByText('mm').length).toBeGreaterThan(0);
    expect(screen.getByText('rad/mm per unit steering input')).toBeInTheDocument();
  });

  it('names the demo anatomy as a placeholder, never as patient data', () => {
    useSimulationStore.getState().loadProfile(demoProfile, calibrationStatus(demoProfile));
    render(<LeftPanel chamber={chamber} />);
    expect(screen.getByText(/PROCEDURALLY GENERATED PLACEHOLDER/)).toBeInTheDocument();
  });
});

describe('keyboard shortcut guard', () => {
  it('ignores shortcuts while a form control has focus', () => {
    const input = document.createElement('input');
    const div = document.createElement('div');
    expect(isFormControlFocused(input)).toBe(true);
    expect(isFormControlFocused(div)).toBe(false);
  });
});

describe('run controls', () => {
  it('toggles play/pause and enables Step only while paused', async () => {
    const user = userEvent.setup();
    render(<BottomPanel onExport={() => {}} />);
    expect(screen.getByTestId('step')).toBeDisabled();
    await user.click(screen.getByTestId('play-pause'));
    expect(useSimulationStore.getState().running).toBe(false);
    expect(screen.getByTestId('step')).toBeEnabled();
    await user.click(screen.getByTestId('step'));
    expect(useSimulationStore.getState().stepRequested).toBe(true);
  });

  it('requests a reset', async () => {
    const user = userEvent.setup();
    render(<BottomPanel onExport={() => {}} />);
    await user.click(screen.getByTestId('reset'));
    expect(useSimulationStore.getState().resetRequested).toBe(true);
  });
});

describe('export', () => {
  const payload = {
    frame: {
      timeS: 1.5,
      centerlineMm: Float64Array.from([0, 0, 0, 0, 0, 2]),
      orientationsXyzw: Float64Array.from([0, 0, 0, 1]),
      radiusMm: 1.25,
      electrodes: [],
      contacts: [] as never[],
      solver: {
        iterations: 7,
        residual: 1e-7,
        maxPenetrationMm: 0,
        converged: true,
        wallTimeMs: 3.2,
        energyNmm: { stretch: 0, bend: 1, twist: 0, total: 1 },
      },
    },
    history: [{ timeS: 1.5, tipLateralMm: 0.2, bendEnergyNmm: 1, residual: 1e-7 }],
    profile: demoProfile,
    demoParametersAccepted: true,
  };

  it('carries the research-only disclaimer and the provenance in JSON', () => {
    const parsed = JSON.parse(buildJsonExport(payload));
    expect(parsed.disclaimer).toMatch(/Not for clinical use/);
    expect(parsed.profile.is_demo_profile).toBe(true);
    expect(parsed.profile.provenance.material_source).toBe('PLACEHOLDER_NOT_MEASURED');
    expect(parsed.frame.centerline_mm).toEqual([
      [0, 0, 0],
      [0, 0, 2],
    ]);
    expect(parsed.frame.solver.iterations).toBe(7);
  });

  it('carries the disclaimer and both tables in CSV', () => {
    const csv = buildCsvExport(payload);
    expect(csv.split('\n')[0]).toMatch(/Not for clinical use/);
    expect(csv).toContain('node_index,x_mm,y_mm,z_mm');
    expect(csv).toContain('time_s,tip_lateral_mm,bend_energy_n_mm,residual_n');
  });
});

describe('synthetic anatomy', () => {
  it('is closed, non-empty and at left-atrium scale', () => {
    const mesh = createSyntheticChamber();
    expect(mesh.triangleCount).toBeGreaterThan(1000);
    expect(mesh.provenance).toMatch(/not patient data/i);
    const spanMm = mesh.boundsMm.max.map((value, axis) => value - mesh.boundsMm.min[axis]);
    for (const span of spanMm) expect(span).toBeGreaterThan(20);
    for (const span of spanMm) expect(span).toBeLessThan(200);
  });
});
