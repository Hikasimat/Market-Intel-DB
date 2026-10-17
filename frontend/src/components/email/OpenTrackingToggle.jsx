import React, { useEffect, useState } from 'react';
import { Eye } from 'lucide-react';
import api from '../../services/api';

// Session-level cache of the server's global tracking switch.
let cachedAvailability = null;

/**
 * "Enable email open tracking" opt-in. Unchecked by default and never forced on.
 * If the server's EMAIL_OPEN_TRACKING_ENABLED is off (or can't be determined) the
 * control is disabled and the parent value is forced to false. The backend enforces the
 * same rule, so this is only an accurate reflection of server behaviour.
 */
export default function OpenTrackingToggle({ checked, onChange, disabled = false, id = 'enable-open-tracking' }) {
  const [available, setAvailable] = useState(cachedAvailability);

  useEffect(() => {
    if (cachedAvailability !== null) return undefined;
    let cancelled = false;
    api.get('/outreach/emails/tracking-config/')
      .then((res) => {
        cachedAvailability = !!res.data?.open_tracking_available;
        if (!cancelled) setAvailable(cachedAvailability);
      })
      .catch(() => {
        // Unknown => treat as unavailable (safe default); do not cache the failure.
        if (!cancelled) setAvailable(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (available === false && checked) onChange(false);
  }, [available, checked, onChange]);

  const unavailable = available === false;
  const isDisabled = disabled || unavailable || available === null;

  return (
    <div className="flex items-start gap-2" data-testid="open-tracking-toggle">
      <input
        type="checkbox"
        id={id}
        checked={!!checked && !unavailable}
        disabled={isDisabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500 disabled:opacity-50"
      />
      <label htmlFor={id} className={`text-[11px] font-bold ${isDisabled ? 'text-slate-400' : 'text-slate-700 cursor-pointer'}`}>
        <span className="inline-flex items-center gap-1"><Eye className="w-3 h-3" /> Enable email open tracking</span>
        <span className="block text-[10px] font-medium text-slate-400">
          {unavailable
            ? 'Open tracking is disabled by the administrator for this server.'
            : 'Off by default. Adds a tiny tracking image, which can reduce deliverability.'}
        </span>
      </label>
    </div>
  );
}
