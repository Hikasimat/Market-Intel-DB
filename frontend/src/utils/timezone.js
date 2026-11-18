export function localDateTimeToUTC(dateStr, timeStr, timeZone) {
    if (!timeZone) timeZone = 'UTC';
    
    let [year, month, day] = dateStr.split('-').map(Number);
    let [hour, minute] = timeStr.split(':').map(Number);
    
    let utcGuess = new Date(Date.UTC(year, month - 1, day, hour, minute, 0));
    let currentUtc = utcGuess.getTime();
    
    for (let i = 0; i < 4; i++) {
        let parts;
        try {
            parts = new Intl.DateTimeFormat('en-US', {
                timeZone,
                year: 'numeric', month: 'numeric', day: 'numeric',
                hour: 'numeric', minute: 'numeric', second: 'numeric',
                hourCycle: 'h23'
            }).formatToParts(new Date(currentUtc));
        } catch (e) {
            // Fallback for invalid timezone
            return new Date(`${dateStr}T${timeStr}:00Z`).toISOString();
        }
        
        const p = {};
        parts.forEach(part => { p[part.type] = parseInt(part.value, 10); });
        if (p.hour === 24) p.hour = 0;
        
        const localInTZ = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
        const targetLocal = Date.UTC(year, month - 1, day, hour, minute, 0);
        
        const diff = targetLocal - localInTZ;
        if (diff === 0) break;
        currentUtc += diff;
    }
    
    return new Date(currentUtc).toISOString();
}

export function formatDateTimeForUser(utcString, timeZone) {
    if (!utcString) return '';
    if (!timeZone) timeZone = 'UTC';
    const d = new Date(utcString);
    try {
        return d.toLocaleString('en-US', {
            timeZone,
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch (e) {
        return d.toLocaleString();
    }
}

export function formatTimeForUser(utcString, timeZone) {
    if (!utcString) return '';
    if (!timeZone) timeZone = 'UTC';
    const d = new Date(utcString);
    try {
        return d.toLocaleTimeString('en-US', {
            timeZone,
            hour: '2-digit', minute: '2-digit'
        });
    } catch (e) {
        return d.toLocaleTimeString();
    }
}

/**
 * Returns a naive Date object where local accessors (.getHours(), .getDate(), etc) 
 * will return the values of the given timezone. This allows existing grid 
 * calendars relying on local time to work correctly.
 */
export function getZonedDate(dateInput, timeZone) {
    if (!timeZone) timeZone = 'UTC';
    const d = dateInput ? new Date(dateInput) : new Date();
    try {
        const str = d.toLocaleString('en-US', { timeZone, hourCycle: 'h23' }); 
        // e.g. "9/24/2026, 13:28:38"
        return new Date(str);
    } catch (e) {
        return d;
    }
}

const FALLBACK_TIMEZONES = [
    'UTC',
    'Africa/Cairo',
    'Africa/Johannesburg',
    'Africa/Lagos',
    'Africa/Nairobi',
    'America/Anchorage',
    'America/Argentina/Buenos_Aires',
    'America/Bogota',
    'America/Chicago',
    'America/Denver',
    'America/Halifax',
    'America/Lima',
    'America/Los_Angeles',
    'America/Mexico_City',
    'America/New_York',
    'America/Phoenix',
    'America/Santiago',
    'America/Sao_Paulo',
    'America/St_Johns',
    'America/Toronto',
    'America/Vancouver',
    'Asia/Bahrain',
    'Asia/Bangkok',
    'Asia/Colombo',
    'Asia/Dhaka',
    'Asia/Dubai',
    'Asia/Hong_Kong',
    'Asia/Jakarta',
    'Asia/Karachi',
    'Asia/Kathmandu',
    'Asia/Kolkata',
    'Asia/Kuala_Lumpur',
    'Asia/Kuwait',
    'Asia/Manila',
    'Asia/Muscat',
    'Asia/Qatar',
    'Asia/Riyadh',
    'Asia/Seoul',
    'Asia/Shanghai',
    'Asia/Singapore',
    'Asia/Taipei',
    'Asia/Tehran',
    'Asia/Tokyo',
    'Asia/Yangon',
    'Australia/Adelaide',
    'Australia/Brisbane',
    'Australia/Darwin',
    'Australia/Melbourne',
    'Australia/Perth',
    'Australia/Sydney',
    'Europe/Amsterdam',
    'Europe/Athens',
    'Europe/Berlin',
    'Europe/Istanbul',
    'Europe/Lisbon',
    'Europe/London',
    'Europe/Madrid',
    'Europe/Moscow',
    'Europe/Paris',
    'Europe/Rome',
    'Europe/Zurich',
    'Pacific/Auckland',
    'Pacific/Honolulu',
];

let _cachedTimeZoneOptions = null;

function _formatGmtOffset(timeZone, now) {
    if (timeZone === 'UTC') return 'UTC+00:00';
    try {
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone,
            timeZoneName: 'shortOffset',
        }).formatToParts(now);
        const tzPart = parts.find((p) => p.type === 'timeZoneName')?.value || '';
        return tzPart || '';
    } catch {
        return '';
    }
}

export function getAllTimeZoneOptions() {
    if (_cachedTimeZoneOptions) return _cachedTimeZoneOptions;
    let zones;
    try {
        zones = typeof Intl?.supportedValuesOf === 'function'
            ? Intl.supportedValuesOf('timeZone')
            : FALLBACK_TIMEZONES;
    } catch {
        zones = FALLBACK_TIMEZONES;
    }
    const zoneSet = new Set(['UTC', ...(zones || [])]);
    const now = new Date();
    _cachedTimeZoneOptions = Array.from(zoneSet)
        .sort((a, b) => {
            if (a === 'UTC') return -1;
            if (b === 'UTC') return 1;
            return a.localeCompare(b);
        })
        .map((tz) => {
            const offset = _formatGmtOffset(tz, now);
            const displayName = tz.replace(/_/g, ' ');
            return {
                value: tz,
                label: offset ? `${displayName} (${offset})` : displayName,
            };
        });
    return _cachedTimeZoneOptions;
}
