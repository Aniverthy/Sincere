/**
 * feedback_ml feature — public surface.
 *
 * Mirrors `sincere/feedback_ml` (FR-4.3-4.4): the We-Met prompt and its responses, which are
 * the ground-truth labels that re-anchor the models to real-world compatibility rather than
 * in-app swipe appeal (§13).
 */

export { WeMetPrompt } from './screens/WeMetPrompt';
export { feedbackApi } from './api';
