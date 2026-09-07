/**
 * Global keyboard shortcuts.
 *
 * Shortcuts must never fire while the user is typing into, or dragging, a form
 * control - otherwise arrow keys would both move a slider and steer the
 * catheter.  Every button in the UI stays reachable with Tab.
 *
 * Research prototype - Not for clinical use.
 */

import { useEffect } from 'react';
import { useSimulationStore } from '../state/simulationStore';

const INSERTION_STEP_MM = 2;
const ROTATION_STEP_DEG = 5;
const STEER_STEP = 0.05;

/** True when the event target is an editable/focusable form control. */
export function isFormControlFocused(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName.toLowerCase();
  return tag === 'input' || tag === 'textarea' || tag === 'select' || tag === 'button';
}

export function useKeyboardControls(): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isFormControlFocused(event.target)) return;
      const store = useSimulationStore.getState();

      switch (event.key) {
        case 'w':
        case 'W':
          store.nudgeInsertion(INSERTION_STEP_MM);
          break;
        case 's':
        case 'S':
          store.nudgeInsertion(-INSERTION_STEP_MM);
          break;
        case 'a':
        case 'A':
          store.nudgeAxialRotationDeg(-ROTATION_STEP_DEG);
          break;
        case 'd':
        case 'D':
          store.nudgeAxialRotationDeg(ROTATION_STEP_DEG);
          break;
        case 'ArrowLeft':
          store.nudgeSteer(-STEER_STEP, 0);
          break;
        case 'ArrowRight':
          store.nudgeSteer(STEER_STEP, 0);
          break;
        case 'ArrowUp':
          store.nudgeSteer(0, STEER_STEP);
          break;
        case 'ArrowDown':
          store.nudgeSteer(0, -STEER_STEP);
          break;
        case ' ':
          store.toggleRunning();
          break;
        case 'r':
        case 'R':
          store.requestReset();
          break;
        default:
          return;
      }
      event.preventDefault();
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
