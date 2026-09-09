/** JSON-lines-free, bounded subprocess bridge to the actual browser decoders. */
import { readFileSync } from 'node:fs';
import { decodeDocumentRecord } from '../lib/document-decode.ts';
import { decodeVersionedHarnessTrace } from '../lib/harness-trace-decode.ts';
import { decodePersonaProfile, decodeSceneProfile } from '../lib/persona-scene-decode.ts';
import { decodeLearningPlan } from '../lib/planning-decode.ts';
import { decodeStudySession } from '../lib/study-session-decode.ts';
import { normalizeTavernErrorDetail } from '../lib/tavern-decode.ts';
import { StrictStreamStateMachine } from '../lib/stream-decode.ts';

const request = JSON.parse(readFileSync(0, 'utf8'));
const supported = ['document_record', 'harness_trace', 'persona_profile', 'scene_profile', 'learning_plan', 'study_session', 'tavern_error_detail', 'stream_state_machine'];
if (!supported.includes(request.decoder)) throw new Error('eval_decoder_unknown');
let observation: { accepted: boolean; error_code: string };
try {
  switch (request.decoder) {
    case 'document_record': decodeDocumentRecord(request.input, request.invocation.expected_document_id); break;
    case 'harness_trace': decodeVersionedHarnessTrace(request.input, 'trace', 'harness-trace-v3', (_path, reason): never => { throw Object.assign(new Error(reason), {code: 'harness_decode_invalid'}); }); break;
    case 'persona_profile': decodePersonaProfile(request.input); break;
    case 'scene_profile': decodeSceneProfile(request.input); break;
    case 'learning_plan': decodeLearningPlan(request.input, {expectedPlanId: request.invocation.expected_plan_id}); break;
    case 'study_session': decodeStudySession(request.input, {expectedSessionId: request.invocation.expected_session_id}); break;
    case 'tavern_error_detail': normalizeTavernErrorDetail(request.input); break;
    case 'stream_state_machine': {
      const m = new StrictStreamStateMachine({streamKind: request.invocation.stream_kind, subject: {subjectType: request.invocation.subject_type, subjectId: request.invocation.subject_id}});
      request.input.forEach((f: unknown, i: number) => m.accept(f, `stream.frames[${i}]`)); m.finish(); break;
    }
  }
  observation = {accepted: true, error_code: ''};
} catch (error) {
  // Unexpected JS/module/runtime errors are infrastructure failures, not a
  // successful negative example. Only the decoder's typed rejection counts.
  if (!(error instanceof Error) || !('code' in error) || typeof error.code !== 'string') throw error;
  observation = {accepted: false, error_code: error.code};
}
process.stdout.write(JSON.stringify(observation));
