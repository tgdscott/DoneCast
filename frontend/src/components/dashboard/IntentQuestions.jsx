import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

// props: open, onSubmit({ flubber, intern, sfx }), onCancel, hide={{flubber:bool,intern:bool,sfx:bool}}
const normalize = (value) => {
  if (value === 'yes') return 'yes';
  return 'no';
};

export default function IntentQuestions({ open, onSubmit, onCancel, hide, initialAnswers, detectedIntents }){
  const [answers, setAnswers] = useState({ flubber: 'no', intern: 'no', sfx: 'no' });
  const [detailMode, setDetailMode] = useState(false);
  useEffect(()=>{
    if(open){
      const base = initialAnswers || {};
      setAnswers({
        flubber: normalize(base.flubber),
        intern: normalize(base.intern),
        sfx: normalize(base.sfx),
      });
      setDetailMode(false);
    }
  }, [open, initialAnswers]);
  if(!open) return null;
  const h = hide || {};
  const options = ['yes', 'no'];
  const allAnswered = ['flubber','intern','sfx']
    .filter(k => !h[k])
    .every(k => options.includes(answers[k]));

  const detection = detectedIntents || {};

  const resolveInfo = (key) => {
    const info = detection?.[key] || {};
    const count = Number(info?.count ?? 0);
    const matches = Array.isArray(info?.matches) ? info.matches : [];
    return { count, matches };
  };

  const makeCopy = (key, baseLabel, baseDescription) => {
    const info = resolveInfo(key);
    if (info.count > 0) {
      if (key === 'flubber') {
        const qty = info.count === 1 ? 'a Flubber marker' : `${info.count} Flubber markers`;
        return {
          detected: true,
          label: `We detected ${qty}. Should we process those?`,
          description: `We heard ${info.count} possible redo${info.count === 1 ? '' : 's'} in your transcript.`,
        };
      }
      if (key === 'intern') {
        const qty = info.count === 1 ? 'an Intern command' : `${info.count} Intern commands`;
        return {
          detected: true,
          label: `We detected ${qty}. Should we process those?`,
          description: `We heard ${info.count} intern cue${info.count === 1 ? '' : 's'} in your transcript.`,
        };
      }
      if (key === 'sfx') {
        const names = Array.from(new Set(info.matches.map(m => (m?.label || m?.phrase || '').trim()).filter(Boolean)));
        let detail = `We heard ${info.count} sound effect cue${info.count === 1 ? '' : 's'}.`;
        if (names.length === 1) detail = `Cue word detected: ${names[0]}.`;
        else if (names.length === 2) detail = `Cue words detected: ${names[0]} and ${names[1]}.`;
        else if (names.length > 2) {
          const preview = names.slice(0, 3).join(', ');
          detail = `Cue words detected: ${preview}${names.length > 3 ? '…' : ''}.`;
        }
        return {
          detected: true,
          label: `We detected sound effect cues. Should we process those?`,
          description: detail,
        };
      }
    }
    return { detected: false, label: baseLabel, description: baseDescription };
  };

  const flubberCopy = makeCopy(
    'flubber',
    'Is there a Flubber?',
    'If you recorded any redos or mistakes, we can look for them automatically so you can trim them in the next step.',
  );
  const internCopy = makeCopy(
    'intern',
    'Is there an Intern?',
    'Tell us if the AI intern voice should speak in this recording. We only ask when voices are available on your account.',
  );
  const sfxCopy = makeCopy(
    'sfx',
    'Are there any word Sound Effects?',
    'Answer yes if you have cue words that should drop music or sound effects during assembly.',
  );

  const Radio = ({name,label,description,detected}) => (
    <div className="flex flex-col gap-2 text-sm">
      <div className="flex items-center gap-4">
        <div className={`w-64 text-[13px] font-medium ${detected ? 'text-emerald-700' : ''}`}>
          {label}
          {detected && (
            <span className="ml-2 inline-flex items-center rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
              Detected
            </span>
          )}
        </div>
        {options.map(v => (
          <label key={v} className="flex items-center gap-1 cursor-pointer">
            <input
              type="radio"
              name={name}
              value={v}
              checked={answers[name]===v}
              onChange={()=> setAnswers(a=>({...a,[name]:v}))}
            />
            <span className="capitalize">{v}</span>
          </label>
        ))}
      </div>
      {(detected || detailMode) && description && (
        <div className={`text-xs ${detected ? 'text-emerald-700' : 'text-muted-foreground'} ml-0 md:ml-[16.5rem] -mt-1`}>
          {description}
        </div>
      )}
    </div>
  );
  const submit = () => onSubmit({
    flubber: h.flubber ? 'no' : normalize(answers.flubber),
    intern: h.intern ? 'no' : normalize(answers.intern),
    sfx: h.sfx ? 'no' : normalize(answers.sfx),
  });
  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40" role="dialog" aria-modal="true">
      <Card className="w-full max-w-2xl">
        <CardHeader className="flex items-center justify-between">
          <CardTitle className="text-base">Before We Start</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Detail toggle */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={()=> setDetailMode(d=>!d)}
              className="text-xs text-slate-600 hover:text-slate-900 underline"
            >
              {detailMode ? 'Hide details' : 'What does this mean?'}
            </button>
          </div>

          {!h.flubber && (
            <Radio
              name="flubber"
              label={flubberCopy.label}
              description={flubberCopy.description}
              detected={flubberCopy.detected}
            />
          )}
          {!h.intern && (
            <Radio
              name="intern"
              label={internCopy.label}
              description={internCopy.description}
              detected={internCopy.detected}
            />
          )}
          {!h.sfx && (
            <Radio
              name="sfx"
              label={sfxCopy.label}
              description={sfxCopy.description}
              detected={sfxCopy.detected}
            />
          )}

          <div className="flex justify-end gap-2 mt-2">
            <Button variant="ghost" onClick={onCancel}>Cancel</Button>
            <Button onClick={submit} disabled={!allAnswered}>Continue</Button>
          </div>
        </CardContent>
      </Card>
    </div>,
    document.body
  );
}
