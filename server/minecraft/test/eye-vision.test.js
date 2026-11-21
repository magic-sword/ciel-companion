import test from 'node:test';
import assert from 'node:assert/strict';
import { Vec3 } from 'vec3';
import { eyeCamera } from '../src/mindcraft/runtime.js';
import { SessionModel } from '../src/mindcraft/session-model.js';
import { VisionInterpreter } from '../src/vendor/mindcraft/src/agent/vision/vision_interpreter.js';

const jpeg = Buffer.from([0xff, 0xd8, 0xff, 0xe0]);

function agentSeeing(seen, look) {
  const vision = { sendVisionRequest: async (messages, prompt, image) => { seen.push(image); return 'grass and a tree'; } };
  return {
    name: 'Ciel',
    bot: { lookAt: async p => look.push(p), blockAtCursor: () => ({ name: 'oak_log', position: new Vec3(1, 64, 2) }) },
    history: { getHistory: () => [] },
    prompter: { vision_model: new SessionModel(() => ({ model: vision, token: null })),
      promptVision: async (messages, image) => vision.sendVisionRequest(messages, 'describe', image) },
  };
}

test("Mindcraft's !lookAtPosition sees through CIEL's eye: it turns, takes the eye's JPEG and reads it", async () => {
  const seen = [], look = [];
  const eye = { look: async () => ({ jpeg, width: 768, height: 480 }) };
  const vision = new VisionInterpreter(agentSeeing(seen, look), true, eyeCamera(eye));
  const result = await vision.lookAtPosition(1, 64, 2);
  assert.deepEqual(look, [new Vec3(1, 66, 2)]);
  assert.deepEqual(seen, [jpeg]);
  assert.match(result, /Image analysis: "grass and a tree\nBlock at center view: oak_log at \(1, 64, 2\)"/);
});

test('without an eye the view cannot be taken and the command says so', async () => {
  const vision = new VisionInterpreter(agentSeeing([], []), false, null);
  assert.match(await vision.lookAtPosition(1, 64, 2), /Vision is disabled/);
  await assert.rejects(eyeCamera({ look: async () => ({ error: 'eye_unavailable' }) }).capture(), /Could not see: eye_unavailable/);
});
