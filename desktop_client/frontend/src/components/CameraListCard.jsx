import { Video, MapPin, Settings, Trash2, CheckCircle2 } from 'lucide-react';

const STATUS_DOT_COLORS = {
  active: 'bg-success',
  inactive: 'bg-text-muted',
  error: 'bg-danger',
};

/**
 * CameraListCard - Clickable card representing a camera in the video wall source panel.
 */
export default function CameraListCard({ camera = {}, isActive = false, onToggle, onEdit, onDelete }) {
  const statusKey = camera.status?.toLowerCase();
  const statusDot = STATUS_DOT_COLORS[statusKey] || 'bg-text-muted';
  const locationInfo = [camera.department, camera.location].filter(Boolean).join(' • ');

  return (
    <div
      onClick={() => onToggle(camera)}
      className={`group bg-bg-elevated border rounded-md p-2.5 transition-all duration-150 select-none cursor-pointer
        ${isActive ? 'border-accent shadow-[0_0_0_1px_rgba(37,99,235,0.4)]' : 'border-border-secondary hover:bg-bg-hover hover:border-border-primary'}
      `}
    >
      {/* Top Row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          {isActive ? (
            <CheckCircle2 className="w-4 h-4 text-accent shrink-0" />
          ) : (
            <Video className="w-4 h-4 text-text-muted shrink-0" />
          )}
          <span className={`font-bold text-sm truncate ${isActive ? 'text-accent' : 'text-text-primary'}`}>
            Camera #{camera.camera_id} {camera.name ? `- ${camera.name}` : ''}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <span
            className={`w-2 h-2 rounded-full ${statusDot}`}
            title={`Status: ${camera.status || 'Unknown'}`}
          />
        </div>
      </div>

      {/* Bottom Row */}
      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-text-muted pl-[22px] min-h-[20px]">
        {locationInfo ? (
          <div className="flex items-center gap-1 min-w-0 truncate">
            <MapPin className="w-3 h-3 text-text-muted shrink-0" />
            <span className="truncate">{locationInfo}</span>
          </div>
        ) : (
          <div />
        )}

        <div className="flex items-center gap-1.5 shrink-0">
          {camera.camera_type && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-primary text-text-secondary border border-border-secondary font-medium uppercase shrink-0">
              {camera.camera_type}
            </span>
          )}
          
          {/* Quick Actions (visible on hover) */}
          <div className="hidden group-hover:flex items-center gap-1">
            <button 
              className="p-1 rounded text-text-muted hover:text-accent hover:bg-accent/10 transition-colors"
              title="Edit Camera"
              onClick={(e) => { e.stopPropagation(); onEdit?.(camera); }}
            >
              <Settings className="w-3.5 h-3.5" />
            </button>
            <button 
              className="p-1 rounded text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
              title="Delete Camera"
              onClick={(e) => { e.stopPropagation(); onDelete?.(camera); }}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
