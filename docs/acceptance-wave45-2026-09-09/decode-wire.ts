import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {decodeDocumentRecord,decodeDocumentDebugRecord} from "../../apps/web/lib/document-decode.ts";
import {decodeLearningPlan,decodeDocumentPlanningContext} from "../../apps/web/lib/planning-decode.ts";
import {decodePersonaCardGenerateResult,decodeSceneTreeGenerateResult} from "../../apps/web/lib/persona-scene-decode.ts";
import {decodeStreamReport} from "../../apps/web/lib/stream-decode.ts";
const root=process.argv[2]!;
const read=(name:string)=>JSON.parse(readFileSync(`${root}/${name}.json`,"utf8"));
const id=read("summary").identities.document_id;
const cases:[string,(value:unknown)=>unknown][]=[
  ["process",value=>decodeDocumentRecord(value,id,"document",true)],
  ["document_debug",value=>decodeDocumentDebugRecord(value,id)],
  ["document_context",value=>decodeDocumentPlanningContext(value,id)],
  ["plan",value=>decodeLearningPlan(value,{expectedDocumentId:id,requireHarnessTrace:true})],
  ["persona",value=>decodePersonaCardGenerateResult(value,{expectedMode:"long_text"})],
  ["scene",value=>decodeSceneTreeGenerateResult(value,{expectedMode:"long_text"})],
  ["document_process_events",value=>decodeStreamReport(value,{expectedDocumentId:id,expectedStreamKind:"document_process"})],
];
let failures=0;
for(const [name,decode] of cases){
  try {decode(read(name)); console.log(JSON.stringify({case:name,status:"passed"}));}
  catch(error){failures++;console.log(JSON.stringify({case:name,status:"failed",error:String(error)}));}
}
for(const [name,decode] of cases.filter(([name])=>["process","plan","persona","scene"].includes(name))){
  const bad=read(name); bad.harness_trace.trace_schema_version="harness-trace-v999";
  assert.throws(()=>decode(bad),error=>error instanceof Error && error.name!=="TypeError");
  console.log(JSON.stringify({case:`${name}_unknown_trace_version`,status:"rejected"}));
}
process.exitCode=failures?1:0;
