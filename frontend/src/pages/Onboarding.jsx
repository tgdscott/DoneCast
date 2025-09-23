import React, { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/AuthContext.jsx";
import OnboardingWrapper from "@/components/onboarding/OnboardingWrapper.jsx";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle, Play, Pause } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useComfort } from '@/ComfortContext.jsx';
import { makeApi } from '@/lib/apiClient';
import { FORMATS, NO_MUSIC_OPTION } from "@/components/onboarding/OnboardingWizard.jsx";

export default function Onboarding() {
  const { token, user, refreshUser } = useAuth();
  const { toast } = useToast();
  const STEP_KEY = 'ppp.onboarding.step';
  // Restore step index on mount from localStorage
  const [stepIndex, setStepIndex] = useState(() => {
    try {
      const raw = localStorage.getItem(STEP_KEY);
      const n = raw != null ? parseInt(raw, 10) : 0;
      return Number.isFinite(n) && n >= 0 ? n : 0;
    } catch {
      return 0;
    }
  });
  const stepSaveTimer = useRef(null);
  const { largeText, setLargeText, highContrast, setHighContrast } = useComfort();

  // Feature flag parity with modal wizard
  const ENABLE_BYOK = (import.meta.env?.VITE_ENABLE_BYOK === 'true');

  // Path selection: 'new' | 'import'
  const [path, setPath] = useState('new');

  // Local state mirrors NewUserWizard.jsx
  const [formData, setFormData] = useState({
    podcastName: '',
    podcastDescription: '',
    coverArt: null,
    elevenlabsApiKey: '',
  });
  const [isSpreakerConnected, setIsSpreakerConnected] = useState(false);
  const [saving, setSaving] = useState(false);
  // Spreaker connect gating (require a click)
  const [spreakerClicked, setSpreakerClicked] = useState(false);

  // Additional state for richer flow
  const [formatKey, setFormatKey] = useState('solo');
  const [publishDay, setPublishDay] = useState('Monday');
  const [rssUrl, setRssUrl] = useState('');

  // Music assets
  const [musicAssets, setMusicAssets] = useState([NO_MUSIC_OPTION]);
  const [musicLoading, setMusicLoading] = useState(false);
  const [musicChoice, setMusicChoice] = useState('none');
  const [musicPreviewing, setMusicPreviewing] = useState(null); // asset id
  const audioRef = useRef(null);
  // New scheduling states
  const [freqUnit, setFreqUnit] = useState(''); // no default; enforce selection
  const [freqCount, setFreqCount] = useState(1);
  const [cadenceError, setCadenceError] = useState('');
  const [selectedWeekdays, setSelectedWeekdays] = useState([]); // e.g., ['Monday','Wednesday']
  const [selectedDates, setSelectedDates] = useState([]); // e.g., ['2025-09-10','2025-09-24']
  const [notSureSchedule, setNotSureSchedule] = useState(false);
  // Name capture (Step 1)
  const [firstName, setFirstName] = useState(() => (user?.first_name || ''));
  const [lastName, setLastName] = useState(() => (user?.last_name || ''));
  const [nameError, setNameError] = useState('');

  // Cover step: allow skipping
  const [skipCoverNow, setSkipCoverNow] = useState(false);

  // Intro/Outro step state
  const [introMode, setIntroMode] = useState('tts'); // 'tts' | 'upload'
  const [outroMode, setOutroMode] = useState('tts'); // 'tts' | 'upload'
  const [introScript, setIntroScript] = useState('Welcome to my podcast!');
  const [outroScript, setOutroScript] = useState('Thank you for listening and see you next time!');
  const [introFile, setIntroFile] = useState(null);
  const [outroFile, setOutroFile] = useState(null);
  const [introAsset, setIntroAsset] = useState(null); // { filename, id, ... }
  const [outroAsset, setOutroAsset] = useState(null);
  // Voice selection and preview for TTS
  const [voices, setVoices] = useState([]);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voicesError, setVoicesError] = useState('');
  const [selectedVoiceId, setSelectedVoiceId] = useState('default');
  const voiceAudioRef = useRef(null);
  const [voicePreviewing, setVoicePreviewing] = useState(false);

  // Helper: find a voice by id across possible schemas
  const getVoiceById = (vid) => {
    if (!vid || vid === 'default') return null;
    const canon = (v) => v?.voice_id || v?.id || v?.name;
    return voices.find(v => canon(v) === vid) || null;
  };

  const previewSelectedVoice = () => {
    try {
      if (voicePreviewing && voiceAudioRef.current) {
        voiceAudioRef.current.pause();
        setVoicePreviewing(false);
        return;
      }
      const v = getVoiceById(selectedVoiceId);
      const url = v?.preview_url || v?.sample_url;
      if (!url) return;
      if (voiceAudioRef.current) { try { voiceAudioRef.current.pause(); } catch {} }
      const a = new Audio(url);
      voiceAudioRef.current = a;
      setVoicePreviewing(true);
      a.onended = () => { setVoicePreviewing(false); };
      a.play().catch(() => setVoicePreviewing(false));
    } catch {
      setVoicePreviewing(false);
    }
  };

  const wizardSteps = useMemo(() => {
    // Step 1: Get their name
    const nameStep = {
      id: 'yourName',
      title: 'What can we call you?',
      description: 'First name required; last name optional. You can update this later in Settings.',
      validate: async () => {
        const fn = (firstName || '').trim();
        const ln = (lastName || '').trim();
        if (!fn) { setNameError('First name is required'); return false; }
        setNameError('');
        try {
            const api = makeApi(token);
            await api.patch('/api/auth/users/me/prefs', { first_name: fn, last_name: ln || undefined });
          try { refreshUser?.({ force: true }); } catch {}
        } catch (_) { /* non-fatal */ }
        return true;
      },
      render: () => (
        <div className="grid gap-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="firstName" className="text-right">First name<span className="text-red-600">*</span></Label>
            <Input id="firstName" value={firstName} onChange={(e)=>setFirstName(e.target.value)} className="col-span-3" placeholder="e.g., Alex" />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="lastName" className="text-right">Last name</Label>
            <Input id="lastName" value={lastName} onChange={(e)=>setLastName(e.target.value)} className="col-span-3" placeholder="(Optional)" />
          </div>
          {nameError && <p className="text-sm text-red-600">{nameError}</p>}
        </div>
      ),
    };

    // Step 2: Ask about existing podcast
    const choosePathStep = {
      id: 'choosePath',
      title: 'Do you have an existing podcast?',
      description: 'Start fresh, or import an existing show if you already have one.',
    };

  if (path === 'import') {
      const importSteps = [
    { id: 'rss', title: 'Import from RSS', description: 'Paste your feed URL.' },
    { id: 'confirm', title: 'Confirm import', description: "We'll mirror your setup and assets." },
    { id: 'importing', title: 'Importing...', description: 'Fetching episodes and metadata.' },
    { id: 'analyze', title: 'Analyzing', description: "We'll bring over what we can, and you can tidy later." },
    { id: 'assets', title: 'Assets', description: "We'll bring over what we can, and you can tidy later." },
        { id: 'importSuccess', title: 'Imported', description: 'Your show is now in Podcast Pro Plus.' },
      ];
  // Import path after branching at Step 2
  return [...importSteps];
    }

    // Default: 'new' flow
    const newSteps = [
      // Step 1: Name
      nameStep,
      // Step 2: Choose path
      choosePathStep,
      // Step 3: About your show
      { id: 'showDetails', title: 'About your show', description: "Tell us the name and what it's about. You can change this later." },
      { id: 'format', title: 'Format', description: 'How will most episodes feel?' },
      { id: 'coverArt', title: 'Podcast Cover Art (optional)', description: "Upload your podcast cover art. A square picture at least 1400 pixels wide works best. If you don't have one yet, you can skip this for now." },
      // New: Intro/Outro creation step
      { id: 'introOutro', title: 'Intro & Outro', description: 'Create simple intro/outro audio now, or upload files if you have them.' },
      { id: 'music', title: 'Music (optional)', description: 'Pick intro/outro music (optional).' },
      { id: 'spreaker', title: 'Connect to Podcast Host', description: "We partner with Spreaker to host your podcast." },
      // Step 8: Publish cadence
      { id: 'publishCadence', title: 'How often will you publish?', description: 'Take your best guess — you can change this later.' },
      // Step 9: Conditional schedule details
      { id: 'publishSchedule', title: 'Publishing days', description: 'Pick your publishing days/dates.' },
      { id: 'finish', title: 'Finish', description: 'Nice work. You can publish now or explore your dashboard.' },
    ];
    // Conditionally include publishSchedule (skip if unit is day or year)
    const includeSchedule = (freqUnit !== 'day' && freqUnit !== 'year');
    const withConditional = includeSchedule ? newSteps : newSteps.filter(s => s.id !== 'publishSchedule');
    return withConditional;
  }, [path, ENABLE_BYOK, firstName, lastName, nameError, freqUnit]);

  const stepId = wizardSteps[stepIndex]?.id;

  // If a query param requests a specific step (e.g., step=2), respect it on first mount
  const bootstrappedRef = useRef(false);
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    try {
      const url = new URL(window.location.href);
      const stepParam = url.searchParams.get('step');
      const n = stepParam != null ? parseInt(stepParam, 10) : NaN;
      if (Number.isFinite(n) && n >= 1) {
        // 1-based in the URL; clamp to available steps
        const clamped = Math.min(Math.max(1, n), wizardSteps.length) - 1;
        setStepIndex(clamped);
        // If jumping to step 2 (choosePath), we already have their name. Ensure path remains 'new'.
      }
    } catch {}
  }, [wizardSteps.length]);

  // Clamp restored step to bounds if env flags change shape
  useEffect(() => {
    const maxIndex = Math.max(0, wizardSteps.length - 1);
    if (stepIndex > maxIndex) setStepIndex(maxIndex);
  }, [wizardSteps.length]);

  // Debounce persist of current step index (≈350ms)
  useEffect(() => {
    if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current);
    stepSaveTimer.current = setTimeout(() => {
      try { localStorage.setItem(STEP_KEY, String(stepIndex)); } catch {}
    }, 350);
    return () => { if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current); };
  }, [stepIndex]);

  // When on the music step, fetch assets once
  useEffect(() => {
    if (stepId === 'music' && musicAssets.length <= 1 && !musicLoading) {
      setMusicLoading(true);
      (async () => {
        try {
          const api = makeApi(token);
          const data = await api.get('/api/music/assets');
          const assets = Array.isArray(data?.assets) ? data.assets : [];
          setMusicAssets([NO_MUSIC_OPTION, ...assets]);
        } catch (_) {
          setMusicAssets([NO_MUSIC_OPTION]);
        } finally {
          setMusicLoading(false);
        }
      })();
    }
    // cleanup preview when leaving music step
    if (stepId !== 'music' && audioRef.current) {
      try { audioRef.current.pause(); } catch {}
      audioRef.current = null;
      setMusicPreviewing(null);
    }
  }, [stepId, musicAssets.length, musicLoading]);

  // Load voices when entering intro/outro step
  useEffect(() => {
    if (stepId === 'introOutro' && !voicesLoading && voices.length === 0) {
      setVoicesLoading(true); setVoicesError('');
      (async()=>{
        try {
          const data = await makeApi(token).get('/api/elevenlabs/voices?size=12');
          const items = (data && (data.items || data.voices)) || [];
          setVoices(items);
          if (items.length > 0 && (!selectedVoiceId || selectedVoiceId === 'default')) {
            const first = items[0];
            setSelectedVoiceId(first.voice_id || first.id || first.name || 'default');
          }
        } catch (e) {
          setVoicesError('Voice list unavailable; using a default voice.');
        } finally {
          setVoicesLoading(false);
        }
      })();
    }
    if (stepId !== 'introOutro' && voiceAudioRef.current) {
      try { voiceAudioRef.current.pause(); } catch {}
      setVoicePreviewing(false);
    }
  }, [stepId, voicesLoading, voices.length, selectedVoiceId, token]);

  const togglePreview = (asset) => {
    if (!asset || asset.id === 'none') return;
    const url = asset.preview_url || asset.url || asset.filename;
    if (!url) return;
    // stop current
    if (musicPreviewing === asset.id) {
      try { audioRef.current?.pause(); } catch {}
      audioRef.current = null;
      setMusicPreviewing(null);
      return;
    }
    try {
      if (audioRef.current) { try { audioRef.current.pause(); } catch {} }
      const a = new Audio(url);
      audioRef.current = a;
      setMusicPreviewing(asset.id);
      const stopAt = 20; // seconds
      const onTick = () => {
        if (!a || isNaN(a.currentTime)) return;
        if (a.currentTime >= stopAt) {
          a.pause();
          setMusicPreviewing(null);
          a.removeEventListener('timeupdate', onTick);
        }
      };
      a.addEventListener('timeupdate', onTick);
      a.onended = () => { setMusicPreviewing(null); try { a.removeEventListener('timeupdate', onTick);} catch {} };
      a.play().catch(() => { setMusicPreviewing(null); });
    } catch {
      setMusicPreviewing(null);
    }
  };

  const handleChange = (e) => {
    const { id, value, files } = e.target;
    setFormData((prev) => ({ ...prev, [id]: files ? files[0] : value }));
  };

  async function handleConnectSpreaker() {
    try {
    const api = makeApi(token);
    const { auth_url } = await api.get('/api/spreaker/auth/login');
    if (!auth_url) throw new Error('Could not start the Spreaker sign-in.');
      const popup = window.open(auth_url, 'spreakerAuth', 'width=600,height=700');
      setSpreakerClicked(true);
      const timer = setInterval(() => {
        if (!popup || popup.closed) {
          clearInterval(timer);
          makeApi(token).get('/api/auth/users/me').then(user => { if (user?.spreaker_access_token) setIsSpreakerConnected(true); }).catch(()=>{});
        }
      }, 1000);
    } catch (error) {
      try { toast({ title: 'Connection Error', description: error.message, variant: 'destructive' }); } catch {}
    }
  }

  async function generateOrUploadTTS(kind, mode, script, file) {
    // kind: 'intro' | 'outro'
    try {
      if (mode === 'upload') {
        if (!file) return null;
        const fd = new FormData();
        fd.append('files', file);
        const data = await makeApi(token).raw(`/api/media/upload/${kind}`, { method: 'POST', body: fd });
        if (Array.isArray(data) && data.length > 0) return data[0];
        return null;
      } else {
        const body = { text: (script || '').trim() || (kind==='intro' ? 'Welcome to my podcast!' : 'Thank you for listening and see you next time!'), category: kind };
        if (selectedVoiceId && selectedVoiceId !== 'default') body.voice_id = selectedVoiceId;
        const item = await makeApi(token).post('/api/media/tts', body);
        return item || null;
      }
    } catch (e) {
      try { toast({ title: `Could not prepare ${kind}`, description: e?.message || String(e), variant: 'destructive' }); } catch {}
      return null;
    }
  }

  async function handleFinish() {
    try {
      setSaving(true);
      if (formData.elevenlabsApiKey) {
        try {
          await makeApi(token).put('/api/users/me/elevenlabs-key', { api_key: formData.elevenlabsApiKey });
        } catch {}
      }
      if (path === 'new') {
        const podcastPayload = new FormData();
        podcastPayload.append('name', formData.podcastName);
        podcastPayload.append('description', formData.podcastDescription);
        if (formData.coverArt) podcastPayload.append('cover_image', formData.coverArt);
        // Optionally include selected format/music/publishDay metadata in a future API
        const createdPodcast = await makeApi(token).raw('/api/podcasts/', { method: 'POST', body: podcastPayload });
        if (!createdPodcast || !createdPodcast.id) {
          let detail = '';
          try { detail = (createdPodcast && createdPodcast.detail) ? createdPodcast.detail : JSON.stringify(createdPodcast || {}); } catch {}
          throw new Error(detail || 'Failed to create the podcast show.');
        }
        try { toast({ title: 'Success!', description: 'Your new podcast show has been created.' }); } catch {}

        // Create a default template "My First Template" with intro/outro segments and background music rules
        try {
          const segments = [];
          if (introAsset?.filename) {
            segments.push({ segment_type: 'intro', source: { source_type: 'static', filename: introAsset.filename } });
          }
          // Always include a content segment placeholder
          segments.push({ segment_type: 'content', source: { source_type: 'static', filename: 'content_placeholder.mp3' } });
          if (outroAsset?.filename) {
            segments.push({ segment_type: 'outro', source: { source_type: 'static', filename: outroAsset.filename } });
          }
          // Compose background music rules if a track was chosen
          const musicRules = [];
          const selectedMusic = (musicAssets || []).find(a => a.id === musicChoice && a.id !== 'none');
          if (selectedMusic && selectedMusic.filename) {
            musicRules.push({
              music_filename: selectedMusic.filename,
              apply_to_segments: ['intro'],
              start_offset_s: 0,
              end_offset_s: 1,
              fade_in_s: 1.5,
              fade_out_s: 2.0,
              volume_db: -4,
            });
            musicRules.push({
              music_filename: selectedMusic.filename,
              apply_to_segments: ['outro'],
              start_offset_s: -10,
              end_offset_s: 0,
              fade_in_s: 3.0,
              fade_out_s: 1.0,
              volume_db: -4,
            });
          }

          const templatePayload = {
            name: 'My First Template',
            podcast_id: createdPodcast.id,
            segments,
            background_music_rules: musicRules,
            timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
            is_active: true,
          };
          try { await makeApi(token).post('/api/templates/', templatePayload); } catch (e) {
            // Non-fatal: user can still proceed; backend prevents last-template deletes
            try { toast({ title: 'Template not saved', description: e?.message || 'We could not save your default template.', variant: 'destructive' }); } catch {}
          }
        } catch (_) {}
      } else {
        // Import path: nothing to create here; finishing just returns to dashboard
        try { toast({ title: 'Imported', description: 'Your show has been imported.' }); } catch {}
      }
      // Send user to dashboard in either case
      try { window.location.href = '/'; } catch {}
    } catch (error) {
      try { toast({ title: 'An Error Occurred', description: error.message, variant: 'destructive' }); } catch {}
    } finally {
      setSaving(false);
    }
  }

  // Map each stepId to a render function
  const steps = wizardSteps.map((s, i) => ({
    id: s.id,
    title: s.title,
    description: s.description,
    tip: (
      s.id === 'yourName' ? "We'll use this to personalize your dashboard." :
  s.id === 'choosePath' ? 'If you have an existing podcast, import it here.' :
      s.id === 'showDetails' ? 'Short and clear works best.' :
      s.id === 'format' ? 'You can mix it up later.' :
  s.id === 'coverArt' ? 'No artwork yet? You can skip this for now.' :
  s.id === 'introOutro' ? 'Start with our default scripts or upload your own audio.' :
      s.id === 'music' ? 'Choose "No Music" to decide later.' :
  s.id === 'spreaker' ? 'Click connect to open a popup; you can come back to this later.' :
  s.id === 'publishCadence' ? 'Take your best guess — you can change this later.' :
      s.id === 'publishSchedule' ? 'Consistency beats volume.' :
      s.id === 'rss' ? 'Paste your feed URL.' :
      s.id === 'analyze' ? "We'll bring over what we can, and you can tidy later." :
      s.id === 'assets' ? "We'll bring over what we can, and you can tidy later." :
      s.id === 'finish' ? "There's a short tour next if you'd like it." : ''
    ),
    render: () => {
      switch (s.id) {
        case 'yourName':
          return (
            <div className="grid gap-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="firstName" className="text-right">First name<span className="text-red-600">*</span></Label>
                <Input id="firstName" value={firstName} onChange={(e)=>setFirstName(e.target.value)} className="col-span-3" placeholder="e.g., Alex" />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="lastName" className="text-right">Last name</Label>
                <Input id="lastName" value={lastName} onChange={(e)=>setLastName(e.target.value)} className="col-span-3" placeholder="(Optional)" />
              </div>
              {nameError && <p className="text-sm text-red-600">{nameError}</p>}
            </div>
          );
  case 'choosePath':
          return (
            <div className="space-y-4">
              <div className="flex gap-3">
                <Button
                  variant={path === 'new' ? 'default' : 'outline'}
                  onClick={() => { setPath('new'); setStepIndex(i + 1); }}
                >Start new</Button>
                <Button
                  variant={path === 'import' ? 'default' : 'outline'}
                  onClick={() => { setPath('import'); setStepIndex(0); }}
                >Import existing</Button>
              </div>
              <p className="text-sm text-muted-foreground">You can't break anything. We save as you go.</p>
            </div>
          );
        case 'showDetails':
          return (
            <div className="grid gap-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="podcastName" className="text-right">Name<span className="text-red-600">*</span></Label>
                <Input id="podcastName" value={formData.podcastName} onChange={handleChange} className="col-span-3" placeholder="e.g., 'The Morning Cup'" />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="podcastDescription" className="text-right">Description<span className="text-red-600">*</span></Label>
                <Textarea id="podcastDescription" value={formData.podcastDescription} onChange={handleChange} className="col-span-3" placeholder="e.g., 'A daily podcast about the latest tech news.'" />
              </div>
            </div>
          );
        case 'format':
          return (
            <div className="space-y-3">
              <div className="grid gap-3">
                {FORMATS.map(f => (
                  <label key={f.key} className={`border rounded p-3 cursor-pointer flex gap-3 ${formatKey===f.key? 'border-blue-600 ring-1 ring-blue-400':'hover:border-gray-400'}`}>
                    <input type="radio" name="format" className="mt-1" value={f.key} checked={formatKey===f.key} onChange={() => setFormatKey(f.key)} />
                    <span><span className="font-medium">{f.label}</span><br/><span className="text-xs text-muted-foreground">{f.desc}</span></span>
                  </label>
                ))}
              </div>
            </div>
          );
        case 'coverArt':
          return (
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="coverArt" className="text-right">Image</Label>
              <Input id="coverArt" type="file" onChange={handleChange} className="col-span-3" accept="image/png, image/jpeg" />
              <div className="col-span-4 flex items-center gap-2 mt-2">
                <input id="skipCoverNow" type="checkbox" checked={skipCoverNow} onChange={(e)=> setSkipCoverNow(e.target.checked)} />
                <Label htmlFor="skipCoverNow">Skip this for now</Label>
              </div>
            </div>
          );
        case 'introOutro':
          return (
            <div className="space-y-6">
              <div className="space-y-2">
                <div className="font-medium">Intro</div>
                <div className="flex gap-3 items-center">
                  <label className={`border rounded p-2 cursor-pointer ${introMode==='tts'?'border-blue-600':'hover:border-gray-400'}`}>
                    <input type="radio" name="introMode" value="tts" checked={introMode==='tts'} onChange={()=> setIntroMode('tts')} />
                    <span className="ml-2">Generate with AI (TTS)</span>
                  </label>
                  <label className={`border rounded p-2 cursor-pointer ${introMode==='upload'?'border-blue-600':'hover:border-gray-400'}`}>
                    <input type="radio" name="introMode" value="upload" checked={introMode==='upload'} onChange={()=> setIntroMode('upload')} />
                    <span className="ml-2">Upload a file</span>
                  </label>
                </div>
                {introMode==='tts' ? (
                  <Textarea value={introScript} onChange={(e)=> setIntroScript(e.target.value)} placeholder="Welcome to my podcast!" />
                ) : (
                  <Input type="file" accept="audio/*" onChange={(e)=> setIntroFile(e.target.files?.[0] || null)} />
                )}
                {introAsset?.filename && <div className="text-xs text-muted-foreground">Prepared: {introAsset.filename}</div>}
              </div>
              <div className="space-y-2">
                <div className="font-medium">Outro</div>
                <div className="flex gap-3 items-center">
                  <label className={`border rounded p-2 cursor-pointer ${outroMode==='tts'?'border-blue-600':'hover:border-gray-400'}`}>
                    <input type="radio" name="outroMode" value="tts" checked={outroMode==='tts'} onChange={()=> setOutroMode('tts')} />
                    <span className="ml-2">Generate with AI (TTS)</span>
                  </label>
                  <label className={`border rounded p-2 cursor-pointer ${outroMode==='upload'?'border-blue-600':'hover:border-gray-400'}`}>
                    <input type="radio" name="outroMode" value="upload" checked={outroMode==='upload'} onChange={()=> setOutroMode('upload')} />
                    <span className="ml-2">Upload a file</span>
                  </label>
                </div>
                {outroMode==='tts' ? (
                  <Textarea value={outroScript} onChange={(e)=> setOutroScript(e.target.value)} placeholder="Thank you for listening and see you next time!" />
                ) : (
                  <Input type="file" accept="audio/*" onChange={(e)=> setOutroFile(e.target.files?.[0] || null)} />
                )}
                {outroAsset?.filename && <div className="text-xs text-muted-foreground">Prepared: {outroAsset.filename}</div>}
              </div>
              <div className="space-y-2">
                <div className="grid grid-cols-4 items-center gap-4">
                  <Label className="text-right">Voice</Label>
                  <div className="col-span-3 flex items-center gap-2">
                    <select className="border rounded p-2 min-w-[220px]" value={selectedVoiceId} onChange={(e)=> setSelectedVoiceId(e.target.value)} disabled={voicesLoading || (voices?.length||0)===0}>
                      <option value="default">Default</option>
                      {voices.map((v)=>{
                        const id = v.voice_id || v.id || v.name;
                        const label = v.name || v.label || id;
                        return <option key={id} value={id}>{label}</option>;
                      })}
                    </select>
                    <Button type="button" variant="outline" onClick={previewSelectedVoice} disabled={voicesLoading || !getVoiceById(selectedVoiceId)?.preview_url}>
                      {voicePreviewing ? <Pause className="w-4 h-4 mr-2"/> : <Play className="w-4 h-4 mr-2"/>}
                      Preview
                    </Button>
                  </div>
                </div>
                {voicesLoading && <div className="text-xs text-muted-foreground">Loading voices…</div>}
                {voicesError && <div className="text-xs text-yellow-700">{voicesError}</div>}
              </div>
              <p className="text-xs text-muted-foreground">We’ll create simple defaults if you leave the scripts unchanged.</p>
            </div>
          );
        case 'music':
          return (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                {musicLoading ? 'Loading music...' : 'Pick a track or choose "No Music".'}
              </div>
              <div className="grid gap-2">
                {musicAssets.map(a => {
                  const canPreview = !!(a && a.id !== 'none' && (a.preview_url || a.url || a.filename));
                  const isActive = musicChoice === a.id;
                  const isPreviewing = musicPreviewing === a.id;
                  return (
                    <div key={a.id} className={`flex items-center gap-3 p-2 rounded border ${isActive? 'border-blue-600 bg-blue-50':'bg-card hover:border-muted-foreground/30'}`}>
                      <button
                        type="button"
                        aria-label={isPreviewing? 'Pause preview':'Play preview'}
                        disabled={!canPreview}
                        onClick={() => canPreview && togglePreview(a)}
                        className={`inline-flex items-center justify-center h-8 w-8 rounded border ${isPreviewing? 'bg-blue-600 text-white border-blue-600':'bg-white text-foreground border-muted-foreground/30'} disabled:opacity-50`}
                        title={canPreview? 'Preview 20s':'Preview not available'}
                      >
                        {isPreviewing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                      </button>
                      <label className="flex items-center gap-3 flex-1 cursor-pointer">
                        <input type="radio" name="music" value={a.id} checked={isActive} onChange={() => setMusicChoice(a.id)} />
                        <div className="flex-1">
                          <div className="text-sm font-medium">{a.display_name}</div>
                          {a.mood_tags && a.mood_tags.length > 0 && (
                            <div className="text-xs text-muted-foreground">{a.mood_tags.slice(0,3).join(', ')}</div>
                          )}
                        </div>
                      </label>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        case 'spreaker':
          return (
            <div className="flex justify-center items-center p-6 bg-accent/30 rounded-[var(--radius)]">
              {isSpreakerConnected ? (
                <Button variant="secondary" disabled className="bg-green-600 text-white hover:bg-green-600">
                  <CheckCircle className="w-5 h-5 mr-2" /> Connected
                </Button>
              ) : (
                <Button onClick={handleConnectSpreaker}>Connect to Podcast Host</Button>
              )}
            </div>
          );
        
        case 'publishDay':
          return null;
        case 'publishCadence':
          return (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-sm">I want to publish</span>
                <Input type="number" min={1} value={freqCount} onChange={(e)=> setFreqCount(Math.max(1, parseInt(e.target.value||'1',10) || 1))} className="w-20" />
                <span className="text-sm">time(s) every</span>
                <select className="border rounded p-2" value={freqUnit} onChange={(e)=> setFreqUnit(e.target.value)}>
                  <option value="" disabled>select...</option>
                  <option value="day">day</option>
                  <option value="week">week</option>
                  <option value="bi-weekly">bi-weekly</option>
                  <option value="month">month</option>
                  <option value="year">year</option>
                </select>
              </div>
              {cadenceError && <p className="text-sm text-red-600">{cadenceError}</p>}
              <p className="text-xs text-muted-foreground">We'll tailor the next step based on this.</p>
            </div>
          );
        case 'publishSchedule':
          if (freqUnit === 'week') {
            const WEEKDAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
            const toggleDay = (d) => setSelectedWeekdays((prev)=> prev.includes(d) ? prev.filter(x=>x!==d) : [...prev, d]);
            return (
              <div className="space-y-2">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {WEEKDAYS.map(d => (
                    <button type="button" key={d} onClick={()=>toggleDay(d)} className={`border rounded p-2 text-center ${selectedWeekdays.includes(d)?'border-blue-600 ring-1 ring-blue-400':'hover:border-gray-400'}`}>{d}</button>
                  ))}
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <input id="notSureSchedule" type="checkbox" checked={notSureSchedule} onChange={(e)=> setNotSureSchedule(e.target.checked)} />
                  <Label htmlFor="notSureSchedule">I'm not sure yet</Label>
                </div>
                <p className="text-xs text-muted-foreground">Pick your publishing day(s) of the week.</p>
              </div>
            );
          }
          // bi-weekly or month: simple two-month calendar picker
          const months = (()=>{
            const start = new Date();
            start.setDate(1);
            const next = new Date(start.getFullYear(), start.getMonth()+1, 1);
            return [start, next];
          })();
          const daysInMonth = (y,m)=> new Date(y, m+1, 0).getDate();
          const pad = (n)=> String(n).padStart(2,'0');
          const toggleDate = (iso)=> setSelectedDates((prev)=> prev.includes(iso) ? prev.filter(x=>x!==iso) : [...prev, iso]);
          // Sunday-first calendar headers
          const HEADERS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
          return (
            <div className="space-y-4">
              {months.map((m, idx)=>{
                const year = m.getFullYear();
                const month = m.getMonth();
                const total = daysInMonth(year, month);
                const first = new Date(year, month, 1);
                // JS: 0=Sun..6=Sat; convert to Monday-first (0..6)
                const jsFirst = first.getDay(); // 0=Sun..6=Sat
                const leadBlanks = jsFirst; // Sunday-first alignment
                const cells = [];
                for (let i=0;i<leadBlanks;i++) cells.push({ key: `b-${i}`, blank: true });
                for (let d=1; d<=total; d++) {
                  const iso = `${year}-${pad(month+1)}-${pad(d)}`;
                  cells.push({ key: iso, iso, day: d });
                }
                // Pad trailing blanks to complete the last week row
                while (cells.length % 7 !== 0) cells.push({ key: `t-${cells.length}`, blank: true });
                return (
                  <div key={idx} className="space-y-2">
                    <div className="font-medium text-sm">{m.toLocaleString(undefined,{ month:'long', year:'numeric' })}</div>
                    <div className="grid grid-cols-7 gap-1 text-[11px] text-muted-foreground">
                      {HEADERS.map(h => <div key={h} className="py-1 text-center">{h}</div>)}
                    </div>
                    <div className="grid grid-cols-7 gap-1">
                      {cells.map(cell => {
                        if (cell.blank) return <div key={cell.key} className="p-2" />;
                        const active = selectedDates.includes(cell.iso);
                        return (
                          <button
                            type="button"
                            key={cell.key}
                            onClick={()=>toggleDate(cell.iso)}
                            className={`border rounded p-2 text-center text-xs ${active?'border-blue-600 ring-1 ring-blue-400':'hover:border-gray-400'}`}
                          >
                            {cell.day}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              <div className="flex items-center gap-2 mt-2">
                <input id="notSureSchedule2" type="checkbox" checked={notSureSchedule} onChange={(e)=> setNotSureSchedule(e.target.checked)} />
                <Label htmlFor="notSureSchedule2">I'm not sure yet</Label>
              </div>
              <p className="text-xs text-muted-foreground">Pick your first publishing day(s); we'll take it from there.</p>
            </div>
          );
        case 'finish':
          return (
            <div className="space-y-2">
              <h3 className="text-lg font-semibold">Finish</h3>
              <p className="text-sm text-muted-foreground">Nice work. You can publish now or explore your dashboard.</p>
              {saving && <div className="text-xs text-muted-foreground">Working...</div>}
            </div>
          );
        // Import flow renders
        case 'rss':
          return (
            <div className="grid gap-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="rssUrl" className="text-right">RSS URL</Label>
                <Input id="rssUrl" value={rssUrl} onChange={(e)=> setRssUrl(e.target.value)} className="col-span-3" placeholder="https://example.com/feed.xml" />
              </div>
            </div>
          );
        case 'confirm':
          return (
            <div className="space-y-3">
              <p className="text-sm">We'll import episodes and assets from:</p>
              <div className="p-3 rounded border bg-accent/30 text-sm break-all">{rssUrl || '-'}</div>
              <p className="text-xs text-muted-foreground">Click Continue to start the import.</p>
            </div>
          );
        case 'importing':
          return (<div className="text-sm">Importing... This may take a moment.</div>);
        case 'analyze':
          return (<div className="text-sm">Analyzing your feed and extracting settings...</div>);
        case 'assets':
          return (<div className="text-sm">Pulling cover art and audio assets...</div>);
        case 'importSuccess':
          return (
            <div className="space-y-2">
              <h3 className="text-lg font-semibold">Imported</h3>
              <p className="text-sm text-muted-foreground">Your show is in Podcast Pro Plus. Explore your episodes on the dashboard.</p>
            </div>
          );
        default:
          return null;
      }
    },
  // Keep validations lenient: prefer step-provided validate, then intercept where needed
  validate: s.validate ? s.validate : s.id === 'publishCadence' ? async () => {
      if (!freqUnit) {
        setCadenceError('Please choose a frequency.');
        return false;
      }
      if (freqUnit === 'bi-weekly' && Number(freqCount) !== 1) {
        setCadenceError('For bi-weekly, X must be 1.');
        return false;
      }
      setCadenceError('');
      return true;
    } : s.id === 'publishSchedule' ? async () => {
      if (notSureSchedule) return true;
      if (freqUnit === 'week' && selectedWeekdays.length === 0) return false;
      if ((freqUnit === 'bi-weekly' || freqUnit === 'month') && selectedDates.length === 0) return false;
      return true;
    } : s.id === 'confirm' && path === 'import' ? async () => {
      // Start import on Continue
      try {
        if (!rssUrl) return true; // lenient: allow moving forward even if blank
        try { await makeApi(token).post('/api/import/rss', { rss_url: rssUrl.trim() }); } catch {}
      } catch {}
      return true;
    } : s.id === 'showDetails' ? async () => {
      const nameOk = (formData.podcastName || '').trim().length > 0;
      const descOk = (formData.podcastDescription || '').trim().length > 0;
      return nameOk && descOk;
    } : s.id === 'coverArt' ? async () => {
      // Require cover or explicit skip
      if (formData.coverArt || skipCoverNow) return true;
      return false;
    } : s.id === 'introOutro' ? async () => {
      // Prepare assets as needed; if already prepared, allow continue
      if (!introAsset) {
        const ia = await generateOrUploadTTS('intro', introMode, introScript, introFile);
        if (ia) setIntroAsset(ia);
      }
      if (!outroAsset) {
        const oa = await generateOrUploadTTS('outro', outroMode, outroScript, outroFile);
        if (oa) setOutroAsset(oa);
      }
      // Allow continue even if one fails; template can be content-only
      return true;
    } : s.id === 'spreaker' ? async () => {
      // Must click connect at least once to proceed
      return !!spreakerClicked || !!isSpreakerConnected;
    } : undefined,
  }));

  // Auto-advance simple import progress steps
  useEffect(() => {
    let t;
    if (path === 'import') {
      if (stepId === 'importing') {
        t = setTimeout(() => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)), 1000);
      } else if (stepId === 'analyze') {
        t = setTimeout(() => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)), 800);
      } else if (stepId === 'assets') {
        t = setTimeout(() => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)), 800);
      }
    }
    return () => { if (t) clearTimeout(t); };
  }, [path, stepId, wizardSteps.length]);

  // Compute gating for Next/Finish and hide rules
  const { nextDisabled, hideNext } = useMemo(() => {
    let disabled = false;
    let hide = false;
    switch (stepId) {
      case 'choosePath':
        // Special UX: hide Continue; use Start new / Import existing buttons
        hide = true;
        break;
      case 'yourName': {
        disabled = !(firstName || '').trim();
        break;
      }
      case 'showDetails': {
        const nameOk = (formData.podcastName || '').trim().length > 0;
        const descOk = (formData.podcastDescription || '').trim().length > 0;
        disabled = !(nameOk && descOk);
        break;
      }
      case 'coverArt': {
        disabled = !(formData.coverArt || skipCoverNow);
        break;
      }
      case 'spreaker': {
        disabled = !(spreakerClicked || isSpreakerConnected);
        break;
      }
      case 'publishCadence': {
        disabled = !freqUnit || (freqUnit === 'bi-weekly' && Number(freqCount) !== 1);
        break;
      }
      case 'publishSchedule': {
        if (!notSureSchedule) {
          if (freqUnit === 'week') disabled = selectedWeekdays.length === 0; else if (freqUnit === 'bi-weekly' || freqUnit === 'month') disabled = selectedDates.length === 0;
        }
        break;
      }
      default:
        break;
    }
    return { nextDisabled: !!disabled, hideNext: !!hide };
  }, [stepId, firstName, formData.podcastName, formData.podcastDescription, formData.coverArt, skipCoverNow, spreakerClicked, isSpreakerConnected, freqUnit, freqCount, notSureSchedule, selectedWeekdays.length, selectedDates.length]);

  return (
    <OnboardingWrapper
      steps={steps}
      index={stepIndex}
      setIndex={setStepIndex}
      onComplete={handleFinish}
      prefs={{ largeText, setLargeText, highContrast, setHighContrast }}
      greetingName={firstName?.trim() || ''}
      nextDisabled={nextDisabled}
      hideNext={hideNext}
    />
  );
}
