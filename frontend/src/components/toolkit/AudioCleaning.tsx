import React, { useEffect, useRef, useState } from 'react';
import { AudioLines, CheckCircle2, Download, FileAudio, FolderGit2, Mic2, Music2, RefreshCw, Settings2, Upload } from 'lucide-react';
import { api } from '../../services/api';
import { ProjectSummary, ToolkitTask } from '../../types';

interface Props {
  projects: ProjectSummary[];
  initialTask: ToolkitTask | null;
  onTaskUpdate: (task: ToolkitTask) => void;
}

const active = (task: ToolkitTask | null) => Boolean(task && ['pending', 'processing', 'cancelling'].includes(task.status));

export const AudioCleaning: React.FC<Props> = ({ projects, initialTask, onTaskUpdate }) => {
  const [task, setTask] = useState<ToolkitTask | null>(initialTask?.tool_type === 'audio_cleaning' ? initialTask : null);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState('upload');
  const [projectId, setProjectId] = useState('');
  const [mode, setMode] = useState('noise');
  const [strength, setStrength] = useState('balanced');
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [caps, setCaps] = useState<Awaited<ReturnType<typeof api.getCleaningCapabilities>> | null>(null);
  const original = useRef<HTMLAudioElement>(null);
  const cleaned = useRef<HTMLAudioElement>(null);
  const background = useRef<HTMLAudioElement>(null);
  const notify = useRef(onTaskUpdate);
  notify.current = onTaskUpdate;

  useEffect(() => {
    let mounted = true;
    api.getCleaningCapabilities().then(c => { if (mounted) setCaps(c); })
      .catch(e => { if (mounted) setError(e.message); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (initialTask?.tool_type === 'audio_cleaning') setTask(initialTask);
  }, [initialTask?.id]);

  useEffect(() => {
    if (!task || !active(task)) return;
    let mounted = true;
    let timer: ReturnType<typeof setTimeout>;
    const id = task.id;
    const poll = async () => {
      try {
        const fresh = await api.getToolkitTask(id);
        if (!mounted) return;
        setTask(fresh);
        notify.current(fresh);
        if (active(fresh)) timer = setTimeout(poll, 1000);
      } catch (e) {
        if (!mounted) return;
        setError(e instanceof Error ? e.message : 'Could not refresh processing status.');
        timer = setTimeout(poll, 2500);
      }
    };
    timer = setTimeout(poll, 500);
    return () => { mounted = false; clearTimeout(timer); };
  }, [task?.id, task?.status]);

  const chooseFile = (candidate: File | undefined) => {
    if (!candidate) return;
    if (!/\.(wav|mp3|m4a|flac|ogg|mp4|mov|mkv|webm)$/i.test(candidate.name)) {
      setError('Choose a supported audio or video file.'); return;
    }
    if (caps && candidate.size > caps.max_upload_size_mb * 1024 * 1024) {
      setError(`Maximum file size is ${caps.max_upload_size_mb} MB.`); return;
    }
    setFile(candidate); setSource('upload'); setError(null);
  };

  const start = async () => {
    setError(null); setUploading(true); setUploaded(0);
    const data = new FormData();
    if (source === 'upload' && file) data.append('file', file);
    else data.append('project_id', projectId);
    data.append('mode', mode); data.append('strength', strength);
    try {
      const result = await api.startAudioCleaning(data, setUploaded);
      setTask(result); notify.current(result);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start processing.'); }
    finally { setUploading(false); }
  };

  const cancel = async () => {
    if (!task) return;
    try { const result = await api.cancelAudioCleaning(task.id); setTask(result); notify.current(result); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not cancel processing.'); }
  };

  const sync = (from: HTMLAudioElement, to: HTMLAudioElement | null) => {
    if (to && Number.isFinite(to.duration) && Math.abs(from.currentTime - to.currentTime) > .05) {
      to.currentTime = Math.min(from.currentTime, to.duration);
    }
  };
  const meta = task?.output_media_metadata || {};
  const busy = uploading || active(task);
  const completed = task?.status === 'completed';
  const files: string[] = meta.files || [];

  return <div className="space-y-6">
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
      <div><h2 className="flex gap-2 items-center text-xl font-bold text-slate-900"><Mic2 className="w-5 h-5 text-indigo-600" />Audio Noise &amp; Music Remover</h2>
        <p className="text-sm text-slate-500 mt-0.5">Clean background sound and compare your speech before exporting.</p></div>
      <div className="flex items-center self-start sm:self-auto bg-slate-100 p-1 rounded-xl text-xs font-semibold" aria-label="Audio source">
        {([{ id: 'upload', label: 'Upload File', Icon: Upload }, { id: 'project', label: 'Projects', Icon: FolderGit2 }] as const).map(({ id, label, Icon }) =>
          <button key={id} type="button" aria-pressed={source === id} disabled={busy} onClick={() => setSource(id)}
            className={`px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1.5 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${source === id ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}>
            <Icon className="w-3.5 h-3.5" />{label}</button>)}
      </div>
    </div>
    <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 sm:p-5">
      {source === 'upload' ? <div onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) chooseFile(e.dataTransfer.files[0]); }}
        className="relative rounded-xl border-2 border-dashed border-slate-300 hover:border-indigo-400 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20 bg-white p-6 text-center transition-colors group">
        <FileAudio className="w-10 h-10 mx-auto text-slate-400 group-hover:text-indigo-600 transition-colors" />
        <p className="mt-2 text-sm font-semibold text-slate-700 break-all">{file?.name || 'Click or drop audio or video to upload'}</p>
        <label className="cursor-pointer">
          <input aria-label="Audio or video to clean" type="file" accept=".wav,.mp3,.m4a,.flac,.ogg,.mp4,.mov,.mkv,.webm" disabled={busy}
            onChange={e => chooseFile(e.target.files?.[0])} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed" /></label>
        <p className="text-xs text-slate-400 mt-1">WAV, MP3, M4A, FLAC, OGG, MP4, MOV, MKV, WebM · up to {caps?.max_upload_size_mb || '…'} MB</p>
      </div> : <label className="block text-xs font-semibold text-slate-700">Select source project
        <select aria-label="Source project for audio cleanup" value={projectId} disabled={busy} onChange={e => setProjectId(e.target.value)} className="block w-full px-3 py-2 text-sm bg-white border border-slate-300 rounded-xl mt-2 focus:outline-none focus:ring-2 focus:ring-indigo-500">
          <option value="">Select a project</option>{projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
        </select><span className="block mt-2 text-xs font-normal text-slate-500">A copy of your project video will be processed.</span></label>}
    </div>
    <div className="bg-white rounded-2xl border border-slate-200 p-4 sm:p-5 space-y-5">
      <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2"><Settings2 className="w-4 h-4 text-indigo-600" />Processing settings</h3>
      <fieldset><legend className="text-xs font-semibold text-slate-700 mb-2">Processing mode</legend>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {([{ id: 'noise', label: 'Background noise removal', description: 'Reduce fan noise, hiss and steady background sound.', Icon: AudioLines },
            { id: 'music', label: 'Voice isolation / music removal', description: 'Separate speech from overlapping background music.', Icon: Music2 }] as const).map(({ id, label, description, Icon }) =>
            <label key={id} className={`relative flex items-start gap-3 rounded-xl border p-4 transition-colors ${busy || (id === 'music' && !caps?.music_available) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'} ${mode === id ? 'border-indigo-400 bg-indigo-50/60' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
              <input type="radio" name="clean-mode" value={id} checked={mode === id} disabled={busy || (id === 'music' && !caps?.music_available)} onChange={() => setMode(id)} className="sr-only peer" />
              <Icon className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5" />
              <span className="flex-1"><span className="block text-sm font-semibold text-slate-800">{label}</span><span className="block text-xs text-slate-500 mt-1 leading-relaxed">{description}</span></span>
              <span className={`w-4 h-4 mt-0.5 shrink-0 rounded-full border peer-focus-visible:ring-2 peer-focus-visible:ring-indigo-500 peer-focus-visible:ring-offset-2 ${mode === id ? 'border-indigo-600 border-[5px] bg-white' : 'border-slate-300'}`} />
            </label>)}
        </div>
        {!caps?.music_available && <p className="text-xs text-amber-800">{caps?.music_reason || 'Checking processing engines…'}</p>}
      </fieldset>
      <label className="block text-xs font-semibold text-slate-700">Processing strength
        <select aria-label="Processing strength" value={strength} disabled={busy} onChange={e => setStrength(e.target.value)} className="block w-full sm:max-w-md border border-slate-300 bg-white rounded-xl px-3 py-2 mt-2 text-sm font-normal focus:outline-none focus:ring-2 focus:ring-indigo-500">
          <option value="light">Light — gentle, best speech preservation</option><option value="balanced">Balanced — moderate reduction</option><option value="strong">Strong — noisy recordings, more artifact risk</option>
        </select></label>
      {strength === 'strong' && <p className="text-xs text-amber-800">Strong processing can affect quiet syllables or voice quality. Try Light if speech sounds less natural.</p>}
      <p className="text-xs text-slate-500 leading-relaxed">The first audio track is processed. Compare the result to check speech clarity before exporting.</p>
      <div className="flex gap-3 flex-wrap border-t border-slate-100 pt-4"><button onClick={start} disabled={busy || !caps?.noise_available || (source === 'upload' ? !file : !projectId)} className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex gap-2 items-center focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2">
        {busy ? <RefreshCw className="animate-spin w-4 h-4" /> : <Mic2 className="w-4 h-4" />}{uploading ? `Uploading ${uploaded}%` : active(task) ? 'Processing…' : 'Start processing'}</button>
        {active(task) && <button onClick={cancel} disabled={task?.status === 'cancelling'} className="border border-slate-300 hover:bg-slate-50 text-sm font-semibold text-slate-700 px-4 py-2.5 rounded-xl cursor-pointer disabled:opacity-50">{task?.status === 'cancelling' ? 'Stopping…' : 'Cancel processing'}</button>}</div>
      {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-xl p-3">{error}</p>}
    </div>
    {task && <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4"><div className="min-w-0"><h3 className="text-sm font-bold text-slate-800">{completed ? 'Cleaned audio & exports' : 'Processing task'}</h3><p className="text-xs text-slate-500 mt-1 break-all">{task.source_filename}</p></div><span role="status" className={`self-start inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold ${completed ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>{completed && <CheckCircle2 className="w-3.5 h-3.5" />}{meta.phase || task.status} · {task.source_media_metadata?.strength || strength}</span></div>
      {active(task) && <div><progress aria-label="Estimated cleanup progress" max={100} value={task.progress_percentage} className="w-full" /><p className="text-xs text-slate-500">Overall stage estimate: {task.progress_percentage}%{typeof meta.phase_progress === 'number' ? ` · current pass: ${meta.phase_progress}%` : ''}</p></div>}
      {task.error_message && <p role="alert" className="text-sm text-rose-700">{task.error_message}</p>}
      {completed && <>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-slate-50 rounded-xl border border-slate-200 p-4"><h3 className="text-xs font-semibold text-slate-700 mb-3">Original audio</h3><audio aria-label="Original audio comparison" ref={original} controls preload="metadata" className="w-full" src={api.getCleaningFileUrl(task.id, 'original')}
            onPlay={() => { cleaned.current?.pause(); background.current?.pause(); }} onSeeked={e => { sync(e.currentTarget, cleaned.current); sync(e.currentTarget, background.current); }} /></div>
          <div className="bg-indigo-50/50 rounded-xl border border-indigo-100 p-4"><h3 className="text-xs font-semibold text-indigo-700 mb-3">Cleaned audio</h3><audio aria-label="Cleaned audio comparison" ref={cleaned} controls preload="metadata" className="w-full" src={api.getCleaningFileUrl(task.id, 'wav')}
            onPlay={() => { original.current?.pause(); background.current?.pause(); }} onSeeked={e => { sync(e.currentTarget, original.current); sync(e.currentTarget, background.current); }} /></div>
        </div>
        {files.includes('background.wav') && <div><h3 className="text-sm font-semibold mb-2">Removed background — check for speech leakage</h3>
          <audio aria-label="Removed background comparison" ref={background} controls preload="metadata" className="w-full" src={api.getCleaningFileUrl(task.id, 'background')}
            onPlay={() => { original.current?.pause(); cleaned.current?.pause(); }} onSeeked={e => { sync(e.currentTarget, original.current); sync(e.currentTarget, cleaned.current); }} /></div>}
        <p className="text-xs text-slate-500">Engine: {meta.engine} · {meta.device?.toUpperCase()}</p>
        <p className="text-xs text-slate-500">Seeking is linked for comparison; starting one player pauses the other. {Number(meta.output_audio_duration || task.output_duration_seconds).toFixed(3)} seconds.</p>
        <div className="flex gap-3 flex-wrap">{(['wav', 'mp3'] as const).map(format => <a key={format} href={api.getCleaningFileUrl(task.id, format, true)} className="px-3 py-2 rounded-lg bg-indigo-50 text-indigo-700 font-semibold text-sm flex items-center gap-2"><Download className="w-4 h-4" />Download clean {format.toUpperCase()}</a>)}
          {files.includes('cleaned.mp4') && <a href={api.getCleaningFileUrl(task.id, 'video', true)} className="px-3 py-2 rounded-lg bg-indigo-50 text-indigo-700 font-semibold text-sm">Download clean video</a>}</div>
        {meta.video_warning && <p className="text-sm text-amber-800">{meta.video_warning}</p>}
        <p className="text-xs text-slate-500">{meta.quality_notice}</p>
      </>}
    </div>}
  </div>;
};
