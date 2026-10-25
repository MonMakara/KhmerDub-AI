import React, { useState, useRef, useEffect } from 'react';
import { MoreVertical, Play, Edit3, Trash2 } from 'lucide-react';

interface ProjectActionMenuProps {
  onOpenStudio: () => void;
  onRename: () => void;
  onDelete: () => void;
  buttonClassName?: string;
}

export const ProjectActionMenu: React.FC<ProjectActionMenuProps> = ({
  onOpenStudio,
  onRename,
  onDelete,
  buttonClassName = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div className="relative inline-block text-left" ref={menuRef}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen((prev) => !prev);
        }}
        className={`p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${buttonClassName}`}
        title="Project actions"
        aria-label="Project actions"
      >
        <MoreVertical className="w-4 h-4" />
      </button>

      {isOpen && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute right-0 mt-1 w-44 rounded-xl bg-white shadow-lg ring-1 ring-black/5 border border-slate-100 py-1 z-30 animate-in fade-in zoom-in-95 duration-100"
        >
          <button
            type="button"
            onClick={() => {
              setIsOpen(false);
              onOpenStudio();
            }}
            className="w-full flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-indigo-600 transition-colors text-left"
          >
            <Play className="w-3.5 h-3.5 text-indigo-500" />
            <span>Open Studio</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setIsOpen(false);
              onRename();
            }}
            className="w-full flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-indigo-600 transition-colors text-left"
          >
            <Edit3 className="w-3.5 h-3.5 text-slate-400" />
            <span>Rename Project</span>
          </button>

          <div className="my-1 border-t border-slate-100" />

          <button
            type="button"
            onClick={() => {
              setIsOpen(false);
              onDelete();
            }}
            className="w-full flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 hover:text-rose-700 transition-colors text-left"
          >
            <Trash2 className="w-3.5 h-3.5 text-rose-500" />
            <span>Delete Project</span>
          </button>
        </div>
      )}
    </div>
  );
};
