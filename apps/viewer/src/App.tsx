/**
 * CathSim LA viewer - single-screen layout.
 *
 * Research prototype - Not for clinical use.
 */

import { useEffect, useMemo, useState } from 'react';
import demoProfileJson from '../../../configs/demo-steerable-rf.json';
import uncalibratedProfileJson from '../../../configs/generic-steerable-rf.json';
import { BottomPanel, LeftPanel, MetricsHud, ResearchBanner, RightPanel } from './components/Panels';
import { SceneView } from './components/SceneView';
import { useKeyboardControls } from './components/useKeyboardControls';
import { createSyntheticChamber } from './geometry/syntheticMesh';
import type { CatheterProfile } from './physics/profile';
import { useSimulationLoop } from './simulation/useSimulationLoop';
import { useSimulationStore } from './state/simulationStore';
import { buildCsvExport, buildJsonExport } from './export';

const DEMO_PROFILE = demoProfileJson as unknown as CatheterProfile;
const UNCALIBRATED_PROFILE = uncalibratedProfileJson as unknown as CatheterProfile;

export function App(): JSX.Element {
  const [selectedProfile, setSelectedProfile] = useState<'demo' | 'generic'>('demo');
  const demoAccepted = useSimulationStore((state) => state.demoParametersAccepted);
  const acceptDemoParameters = useSimulationStore((state) => state.acceptDemoParameters);
  const history = useSimulationStore((state) => state.history);

  const chamber = useMemo(() => createSyntheticChamber(), []);
  const profile = selectedProfile === 'demo' ? DEMO_PROFILE : UNCALIBRATED_PROFILE;
  const { frameRef } = useSimulationLoop(profile, demoAccepted);

  useKeyboardControls();

  // The demo profile is opt-in, but the viewer would otherwise open on an empty
  // scene. Start with it accepted and keep the warning permanently visible.
  useEffect(() => {
    acceptDemoParameters(true);
  }, [acceptDemoParameters]);

  const onExport = (format: 'json' | 'csv') => {
    const payload = {
      frame: frameRef.current,
      history,
      profile,
      demoParametersAccepted: demoAccepted,
    };
    const text = format === 'json' ? buildJsonExport(payload) : buildCsvExport(payload);
    const blob = new Blob([text], {
      type: format === 'json' ? 'application/json' : 'text/csv',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `cathsim-la-frame.${format}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app">
      <ResearchBanner />
      <div className="workspace">
        <LeftPanel chamber={chamber} />
        <div style={{ position: 'relative', flex: 1, minWidth: 0, display: 'flex' }}>
          <SceneView frameRef={frameRef} chamber={chamber} />
          <MetricsHud />
          <div style={{ position: 'absolute', bottom: 10, left: 10 }}>
            <label htmlFor="profile-select" className="keyhelp" style={{ marginRight: 6 }}>
              Parameter profile
            </label>
            <select
              id="profile-select"
              value={selectedProfile}
              onChange={(event) => setSelectedProfile(event.target.value as 'demo' | 'generic')}
            >
              <option value="demo">DEMO steerable (placeholder values)</option>
              <option value="generic">GenericSteerableRF (calibration required)</option>
            </select>
          </div>
        </div>
        <RightPanel />
      </div>
      <BottomPanel onExport={onExport} />
    </div>
  );
}
