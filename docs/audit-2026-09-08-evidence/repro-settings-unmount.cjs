const fs = require('fs');
const ts = require(process.cwd()+'/node_modules/typescript');
const vm = require('vm');
const src = fs.readFileSync('apps/web/components/settings/use-settings-controller.ts','utf8');
const start = src.indexOf('  const persistSnapshot = useEffectEvent(');
const end = src.indexOf('\n  useEffect(() => {', start);
let finishRequest;
const calls=[];
const ctx={
  useEffectEvent:f=>f,
  savingRef:{current:false}, pendingSaveRef:{current:null},
  desktopSecurityRef:{current:{enabled:false}},
  lastSavedSerializedRef:{current:''},blockedSerializedRef:{current:''},settingsRef:{current:{value:'B'}},
  setIsSaving:()=>{},setSavePhase:()=>{},setSaveError:()=>{},setLastSavedAt:()=>{},setSettings:()=>{},setNumericDrafts:()=>{},
  runtimeSettings:{replaceSettings:()=>{}},serializeSettings:JSON.stringify,
  buildRuntimeSettingsPatch:x=>x,buildNumericDrafts:x=>x,
  updateRuntimeSettings:async x=>{calls.push(x.value);return await new Promise(r=>finishRequest=()=>r(x));}
};
vm.createContext(ctx);
vm.runInContext(ts.transpileModule(src.slice(start,end)+'\nglobalThis.api = {persistSnapshot,flushPendingSave};',{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText,ctx);
(async()=>{
 const first=ctx.api.persistSnapshot({value:'A'}, JSON.stringify({value:'A'}));
 ctx.pendingSaveRef.current={snapshot:{value:'B'},serialized:JSON.stringify({value:'B'})};
 ctx.api.flushPendingSave(); // actual unmount handler
 finishRequest(); await first;
 console.log(JSON.stringify({scenario:'edit B during in-flight save A, then unmount',saved:calls,pendingAfterCompletion:ctx.pendingSaveRef.current}));
})();
