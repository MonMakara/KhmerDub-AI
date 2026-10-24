import React from 'react';
import { Cpu, HardDrive, Terminal, Info } from 'lucide-react';
import { HealthResponse } from '../types';

interface SettingsProps {
  health: HealthResponse | null;
}

export const Settings: React.FC<SettingsProps> = ({ health }) => {
  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-bold text-slate-900">System Configuration</h2>
        <p className="text-xs text-slate-500 mt-1">
          Review environment parameters, hardware allocation, and storage mount points.
        </p>
      </div>

      {/* Hardware & Acceleration Status */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Compute & Hardware</h3>
            <p className="text-xs text-slate-500">Current device configuration for AI inference</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-medium">Whisper Device:</span>
            <div className="font-semibold text-slate-800 text-sm mt-1 uppercase">
              {health?.system_info?.whisper_device || 'CPU'}
            </div>
            <p className="text-slate-400 mt-1">Initial CPU execution ensures 100% reproducible startup without CUDA driver locks.</p>
          </div>

          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-medium">Whisper Model Size:</span>
            <div className="font-semibold text-slate-800 text-sm mt-1">
              {health?.system_info?.whisper_model || 'base'} (int8 quantized)
            </div>
            <p className="text-slate-400 mt-1">Optimized for low RAM footprint and fast inference on Intel i7 laptop CPU.</p>
          </div>
        </div>

        {/* NVIDIA GPU Note */}
        <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 text-xs text-amber-900 flex gap-3">
          <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold">Optional NVIDIA RTX 4060 GPU Acceleration</p>
            <p className="text-amber-800">
              Per requirements, Version 1 defaults to CPU execution to guarantee zero-hassle startup. 
              Once Phase 1 is validated, the Docker Compose configuration can be toggled to utilize 
              the NVIDIA Container Toolkit (<code className="font-mono bg-amber-100 px-1 rounded">runtime: nvidia</code>) 
              for CUDA-accelerated Whisper and NLLB inference without touching application logic.
            </p>
          </div>
        </div>
      </div>

      {/* Storage and Mount Points */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
            <HardDrive className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Storage & Volumes</h3>
            <p className="text-xs text-slate-500">Persistent storage mounts and media caching</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-sans block text-[11px] mb-1">Uploads Path</span>
            <span className="text-slate-800 font-semibold">/app/data/uploads</span>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-sans block text-[11px] mb-1">Outputs Path</span>
            <span className="text-slate-800 font-semibold">/app/data/outputs</span>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-sans block text-[11px] mb-1">AI Model Cache</span>
            <span className="text-slate-800 font-semibold">/root/.cache</span>
          </div>
        </div>
      </div>

      {/* Docker Dev Environment Tips */}
      <div className="bg-slate-900 rounded-xl p-6 text-white text-xs space-y-4">
        <div className="flex items-center gap-2 text-slate-300 font-semibold text-sm">
          <Terminal className="w-4 h-4 text-indigo-400" />
          <span>Quick Control Commands</span>
        </div>
        <div className="space-y-2 font-mono text-slate-300">
          <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
            docker compose logs -f backend
          </div>
          <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
            docker compose exec backend pytest
          </div>
          <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
            docker compose down
          </div>
        </div>
      </div>
    </div>
  );
};
