/**
 * UI panels: anatomy / profile (left), actuation and solver (right), timeline
 * and metrics (bottom).  Presentation only - every value shown here comes from
 * the store, and every control writes actuation, never geometry.
 *
 * Research prototype - Not for clinical use.
 */

import { useMemo } from 'react';
import { CALIBRATION_REQUIRED, type CatheterProfile } from '../physics/profile';
import type { TriangleMesh } from '../geometry/syntheticMesh';
import { INSERTION_RANGE_MM, useSimulationStore } from '../state/simulationStore';

interface SliderProps {
  id: string;
  name: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  step: number;
  decimals?: number;
  onChange: (value: number) => void;
}

function Slider({ id, name, unit, value, min, max, step, decimals = 1, onChange }: SliderProps) {
  return (
    <div className="control">
      <label htmlFor={id}>
        <span className="name">{name}</span>
        <span>
          <span className="value">{value.toFixed(decimals)}</span> <span className="unit">{unit}</span>
        </span>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

export function ResearchBanner(): JSX.Element {
  return (
    <div className="research-banner" role="note" data-testid="research-banner">
      <span className="tag">RESEARCH</span>
      <span>Research prototype - Not for clinical use.</span>
      <span style={{ fontWeight: 400, color: '#d8b774' }}>
        Geometric similarity is not mechanical accuracy. No lesion, electric-field or thermal
        prediction is performed.
      </span>
    </div>
  );
}

export function LeftPanel({ chamber }: { chamber: TriangleMesh }): JSX.Element {
  const profile = useSimulationStore((state) => state.profile);
  const calibration = useSimulationStore((state) => state.calibration);
  const demoAccepted = useSimulationStore((state) => state.demoParametersAccepted);
  const acceptDemoParameters = useSimulationStore((state) => state.acceptDemoParameters);
  const profileError = useSimulationStore((state) => state.profileError);
  const showMesh = useSimulationStore((state) => state.showMesh);
  const setShowMesh = useSimulationStore((state) => state.setShowMesh);

  return (
    <aside className="panel" aria-label="Anatomy and catheter profile">
      <h2>Anatomy</h2>
      <div className="status-line">
        <span className="k">Model</span>
        <span className="v">{chamber.name}</span>
      </div>
      <div className="status-line">
        <span className="k">Triangles</span>
        <span className="v">{chamber.triangleCount.toLocaleString('en-US')}</span>
      </div>
      <div className="status-line">
        <span className="k">Units</span>
        <span className="v">mm (generated)</span>
      </div>
      <div className="notice" style={{ marginTop: 8 }}>
        {chamber.provenance}
      </div>
      <div className="checkbox">
        <input
          id="show-mesh"
          type="checkbox"
          checked={showMesh}
          onChange={(event) => setShowMesh(event.target.checked)}
        />
        <label htmlFor="show-mesh">Show chamber surface</label>
      </div>
      <p className="keyhelp">
        STL / OBJ import with manifold, normal, duplicate-vertex and scale checks is Milestone 2.
        Until then the scene uses synthetic geometry only - no patient data is accepted.
      </p>

      <h2>Catheter model</h2>
      <div className="status-line">
        <span className="k">Type</span>
        <span className="v">{profile?.model_type ?? '-'}</span>
      </div>
      <div className="status-line">
        <span className="k">Profile</span>
        <span className="v" style={{ textAlign: 'right' }}>
          {profile?.display_name ?? '-'}
        </span>
      </div>
      <div className="status-line">
        <span className="k">Schema</span>
        <span className="v">{profile?.schema_version ?? '-'}</span>
      </div>

      <h2>Calibration status</h2>
      {calibration ? (
        <>
          <div className="status-line">
            <span className="k">Simulation ready</span>
            <span className={`pill ${calibration.readyForSimulation ? 'ok' : 'danger'}`}>
              {calibration.readyForSimulation ? 'YES' : 'BLOCKED'}
            </span>
          </div>
          <div className="status-line">
            <span className="k">Material source</span>
            <span className="v" data-testid="material-source">
              {calibration.materialSource}
            </span>
          </div>
          <div className="status-line">
            <span className="k">Geometry source</span>
            <span className="v">{calibration.geometrySource}</span>
          </div>
          {calibration.isDemoProfile && (
            <div className="notice" data-testid="demo-warning">
              <strong>DEMO parameters.</strong> Every material and actuation number in this profile
              is an arbitrary placeholder. Nothing computed with it is mechanically valid, and these
              numbers must never be quoted as device properties.
              <div className="checkbox" style={{ marginTop: 6 }}>
                <input
                  id="accept-demo"
                  type="checkbox"
                  checked={demoAccepted}
                  onChange={(event) => acceptDemoParameters(event.target.checked)}
                />
                <label htmlFor="accept-demo">I understand - run with demo parameters</label>
              </div>
            </div>
          )}
          {calibration.missingFields.length > 0 && (
            <div className="notice danger">
              <strong>{CALIBRATION_REQUIRED}:</strong>
              <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                {calibration.missingFields.map((field) => (
                  <li key={field}>{field}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="keyhelp">No profile loaded.</p>
      )}
      {profileError && (
        <div className="notice danger" data-testid="profile-error">
          {profileError}
        </div>
      )}

      <h2>Parameters and units</h2>
      <ParameterTable profile={profile} />
    </aside>
  );
}

function ParameterTable({ profile }: { profile: CatheterProfile | null }) {
  const rows = useMemo(() => {
    if (!profile) return [];
    const units = profile.units ?? {};
    const collect = (section: Record<string, unknown>, prefix: string) =>
      Object.entries(section)
        .filter(([, value]) => typeof value === 'number' || value === null)
        .map(([key, value]) => ({
          key: `${prefix}.${key}`,
          label: key,
          value: value as number | null,
          unit: units[key] ?? inferUnit(key),
        }));
    return [
      ...collect(profile.geometry as unknown as Record<string, unknown>, 'geometry'),
      ...collect(profile.material as unknown as Record<string, unknown>, 'material'),
      ...collect(profile.actuation as unknown as Record<string, unknown>, 'actuation'),
      ...collect(profile.contact as unknown as Record<string, unknown>, 'contact'),
    ];
  }, [profile]);

  if (rows.length === 0) return <p className="keyhelp">-</p>;
  return (
    <table className="param-table">
      <thead>
        <tr>
          <th>Parameter</th>
          <th style={{ textAlign: 'right' }}>Value</th>
          <th>Unit</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            <td title={row.key}>{row.label}</td>
            <td className="num">
              {row.value === null ? (
                <span className="pill warn" title="This value blocks simulation until calibrated">
                  n/a
                </span>
              ) : (
                formatNumber(row.value)
              )}
            </td>
            <td className="unit">{row.unit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function inferUnit(key: string): string {
  if (key.endsWith('_mm')) return 'mm';
  if (key.endsWith('_mm2')) return 'N mm^2';
  if (key.endsWith('_mpa')) return 'MPa';
  if (key.endsWith('_n')) return 'N';
  if (key.endsWith('_rad_per_mm')) return 'rad/mm';
  if (key.endsWith('_mm_per_n')) return 'mm/N';
  if (key.endsWith('_kg_per_mm3')) return 'kg/mm^3';
  return '-';
}

function formatNumber(value: number): string {
  if (value === 0) return '0';
  const magnitude = Math.abs(value);
  if (magnitude >= 1e5 || magnitude < 1e-3) return value.toExponential(3);
  return String(Number(value.toPrecision(6)));
}

export function RightPanel(): JSX.Element {
  const store = useSimulationStore();
  return (
    <aside className="panel right" aria-label="Actuation and solver settings">
      <h2>Actuation</h2>
      <Slider
        id="insertion"
        name="Insertion"
        unit="mm"
        value={store.insertionMm}
        min={INSERTION_RANGE_MM[0]}
        max={INSERTION_RANGE_MM[1]}
        step={0.5}
        onChange={store.setInsertion}
      />
      <Slider
        id="rotation"
        name="Axial rotation"
        unit="deg"
        value={store.axialRotationDeg}
        min={-360}
        max={360}
        step={1}
        decimals={0}
        onChange={store.setAxialRotationDeg}
      />
      <Slider
        id="steer-x"
        name="Steer X"
        unit="[-1, 1]"
        value={store.steerX}
        min={-1}
        max={1}
        step={0.01}
        decimals={2}
        onChange={(value) => store.setSteer(value, store.steerY)}
      />
      <Slider
        id="steer-y"
        name="Steer Y"
        unit="[-1, 1]"
        value={store.steerY}
        min={-1}
        max={1}
        step={0.01}
        decimals={2}
        onChange={(value) => store.setSteer(store.steerX, value)}
      />
      <Slider
        id="deployment"
        name="Deployment"
        unit="[0, 1]"
        value={store.deployment}
        min={0}
        max={1}
        step={0.01}
        decimals={2}
        onChange={store.setDeployment}
      />
      <p className="keyhelp">
        Deployment has no mechanical effect on a steerable RF catheter; it exists for the shared
        catheter interface and drives the pentaspline model in Milestone 4.
      </p>

      <h2>Solver</h2>
      <Slider
        id="solver-hz"
        name="Physics rate"
        unit="Hz"
        value={store.solverHz}
        min={5}
        max={60}
        step={1}
        decimals={0}
        onChange={store.setSolverHz}
      />
      <div className="checkbox">
        <input
          id="low-quality"
          type="checkbox"
          checked={store.lowQualityMode}
          onChange={(event) => store.setLowQualityMode(event.target.checked)}
        />
        <label htmlFor="low-quality">Low-quality mode (fewer solver iterations)</label>
      </div>
      <div className="checkbox">
        <input
          id="gravity"
          type="checkbox"
          checked={store.gravityEnabled}
          disabled
          onChange={(event) => store.setGravityEnabled(event.target.checked)}
        />
        <label htmlFor="gravity" title="Requires a calibrated linear density">
          Gravity (needs calibrated density)
        </label>
      </div>

      <h2>Debug overlays</h2>
      <div className="checkbox">
        <input
          id="show-nodes"
          type="checkbox"
          checked={store.showNodes}
          onChange={(event) => store.setShowNodes(event.target.checked)}
        />
        <label htmlFor="show-nodes">Rod nodes</label>
      </div>
      <div className="checkbox">
        <input
          id="show-frames"
          type="checkbox"
          checked={store.showRodFrames}
          onChange={(event) => store.setShowRodFrames(event.target.checked)}
        />
        <label htmlFor="show-frames">Material frame (m1 red, m2 green)</label>
      </div>
      <p className="keyhelp">
        Contact heat-map, BVH and penetration overlays arrive with the contact stage in Milestone 2.
      </p>

      <h2>Keyboard</h2>
      <p className="keyhelp">
        <kbd>W</kbd>/<kbd>S</kbd> insert / retract &middot; <kbd>A</kbd>/<kbd>D</kbd> rotate &middot;{' '}
        <kbd>&larr;</kbd><kbd>&rarr;</kbd><kbd>&uarr;</kbd><kbd>&darr;</kbd> steer &middot;{' '}
        <kbd>Space</kbd> play/pause &middot; <kbd>R</kbd> reset. Shortcuts are ignored while a text
        field or slider has focus.
      </p>
    </aside>
  );
}

export function BottomPanel({ onExport }: { onExport: (format: 'json' | 'csv') => void }): JSX.Element {
  const running = useSimulationStore((state) => state.running);
  const toggleRunning = useSimulationStore((state) => state.toggleRunning);
  const requestStep = useSimulationStore((state) => state.requestStep);
  const requestReset = useSimulationStore((state) => state.requestReset);
  const timeS = useSimulationStore((state) => state.timeS);
  const history = useSimulationStore((state) => state.history);
  const solverError = useSimulationStore((state) => state.solverError);

  return (
    <div className="bottom">
      <button type="button" className="primary" onClick={toggleRunning} data-testid="play-pause">
        {running ? 'Pause' : 'Play'}
      </button>
      <button type="button" onClick={requestStep} disabled={running} data-testid="step">
        Step
      </button>
      <button type="button" onClick={requestReset} data-testid="reset">
        Reset
      </button>
      <span className="status-line" style={{ minWidth: 150 }}>
        <span className="k">Sim time</span>
        <span className="v" data-testid="sim-time">
          {timeS.toFixed(2)} s
        </span>
      </span>
      <Sparkline
        label="Tip lateral offset"
        unit="mm"
        values={history.map((sample) => sample.tipLateralMm)}
      />
      <Sparkline
        label="Bending energy"
        unit="N mm"
        values={history.map((sample) => sample.bendEnergyNmm)}
      />
      <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
        <button type="button" onClick={() => onExport('json')}>
          Export JSON
        </button>
        <button type="button" onClick={() => onExport('csv')}>
          Export CSV
        </button>
      </span>
      {solverError && (
        <div className="notice danger" style={{ flexBasis: '100%', margin: 0 }} data-testid="solver-error">
          Solver stopped safely: {solverError}
        </div>
      )}
    </div>
  );
}

function Sparkline({ label, unit, values }: { label: string; unit: string; values: number[] }) {
  const width = 150;
  const height = 34;
  const path = useMemo(() => {
    if (values.length < 2) return '';
    const max = Math.max(...values, 1e-12);
    const min = Math.min(...values, 0);
    const span = max - min || 1;
    return values
      .map((value, index) => {
        const x = (index / (values.length - 1)) * width;
        const y = height - ((value - min) / span) * (height - 4) - 2;
        return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  }, [values]);
  const latest = values.length > 0 ? values[values.length - 1] : 0;

  return (
    <span style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <span className="keyhelp">
        {label}: <span style={{ color: 'var(--accent)' }}>{formatNumber(latest)}</span> {unit}
      </span>
      <svg
        className="chart"
        width={width}
        height={height}
        role="img"
        aria-label={`${label} over time, latest ${formatNumber(latest)} ${unit}`}
      >
        <path d={path} fill="none" stroke="#4aa3ff" strokeWidth="1.2" />
      </svg>
    </span>
  );
}

export function MetricsHud(): JSX.Element {
  const metrics = useSimulationStore((state) => state.metrics);
  const fps = useSimulationStore((state) => state.fps);
  const timeS = useSimulationStore((state) => state.timeS);
  const tip = useSimulationStore((state) => state.tipPositionMm);

  const rows: [string, string, string?][] = [
    ['Physics rate', `${fps.toFixed(1)} Hz`],
    ['Solve wall time', `${metrics.wallTimeMs.toFixed(2)} ms`],
    ['Solver iterations', String(metrics.iterations)],
    ['Residual |grad E|', `${metrics.residual.toExponential(2)} N`],
    ['Converged', metrics.converged ? 'yes' : 'no', metrics.converged ? 'ok' : 'warn'],
    ['Max penetration', `${metrics.maxPenetrationMm.toFixed(3)} mm`],
    ['Bending energy', `${metrics.bendEnergyNmm.toExponential(3)} N mm`],
    ['Twist energy', `${metrics.twistEnergyNmm.toExponential(3)} N mm`],
    ['Simulation time', `${timeS.toFixed(2)} s`],
    ['Tip position', `${tip.map((value) => value.toFixed(1)).join(', ')} mm`],
  ];

  return (
    <div className="hud" data-testid="metrics-hud">
      <table>
        <tbody>
          {rows.map(([label, value, tone]) => (
            <tr key={label}>
              <td className="label">{label}</td>
              <td style={tone === 'warn' ? { color: 'var(--warn)' } : undefined}>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 6, color: 'var(--muted)' }}>
        Contact force is not yet computed (Milestone 2). When it is, it will be a numerical estimate,
        not a calibrated clinical contact-force reading.
      </div>
    </div>
  );
}
