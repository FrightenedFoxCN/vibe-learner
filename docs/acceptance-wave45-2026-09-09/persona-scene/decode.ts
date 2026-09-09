import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {decodePersonaProfile, decodeSceneLibraryItem} from '../../../apps/web/lib/persona-scene-decode.ts';
const wire=JSON.parse(readFileSync(new URL('./final-readback.json',import.meta.url),'utf8'));
assert.equal(wire.personas.length,2);
assert.equal(wire.scenes.length,2);
for(const p of wire.personas) decodePersonaProfile(p,{expectedPersonaId:p.id,expectedSource:'user'});
for(const s of wire.scenes) decodeSceneLibraryItem(s,{expectedSceneId:s.scene_id,expectedRevision:s.revision});
console.log('Passed: 2 real desktop Persona and 2 Scene library responses decoded strictly.');
