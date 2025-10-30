
import React, { useRef, useState, useEffect } from "react";
import { abApi } from "../lib/abApi";
import { formatDisplayName } from "@/lib/displayNames";

export default function AudioCleanup({ token }) {
  const [fillerOn, setFillerOn] = useState(true);
  const [words, setWords] = useState(["um", "uh", "like", "you know"]);
  const [shortenPauses, setShortenPauses] = useState(true);
  const [aggressive, setAggressive] = useState(false);
  const [beepOn, setBeepOn] = useState(false);
  const [beepType, setBeepType] = useState('low'); // 'low' | 'high' | 'custom'
  const [selectedSfx, setSelectedSfx] = useState("");
  const [sfxList, setSfxList] = useState([]);

  useEffect(() => {
    let mounted = true;
    abApi(token).listSfx().then(list => mounted && setSfxList(list));
    return () => { mounted = false; };
  }, [token]);

  const audioCtxRef = useRef(null);
  const playBeep = (type) => {
    if (!audioCtxRef.current) audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
    const ctx = audioCtxRef.current;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = type === "low" ? 700 : 1200;
    gain.gain.value = 0.1;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    setTimeout(()=>osc.stop(), 200);
  };

  const onUploadSfx = async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "audio/*";
    input.onchange = async (e) => {
      const f = e.target.files?.[0];
      if (!f) return;
      await abApi(token).uploadMedia([f], [f.name], "sfx");
      const list = await abApi(token).listSfx();
      setSfxList(list);
      setSelectedSfx(list[list.length-1]?.id || "");
    };
    input.click();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div><h2 className="text-base font-semibold">Audio cleanup</h2></div>
        <button className="rounded-lg border px-3 py-2 hover:bg-muted" onClick={()=>{
          setFillerOn(true); setWords(["um","uh","like","you know"]); setShortenPauses(true); setAggressive(false);
          setBeepOn(false); setBeepType("low"); setSelectedSfx("");
        }}>Restore defaults</button>
      </div>

      {/* Filler words */}
      <div className="rounded-xl border p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">Remove filler words</div>
            <div className="text-sm text-muted-foreground">Hide common fillers like “um/uh/like” when it’s safe</div>
          </div>
          <label className="inline-flex items-center gap-2 text-sm"><input type="checkbox" checked={fillerOn} onChange={()=>setFillerOn(v=>!v)} /> Enable</label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {words.map((w,i)=> (
            <span key={i} className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm">
              {w}
              <button className="text-muted-foreground" onClick={()=>setWords(words.filter((_,idx)=>idx!==i))}>×</button>
            </span>
          ))}
          <button className="rounded-full border px-3 py-1 text-sm" onClick={()=>setWords(ws => ws.concat(["um"]))}>+ Add word</button>
        </div>
      </div>

      {/* Silence trimming */}
      <div className="rounded-xl border p-4">
        <div className="font-medium">Shorten long pauses</div>
        <div className="mt-2 flex items-center gap-6 text-sm">
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={shortenPauses} onChange={()=>setShortenPauses(v=>!v)} /> Enable</label>
          <label className={"inline-flex items-center gap-2 " + (shortenPauses ? "" : "opacity-60 pointer-events-none")}>
            <input type="checkbox" checked={aggressive} onChange={()=>setAggressive(v=>!v)} /> More aggressive detection
          </label>
        </div>
      </div>

      {/* Censor beep */}
      <div className="rounded-xl border p-4">
        <div className="font-medium">Censor beep</div>
        <div className="mt-2 space-y-3 text-sm">
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={beepOn} onChange={()=>setBeepOn(v=>!v)} /> Enable</label>
          <div className={beepOn ? "" : "opacity-60 pointer-events-none"}>
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <label className="inline-flex items-center gap-2"><input type="radio" name="beep" checked={beepType==='low'} onChange={()=>setBeepType('low')} /> Low beep</label>
                <button className="w-6 h-6 border rounded grid place-items-center text-xs" title="Play low beep" onClick={()=>playBeep("low")}>▶</button>
              </div>
              <div className="flex items-center gap-2">
                <label className="inline-flex items-center gap-2"><input type="radio" name="beep" checked={beepType==='high'} onChange={()=>setBeepType('high')} /> High beep</label>
                <button className="w-6 h-6 border rounded grid place-items-center text-xs" title="Play high beep" onClick={()=>playBeep("high")}>▶</button>
              </div>
              <div className="flex items-center gap-2">
                <label className="inline-flex items-center gap-2"><input type="radio" name="beep" checked={beepType==='custom'} onChange={()=>setBeepType('custom')} /> Use your own sound</label>
              </div>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <label className="text-sm">Sound</label>
              <select className="rounded-lg border px-2 py-1 text-sm" disabled={beepType!== 'custom'} value={selectedSfx} onChange={(e)=>setSelectedSfx(e.target.value)}>
                <option value="">Select sound effects...</option>
                {sfxList.map(s => <option key={s.id} value={s.id}>{formatDisplayName(s, { fallback: 'Sound effect' }) || 'Sound effect'}</option>)}
                <option value="__upload">Upload new sound effects…</option>
              </select>
              {selectedSfx && selectedSfx !== '__upload' && (
                <span className="text-xs text-muted-foreground">Selected: {sfxList.find(s=>s.id===selectedSfx)?.friendly_name || selectedSfx}</span>
              )}
              {selectedSfx === '__upload' && (
                <button className="px-2 py-1 rounded border text-xs" onClick={onUploadSfx}>Choose file…</button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Coming soon */}
      <div className="rounded-xl border p-4">
        <div className="font-medium">Coming soon</div>
        <div className="mt-2 grid sm:grid-cols-2 gap-2 text-sm">
          <label className="flex items-center gap-2 opacity-60"><input type="checkbox" disabled /> Remove coughs</label>
          <label className="flex items-center gap-2 opacity-60"><input type="checkbox" disabled /> Duck background sound effects</label>
        </div>
      </div>
    </div>
  );
}
