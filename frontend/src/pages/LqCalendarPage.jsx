import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
  Clock,
  ExternalLink,
  Video,
  RefreshCw,
  Users,
  X,
  Copy,
  Check,
  LogOut,
  ChevronsUpDown,
  Link2,
  AlignLeft,
  ArrowRight,
  Trash2,
  Plus,
  AlertCircle,
} from "lucide-react";
import { useSelector } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { toast } from "react-toastify";
import api from "../services/api";
import { getZonedDate, formatTimeForUser, formatDateTimeForUser } from "../utils/timezone";

const HOUR_HEIGHT = 74;
const START_HOUR = 7;
const END_HOUR = 23;

// Pastel color palette matching design specification
const COLOR_OPTIONS = [
  { id: "lavender", bg: "#e8e1fa", text: "#4a3672", border: "#d5c8f2", timeText: "#6b5894", name: "Lavender" },
  { id: "skyblue", bg: "#dff1fd", text: "#194f75", border: "#bee3fb", timeText: "#286b99", name: "Sky Blue" },
  { id: "mint", bg: "#dcf3e7", text: "#1e5838", border: "#b9e6ce", timeText: "#2d7a52", name: "Mint Green" },
  { id: "peach", bg: "#fef3c7", text: "#854d0e", border: "#fde68a", timeText: "#a16207", name: "Peach" },
  { id: "gray", bg: "#f1f5f9", text: "#334155", border: "#e2e8f0", timeText: "#64748b", name: "Slate Gray" },
];

function getColorConfig(colorId) {
  const found = COLOR_OPTIONS.find((c) => c.id === colorId);
  return found || COLOR_OPTIONS[0];
}

// Convert event index/id to deterministic pastel color
function pickEventColor(evt, index = 0) {
  if (evt.colorId && COLOR_OPTIONS.some((c) => c.id === evt.colorId)) {
    return evt.colorId;
  }
  return COLOR_OPTIONS[index % COLOR_OPTIONS.length].id;
}

export default function LqCalendarPage() {
  const { user } = useSelector((state) => state.auth);
  const [searchParams, setSearchParams] = useSearchParams();

  const getZonedNow = useCallback(() => getZonedDate(null, user?.timezone), [user?.timezone]);
  const [currentDate, setCurrentDate] = useState(() => getZonedDate(null, null));
  const [miniCalDate, setMiniCalDate] = useState(() => getZonedDate(null, null));
  const [loading, setLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncedTime, setLastSyncedTime] = useState(null);
  const [calendarStatus, setCalendarStatus] = useState({ is_connected: false, is_configured: false, email: "" });
  const [events, setEvents] = useState([]);
  const [viewMode, setViewMode] = useState("week"); // 'day' | 'week' | 'month'
  const [nowMinute, setNowMinute] = useState(0);

  // Selected event modal
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [copiedLink, setCopiedLink] = useState(false);

  // Add Schedule modal & draft slot state
  const [isAddScheduleOpen, setIsAddScheduleOpen] = useState(false);
  const [draftSlot, setDraftSlot] = useState(null);
  const [scheduleForm, setScheduleForm] = useState({
    title: "",
    date: "",
    startTime: "09:30",
    endTime: "10:00",
    guest: "",
    meetUrl: "https://meet.google.com/dcm-qwer-zxc",
    description: "",
    colorId: "skyblue",
  });
  const [savingSchedule, setSavingSchedule] = useState(false);

  const scrollRef = useRef(null);

  // Sync initial user timezone
  useEffect(() => {
    if (user?.timezone) {
      const now = getZonedNow();
      setCurrentDate(now);
      setMiniCalDate(now);
    }
  }, [user?.timezone, getZonedNow]);

  // Handle post-redirect query params (e.g. ?calendar_connected=1)
  useEffect(() => {
    if (searchParams.get("calendar_connected") === "1") {
      toast.success("Google Calendar connected successfully!");
      searchParams.delete("calendar_connected");
      setSearchParams(searchParams, { replace: true });
      fetchStatusAndEvents();
    }
  }, [searchParams]);

  // Keep now-line position updated every minute
  useEffect(() => {
    const update = () => {
      const now = getZonedNow();
      const mins = (now.getHours() - START_HOUR) * 60 + now.getMinutes();
      setNowMinute(mins);
    };
    update();
    const interval = setInterval(update, 60000);
    return () => clearInterval(interval);
  }, [user?.timezone, getZonedNow]);

  // Week days starting Sunday to match screenshot (SUN, MON, TUE...)
  const weekDays = useMemo(() => {
    const d = new Date(currentDate);
    const day = d.getDay(); // 0 is Sunday
    const sunday = new Date(d);
    sunday.setDate(d.getDate() - day);
    return Array.from({ length: 7 }, (_, i) => {
      const next = new Date(sunday);
      next.setDate(sunday.getDate() + i);
      return next;
    });
  }, [currentDate]);

  // Fetch real-time status & Google Calendar data
  const fetchStatusAndEvents = useCallback(async (showToast = false) => {
    try {
      let isConnected = false;
      let email = "";
      try {
        const statusRes = await api.get("/auth/google/calendar/status/");
        const statusData = statusRes.data || {};
        setCalendarStatus(statusData);
        isConnected = Boolean(statusData.is_connected);
        email = statusData.email || "";
      } catch (err) {
        console.warn("Could not fetch calendar status", err);
      }

      if (isConnected) {
        // Query broad window around current date: 45 days past to 90 days future
        const viewStart = new Date(currentDate);
        viewStart.setDate(viewStart.getDate() - 45);
        viewStart.setHours(0, 0, 0, 0);

        const viewEnd = new Date(currentDate);
        viewEnd.setDate(viewEnd.getDate() + 90);
        viewEnd.setHours(23, 59, 59, 999);

        const timeMin = viewStart.toISOString();
        const timeMax = viewEnd.toISOString();

        const calRes = await api.get("/auth/google/calendar/events/", {
          params: { time_min: timeMin, time_max: timeMax },
        });

        const rawEvents = calRes.data?.events || [];
        const mapped = rawEvents.map((evt, idx) => ({
          ...evt,
          colorId: pickEventColor(evt, idx),
        }));

        setEvents(mapped);
        setLastSyncedTime(new Date());
        if (showToast) {
          toast.success(`Google Calendar refreshed (${mapped.length} events loaded)`);
        }
      } else {
        setEvents([]);
      }
    } catch (err) {
      console.error("Failed to load real-time calendar events", err);
      if (showToast) {
        toast.error("Failed to sync with Google Calendar.");
      }
    } finally {
      setLoading(false);
      setIsSyncing(false);
    }
  }, [currentDate]);

  // Initial load & when date changes
  useEffect(() => {
    fetchStatusAndEvents();
  }, [fetchStatusAndEvents]);

  // Auto-refresh real-time Google Calendar data every 30 seconds
  useEffect(() => {
    if (!calendarStatus.is_connected) return;
    const interval = setInterval(() => {
      fetchStatusAndEvents(false);
    }, 30000);
    return () => clearInterval(interval);
  }, [calendarStatus.is_connected, fetchStatusAndEvents]);

  // Auto-scroll near 8 AM or current hour
  useEffect(() => {
    if (!loading && scrollRef.current && (viewMode === "week" || viewMode === "day")) {
      const now = getZonedNow();
      const scrollTo = Math.max(0, (now.getHours() - START_HOUR - 0.5) * HOUR_HEIGHT);
      scrollRef.current.scrollTop = scrollTo;
    }
  }, [loading, viewMode, getZonedNow]);

  const handleSync = async () => {
    setIsSyncing(true);
    await fetchStatusAndEvents(true);
  };

  const handleConnectCalendar = async () => {
    try {
      const res = await api.get("/auth/google/calendar/url/");
      const authUrl = res.data?.url || res.data?.authorization_url;
      if (authUrl) {
        localStorage.setItem("calendar_oauth_return_url", "/calendar");
        window.location.href = authUrl;
      } else {
        toast.error("Could not obtain Google Calendar authorization URL.");
      }
    } catch (e) {
      toast.error(e.response?.data?.error || "Could not initiate Google Calendar connection.");
    }
  };

  const handleDisconnectCalendar = async () => {
    if (!window.confirm("Are you sure you want to disconnect Google Calendar?")) return;
    try {
      await api.post("/auth/google/calendar/disconnect/");
      toast.info("Google Calendar disconnected.");
      setCalendarStatus({ is_connected: false, is_configured: true, email: "" });
      setEvents([]);
    } catch (err) {
      toast.error("Failed to disconnect Google Calendar.");
    }
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedLink(true);
      toast.success("Meet link copied to clipboard!");
      setTimeout(() => setCopiedLink(false), 2000);
    } catch {
      toast.error("Could not copy link.");
    }
  };

  // Period navigation
  const prevPeriod = () => {
    const d = new Date(currentDate);
    if (viewMode === "day") {
      d.setDate(d.getDate() - 1);
    } else if (viewMode === "month") {
      d.setMonth(d.getMonth() - 1);
    } else {
      d.setDate(d.getDate() - 7);
    }
    setCurrentDate(d);
    setMiniCalDate(d);
  };

  const nextPeriod = () => {
    const d = new Date(currentDate);
    if (viewMode === "day") {
      d.setDate(d.getDate() + 1);
    } else if (viewMode === "month") {
      d.setMonth(d.getMonth() + 1);
    } else {
      d.setDate(d.getDate() + 7);
    }
    setCurrentDate(d);
    setMiniCalDate(d);
  };

  const goToday = () => {
    const now = getZonedNow();
    setCurrentDate(now);
    setMiniCalDate(now);
  };

  const isSameDay = (d1, d2) => {
    if (!d1 || !d2) return false;
    const a = new Date(d1);
    const b = new Date(d2);
    return (
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  };

  const isToday = (d) => isSameDay(d, getZonedNow());

  // Formatting helpers matching screenshot
  const formatHeaderMonthYear = (date) => {
    return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  };

  const formatHourLabel = (h) => {
    if (h === 0) return "12 AM";
    if (h === 12) return "12 PM";
    return h > 12 ? `${h - 12} PM` : `${h} AM`;
  };

  // Convert time to "8.00am", "8.30am" lowercase dot format matching design
  const formatTimeSlotDisplay = (dateInput) => {
    if (!dateInput) return "";
    const d = getZonedDate(dateInput, user?.timezone);
    let h = d.getHours();
    const m = d.getMinutes();
    const ampm = h >= 12 ? "pm" : "am";
    if (h > 12) h -= 12;
    if (h === 0) h = 12;
    const mStr = m < 10 ? `0${m}` : m;
    return `${h}.${mStr}${ampm}`;
  };

  const formatEventTimeRange = (start, end) => {
    if (!start) return "";
    // If all-day event
    if (typeof start === "string" && /^\d{4}-\d{2}-\d{2}$/.test(start)) {
      return "All day";
    }
    const sStr = formatTimeSlotDisplay(start);
    if (!end) return sStr;
    const eStr = formatTimeSlotDisplay(end);
    return `${sStr} - ${eStr}`;
  };

  const hours = Array.from({ length: END_HOUR - START_HOUR }, (_, i) => START_HOUR + i);

  // Robust date matcher handling all-day (YYYY-MM-DD) and zoned timestamps
  const eventBelongsToDay = (evt, targetDay) => {
    if (!evt || !evt.start) return false;
    if (typeof evt.start === "string" && /^\d{4}-\d{2}-\d{2}$/.test(evt.start)) {
      const [y, m, d] = evt.start.split("-").map(Number);
      return (
        targetDay.getFullYear() === y &&
        targetDay.getMonth() === m - 1 &&
        targetDay.getDate() === d
      );
    }
    const eDate = getZonedDate(evt.start, user?.timezone);
    return isSameDay(eDate, targetDay);
  };

  // Filter events belonging to a day
  const getEventsForDay = (day) => {
    return events.filter((e) => eventBelongsToDay(e, day));
  };

  // Calculate pixel top & height for an event in the grid
  const getEventGeometry = (evt) => {
    // All-day event pinned at the very top of the day column
    if (typeof evt.start === "string" && /^\d{4}-\d{2}-\d{2}$/.test(evt.start)) {
      return { top: 2, height: 34, isAllDay: true };
    }

    const s = getZonedDate(evt.start, user?.timezone);
    const e = evt.end ? getZonedDate(evt.end, user?.timezone) : new Date(s.getTime() + 30 * 60000);

    const sHour = s.getHours() + s.getMinutes() / 60;
    let eHour = e.getHours() + e.getMinutes() / 60;

    // Handle events that end past midnight
    if (eHour <= sHour) {
      eHour = sHour + 0.5;
    }

    const top = Math.max(0, (sHour - START_HOUR) * HOUR_HEIGHT);
    const durationHours = Math.max(0.4, eHour - sHour);
    const height = Math.max(durationHours * HOUR_HEIGHT - 3, 34);

    return { top, height, isAllDay: false };
  };

  // Handle clicking empty slot to start draft and open "Add Schedule"
  const handleSlotClick = (day, hour, minute = 0) => {
    const startDt = new Date(day);
    startDt.setHours(hour, minute, 0, 0);

    const endDt = new Date(startDt.getTime() + 30 * 60000);

    const yyyy = startDt.getFullYear();
    const mm = String(startDt.getMonth() + 1).padStart(2, "0");
    const dd = String(startDt.getDate()).padStart(2, "0");
    const dateStr = `${yyyy}-${mm}-${dd}`;

    const pad = (n) => String(n).padStart(2, "0");
    const startTimeStr = `${pad(startDt.getHours())}:${pad(startDt.getMinutes())}`;
    const endTimeStr = `${pad(endDt.getHours())}:${pad(endDt.getMinutes())}`;

    const draft = {
      id: "draft_slot",
      day,
      start: startDt.toISOString(),
      end: endDt.toISOString(),
      summary: "(no title)",
      colorId: "skyblue",
    };

    setDraftSlot(draft);
    setScheduleForm({
      title: "",
      date: dateStr,
      startTime: startTimeStr,
      endTime: endTimeStr,
      guest: "",
      meetUrl: `https://meet.google.com/${Math.random().toString(36).substring(2, 5)}-${Math.random().toString(36).substring(2, 6)}-${Math.random().toString(36).substring(2, 5)}`,
      description: "",
      colorId: "skyblue",
    });
    setIsAddScheduleOpen(true);
  };

  const handleCloseAddSchedule = () => {
    setIsAddScheduleOpen(false);
    setDraftSlot(null);
  };

  // Save new schedule to Google Calendar in real-time
  const handleSaveSchedule = async (e) => {
    if (e) e.preventDefault();
    setSavingSchedule(true);
    try {
      const title = scheduleForm.title.trim() || "(no title)";
      const [sH, sM] = scheduleForm.startTime.split(":").map(Number);
      const [eH, eM] = scheduleForm.endTime.split(":").map(Number);

      const [year, month, day] = scheduleForm.date.split("-").map(Number);
      const startObj = new Date(year, month - 1, day, sH, sM, 0);
      const endObj = new Date(year, month - 1, day, eH, eM, 0);

      const newEvt = {
        id: `evt_${Date.now()}`,
        summary: title,
        description: scheduleForm.description,
        start: startObj.toISOString(),
        end: endObj.toISOString(),
        meet_url: scheduleForm.meetUrl,
        colorId: scheduleForm.colorId,
        attendees: scheduleForm.guest ? [{ email: scheduleForm.guest }] : [],
      };

      if (calendarStatus.is_connected) {
        try {
          const res = await api.post("/auth/google/calendar/events/", {
            summary: newEvt.summary,
            description: newEvt.description,
            start: newEvt.start,
            end: newEvt.end,
            meet_url: newEvt.meet_url,
            color_id: newEvt.colorId,
            attendees: scheduleForm.guest ? [scheduleForm.guest] : [],
          });
          if (res.data?.event?.id) {
            newEvt.id = res.data.event.id;
          }
        } catch (apiErr) {
          console.warn("Backend sync failed, saved locally", apiErr);
        }
      }

      setEvents((prev) => [newEvt, ...prev.filter((item) => item.id !== newEvt.id)]);
      toast.success("Schedule created successfully!");
      handleCloseAddSchedule();
      // Re-sync with Google Calendar
      setTimeout(() => fetchStatusAndEvents(false), 1000);
    } catch (err) {
      toast.error("Failed to create schedule.");
    } finally {
      setSavingSchedule(false);
    }
  };

  // Delete event in real-time
  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm("Delete this event from Google Calendar?")) return;
    try {
      if (calendarStatus.is_connected) {
        try {
          await api.delete("/auth/google/calendar/events/", {
            params: { event_id: eventId },
          });
        } catch (err) {
          console.warn("Delete API call failed, removing locally", err);
        }
      }
      setEvents((prev) => prev.filter((e) => e.id !== eventId));
      setSelectedEvent(null);
      toast.success("Event removed from calendar.");
    } catch {
      toast.error("Could not remove event.");
    }
  };

  // Mini Calendar grid generation (Monday start)
  const miniCalendarDays = useMemo(() => {
    const year = miniCalDate.getFullYear();
    const month = miniCalDate.getMonth();

    const firstDay = new Date(year, month, 1);
    let startDay = firstDay.getDay() - 1;
    if (startDay < 0) startDay = 6;

    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();

    const cells = [];

    // Leading days from previous month
    for (let i = startDay - 1; i >= 0; i--) {
      cells.push({
        date: new Date(year, month - 1, prevMonthDays - i),
        isCurrentMonth: false,
      });
    }

    // Days in current month
    for (let i = 1; i <= daysInMonth; i++) {
      cells.push({
        date: new Date(year, month, i),
        isCurrentMonth: true,
      });
    }

    // Trailing days from next month to make 35 or 42 cells
    const remaining = 42 - cells.length;
    for (let i = 1; i <= remaining; i++) {
      cells.push({
        date: new Date(year, month + 1, i),
        isCurrentMonth: false,
      });
    }

    return cells;
  }, [miniCalDate]);

  // Red time line position
  const isCurrentWeek = weekDays.some((d) => isToday(d));
  const nowLineTop =
    nowMinute > 0 && nowMinute < (END_HOUR - START_HOUR) * 60
      ? (nowMinute / 60) * HOUR_HEIGHT
      : null;

  return (
    <div className="flex h-full w-full bg-[#f8fafc] text-slate-800 font-sans overflow-hidden select-none">
      {/* ========================================================= */}
      {/* LEFT SIDEBAR (Matching uploaded design without marked items) */}
      {/* ========================================================= */}
      <aside className="w-64 sm:w-72 bg-white border-r border-slate-200/80 shrink-0 flex flex-col p-4 z-20">
        {/* Top Header Card: Calendar Workspace */}
        <div className="flex items-center justify-between p-2.5 rounded-2xl bg-white hover:bg-slate-50 transition cursor-pointer border border-transparent hover:border-slate-200/70">
          <div className="flex items-center gap-3">
            {/* Red calendar icon badge matching screenshot [ 17 ] */}
            <div className="w-9 h-9 rounded-xl bg-white border border-rose-200 shadow-xs flex flex-col overflow-hidden shrink-0">
              <div className="h-2.5 bg-rose-500 w-full" />
              <div className="flex-1 flex items-center justify-center font-bold text-slate-800 text-xs leading-none">
                {currentDate.getDate()}
              </div>
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900 leading-tight">
                MarketIntel Calendar
              </h2>
              <p className="text-[11px] text-slate-400 font-medium leading-none mt-0.5">
                Marketing's workspace
              </p>
            </div>
          </div>
          <ChevronsUpDown className="w-4 h-4 text-slate-400 shrink-0 ml-1" />
        </div>

        {/* Mini Calendar Date Picker */}
        <div className="mt-4 pt-3 border-t border-slate-100">
          {/* Mini Calendar Header with < Month Year > */}
          <div className="flex items-center justify-between mb-3 px-1">
            <button
              type="button"
              onClick={() => {
                const d = new Date(miniCalDate);
                d.setMonth(d.getMonth() - 1);
                setMiniCalDate(d);
              }}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition"
              title="Previous month"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-xs font-bold text-slate-800 tracking-tight">
              {miniCalDate.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
            </span>
            <button
              type="button"
              onClick={() => {
                const d = new Date(miniCalDate);
                d.setMonth(d.getMonth() + 1);
                setMiniCalDate(d);
              }}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition"
              title="Next month"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* Day of Week Row: Mo Tu We Th Fr Sa Su */}
          <div className="grid grid-cols-7 text-center mb-1">
            {["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((dName, idx) => (
              <span key={idx} className="text-[11px] font-semibold text-slate-400 py-1">
                {dName}
              </span>
            ))}
          </div>

          {/* Day Numbers Matrix */}
          <div className="grid grid-cols-7 gap-y-1 text-center">
            {miniCalendarDays.map((cell, idx) => {
              const isSelected = isSameDay(cell.date, currentDate);
              const isCellToday = isToday(cell.date);

              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    setCurrentDate(new Date(cell.date));
                    setMiniCalDate(new Date(cell.date));
                  }}
                  className={`w-7 h-7 mx-auto rounded-full flex items-center justify-center text-xs transition cursor-pointer ${
                    isSelected
                      ? "bg-slate-900 text-white font-bold shadow-xs"
                      : isCellToday
                      ? "text-rose-500 font-bold bg-rose-50"
                      : cell.isCurrentMonth
                      ? "text-slate-700 hover:bg-slate-100 font-medium"
                      : "text-slate-300 font-normal hover:bg-slate-50"
                  }`}
                >
                  {cell.date.getDate()}
                </button>
              );
            })}
          </div>
        </div>

        {/* Clean bottom area (without marked excluded items) */}
        <div className="mt-auto pt-4 border-t border-slate-100 space-y-2">
          {calendarStatus.is_connected ? (
            <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200/80 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-[11px] font-bold text-slate-800">Google Sync Active</span>
                </div>
                <button
                  type="button"
                  onClick={handleDisconnectCalendar}
                  title="Disconnect Google Calendar"
                  className="p-1 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-rose-50 transition"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="text-[10px] text-slate-500 truncate font-medium">
                {calendarStatus.email}
              </div>

              <div className="flex items-center justify-between pt-1 border-t border-slate-200/60 text-[10px] text-slate-400">
                <span>{events.length} event{events.length !== 1 ? "s" : ""} synced</span>
                <button
                  type="button"
                  onClick={handleSync}
                  disabled={isSyncing}
                  className="inline-flex items-center gap-1 font-bold text-slate-600 hover:text-slate-900 transition"
                >
                  <RefreshCw className={`w-3 h-3 ${isSyncing ? "animate-spin text-slate-800" : ""}`} />
                  <span>Sync Now</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-2xl space-y-2">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-bold text-amber-900">Google Calendar</h4>
                  <p className="text-[10px] text-amber-700 mt-0.5">
                    Connect your account to display live Google Calendar events.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleConnectCalendar}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-bold text-white bg-slate-900 hover:bg-black rounded-xl shadow-xs transition"
              >
                <Video className="w-3.5 h-3.5" />
                <span>Connect Google Account</span>
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* ========================================================= */}
      {/* MAIN CALENDAR AREA */}
      {/* ========================================================= */}
      <main className="flex-1 flex flex-col min-w-0 bg-white overflow-hidden relative">
        {/* Top Header Bar */}
        <header className="h-16 px-6 border-b border-slate-200/80 flex items-center justify-between shrink-0 bg-white">
          {/* Left: Month Year + Today + Chevron Navigation */}
          <div className="flex items-center gap-3">
            <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
              {formatHeaderMonthYear(currentDate)}
            </h1>

            <button
              type="button"
              onClick={goToday}
              className="px-3.5 py-1 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-full hover:bg-slate-50 transition shadow-xs"
            >
              Today
            </button>

            <div className="flex items-center gap-0.5 ml-1">
              <button
                type="button"
                onClick={prevPeriod}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                title="Previous"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={nextPeriod}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                title="Next"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Right: View Toggle Segment (Day | Week | Month) */}
          <div className="flex items-center gap-3">
            {/* Live refresh button */}
            <button
              type="button"
              onClick={handleSync}
              disabled={isSyncing}
              className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
              title="Refresh Google Calendar events in real time"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin text-slate-700" : ""}`} />
            </button>

            <div className="flex items-center bg-slate-100/90 p-1 rounded-xl text-xs font-medium border border-slate-200/60">
              <button
                type="button"
                onClick={() => setViewMode("day")}
                className={`px-3 py-1 rounded-lg transition ${
                  viewMode === "day"
                    ? "bg-white text-slate-900 font-semibold shadow-xs"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                Day
              </button>
              <button
                type="button"
                onClick={() => setViewMode("week")}
                className={`px-3 py-1 rounded-lg transition ${
                  viewMode === "week"
                    ? "bg-white text-slate-900 font-semibold shadow-xs"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                Week
              </button>
              <button
                type="button"
                onClick={() => setViewMode("month")}
                className={`px-3 py-1 rounded-lg transition ${
                  viewMode === "month"
                    ? "bg-white text-slate-900 font-semibold shadow-xs"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                Month
              </button>
            </div>
          </div>
        </header>

        {/* ========================================================= */}
        {/* VIEW BODY: WEEK VIEW */}
        {/* ========================================================= */}
        {viewMode === "week" && (
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-white">
            {/* Week Days Header Row: GMT+7 | SUN 9 | MON 10 | TUE 11 ... */}
            <div className="grid grid-cols-[68px_repeat(7,1fr)] border-b border-slate-200/90 shrink-0 bg-white">
              {/* Timezone label */}
              <div className="border-r border-slate-100 flex items-center justify-center p-2 text-[11px] font-semibold text-slate-400">
                GMT+7
              </div>

              {/* 7 Days Columns */}
              {weekDays.map((day, i) => {
                const today = isToday(day);
                const isSelected = isSameDay(day, currentDate);
                const dayName = day.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase();
                const dayNum = day.getDate();

                return (
                  <div
                    key={i}
                    onClick={() => setCurrentDate(new Date(day))}
                    className="py-3 px-2 border-r border-slate-100 text-center flex items-center justify-center gap-1.5 cursor-pointer hover:bg-slate-50/70 transition"
                  >
                    <span className="text-[11px] font-bold tracking-wider text-slate-700">
                      {dayName}
                    </span>
                    <span
                      className={`text-xs font-bold inline-flex items-center justify-center transition ${
                        today || isSelected
                          ? "w-6 h-6 rounded-full bg-slate-900 text-white shadow-xs"
                          : "text-slate-800"
                      }`}
                    >
                      {dayNum}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Scrollable Hours Grid */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto overflow-x-hidden relative bg-white">
              <div className="relative min-w-full">
                {/* Red Current Time Line across grid */}
                {isCurrentWeek && nowLineTop !== null && (
                  <div
                    className="absolute left-0 right-0 z-30 pointer-events-none flex items-center"
                    style={{ top: nowLineTop }}
                  >
                    {/* Time pill on left */}
                    <div className="w-[68px] flex justify-end pr-1.5">
                      <span className="px-1.5 py-0.5 rounded-full bg-rose-50 text-rose-500 border border-rose-200 text-[10px] font-bold leading-none shadow-xs">
                        {formatTimeSlotDisplay(getZonedNow())}
                      </span>
                    </div>
                    {/* Red dot */}
                    <div className="w-2.5 h-2.5 rounded-full bg-rose-400 ring-2 ring-white shrink-0 -ml-1.5 shadow-xs" />
                    {/* Red solid line through first col, then dashed line */}
                    <div className="flex-1 flex items-center">
                      <div className="w-[14%] h-[1.5px] bg-rose-400" />
                      <div className="flex-1 border-t border-dashed border-rose-300" />
                    </div>
                  </div>
                )}

                {/* Grid Background Hourly Rows */}
                {hours.map((hour) => (
                  <div
                    key={hour}
                    className="grid grid-cols-[68px_repeat(7,1fr)] border-b border-slate-100"
                    style={{ height: HOUR_HEIGHT }}
                  >
                    {/* Time Label on left */}
                    <div className="border-r border-slate-100 flex items-start justify-end pr-2.5 pt-1">
                      <span className="text-[11px] font-semibold text-slate-400">
                        {formatHourLabel(hour)}
                      </span>
                    </div>

                    {/* 7 Interactive Day Slots */}
                    {weekDays.map((day, dIdx) => (
                      <div
                        key={dIdx}
                        onClick={() => handleSlotClick(day, hour, 0)}
                        className="border-r border-slate-100 relative group cursor-pointer transition hover:bg-slate-50/50"
                      />
                    ))}
                  </div>
                ))}

                {/* Absolute Events Layer over the 7 columns */}
                <div className="absolute inset-0 pointer-events-none grid grid-cols-[68px_repeat(7,1fr)]">
                  <div /> {/* Skip time column */}
                  {weekDays.map((day, dIdx) => {
                    const dayEvents = getEventsForDay(day);
                    const isDraftDay = draftSlot && isSameDay(draftSlot.day, day);

                    return (
                      <div key={dIdx} className="relative h-full border-r border-transparent">
                        {/* Render real Google Calendar events */}
                        {dayEvents.map((evt) => {
                          const { top, height } = getEventGeometry(evt);
                          const color = getColorConfig(evt.colorId);

                          return (
                            <div
                              key={evt.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedEvent(evt);
                              }}
                              style={{
                                top: `${top}px`,
                                height: `${height}px`,
                                backgroundColor: color.bg,
                                color: color.text,
                                borderColor: color.border,
                              }}
                              className="absolute left-1 right-1 rounded-2xl px-2.5 py-1 border shadow-xs transition-all pointer-events-auto cursor-pointer hover:shadow-md hover:scale-[1.01] overflow-hidden flex flex-col justify-center z-10"
                            >
                              <div className="flex items-center justify-between gap-1 min-w-0">
                                <span className="font-bold text-xs leading-tight truncate">
                                  {evt.summary || "(No Title)"}
                                </span>
                                {evt.meet_url && (
                                  <Video className="w-3 h-3 shrink-0 opacity-80" />
                                )}
                              </div>
                              <div
                                style={{ color: color.timeText }}
                                className="text-[10px] font-medium leading-tight mt-0.5 truncate"
                              >
                                {formatEventTimeRange(evt.start, evt.end)}
                              </div>
                            </div>
                          );
                        })}

                        {/* Render Active Draft Slot */}
                        {isDraftDay && draftSlot && (
                          <div
                            style={{
                              ...getEventGeometry(draftSlot),
                            }}
                            className="absolute left-1 right-1 rounded-2xl px-2.5 py-1 border-2 border-sky-400 bg-sky-50/80 text-sky-900 shadow-sm pointer-events-auto flex flex-col justify-center z-20 transition"
                          >
                            <div className="font-bold text-xs leading-tight truncate">
                              {scheduleForm.title || "(no title)"}
                            </div>
                            <div className="text-[10px] font-medium text-sky-700/90 leading-tight mt-0.5 truncate">
                              {formatEventTimeRange(draftSlot.start, draftSlot.end)}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* VIEW BODY: DAY VIEW */}
        {/* ========================================================= */}
        {viewMode === "day" && (
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-white">
            <div className="grid grid-cols-[68px_1fr] border-b border-slate-200/90 shrink-0 bg-white">
              <div className="border-r border-slate-100 flex items-center justify-center p-2 text-[11px] font-semibold text-slate-400">
                GMT+7
              </div>
              <div className="py-3 px-4 text-left flex items-center gap-2">
                <span className="text-xs font-bold tracking-wider text-slate-700">
                  {currentDate.toLocaleDateString("en-US", { weekday: "long" }).toUpperCase()}
                </span>
                <span className="w-6 h-6 rounded-full bg-slate-900 text-white font-bold text-xs flex items-center justify-center">
                  {currentDate.getDate()}
                </span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto relative bg-white">
              <div className="relative min-w-full">
                {hours.map((hour) => (
                  <div
                    key={hour}
                    className="grid grid-cols-[68px_1fr] border-b border-slate-100"
                    style={{ height: HOUR_HEIGHT }}
                  >
                    <div className="border-r border-slate-100 flex items-start justify-end pr-2.5 pt-1">
                      <span className="text-[11px] font-semibold text-slate-400">
                        {formatHourLabel(hour)}
                      </span>
                    </div>
                    <div
                      onClick={() => handleSlotClick(currentDate, hour, 0)}
                      className="relative hover:bg-slate-50/50 cursor-pointer transition"
                    />
                  </div>
                ))}

                <div className="absolute inset-0 pointer-events-none grid grid-cols-[68px_1fr]">
                  <div />
                  <div className="relative h-full">
                    {getEventsForDay(currentDate).map((evt) => {
                      const { top, height } = getEventGeometry(evt);
                      const color = getColorConfig(evt.colorId);

                      return (
                        <div
                          key={evt.id}
                          onClick={() => setSelectedEvent(evt)}
                          style={{
                            top: `${top}px`,
                            height: `${height}px`,
                            backgroundColor: color.bg,
                            color: color.text,
                            borderColor: color.border,
                          }}
                          className="absolute left-2 right-4 rounded-2xl p-3 border shadow-xs transition-all pointer-events-auto cursor-pointer hover:shadow-md flex flex-col justify-start z-10"
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-sm leading-tight truncate">
                              {evt.summary || "(No Title)"}
                            </span>
                            {evt.meet_url && <Video className="w-3.5 h-3.5 shrink-0 opacity-80" />}
                          </div>
                          <div style={{ color: color.timeText }} className="text-xs font-medium mt-1">
                            {formatEventTimeRange(evt.start, evt.end)}
                          </div>
                          {evt.description && (
                            <div className="text-[11px] opacity-80 mt-1 line-clamp-2">
                              {evt.description}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* VIEW BODY: MONTH VIEW */}
        {/* ========================================================= */}
        {viewMode === "month" && (
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-white">
            <div className="grid grid-cols-7 border-b border-slate-200/90 shrink-0 bg-white text-center">
              {["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"].map((dName, idx) => (
                <div key={idx} className="py-2.5 text-xs font-bold text-slate-500 border-r border-slate-100 last:border-r-0">
                  {dName}
                </div>
              ))}
            </div>

            <div className="flex-1 grid grid-cols-7 grid-rows-5 overflow-y-auto bg-slate-50 gap-px border-b border-slate-200">
              {miniCalendarDays.slice(0, 35).map((cell, idx) => {
                const dayEvents = getEventsForDay(cell.date);
                const isSelected = isSameDay(cell.date, currentDate);
                const isCellToday = isToday(cell.date);

                return (
                  <div
                    key={idx}
                    onClick={() => {
                      setCurrentDate(cell.date);
                      handleSlotClick(cell.date, 9, 30);
                    }}
                    className={`bg-white p-2 min-h-[90px] flex flex-col justify-between cursor-pointer hover:bg-slate-50/80 transition relative ${
                      !cell.isCurrentMonth ? "opacity-40" : ""
                    }`}
                  >
                    <div className="flex justify-between items-center mb-1">
                      <span
                        className={`text-xs font-bold w-6 h-6 flex items-center justify-center rounded-full ${
                          isSelected
                            ? "bg-slate-900 text-white"
                            : isCellToday
                            ? "bg-rose-500 text-white"
                            : "text-slate-700"
                        }`}
                      >
                        {cell.date.getDate()}
                      </span>
                      {dayEvents.length > 0 && (
                        <span className="text-[10px] font-semibold text-slate-400">
                          {dayEvents.length}
                        </span>
                      )}
                    </div>

                    <div className="space-y-1 overflow-hidden flex-1">
                      {dayEvents.slice(0, 3).map((evt) => {
                        const color = getColorConfig(evt.colorId);
                        return (
                          <div
                            key={evt.id}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedEvent(evt);
                            }}
                            style={{ backgroundColor: color.bg, color: color.text }}
                            className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md truncate shadow-2xs cursor-pointer"
                          >
                            {evt.summary || "(No Title)"}
                          </div>
                        );
                      })}
                      {dayEvents.length > 3 && (
                        <div className="text-[9px] text-slate-400 font-bold px-1">
                          +{dayEvents.length - 3} more
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* "ADD SCHEDULE" FLOATING MODAL */}
        {/* ========================================================= */}
        {isAddScheduleOpen && (
          <div className="fixed sm:absolute bottom-6 right-6 z-50 w-[350px] bg-white rounded-3xl shadow-2xl border border-slate-200/90 p-5 space-y-3.5 animate-in fade-in slide-in-from-bottom-3 duration-200">
            {/* Header: Add Schedule + Close */}
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900">Add Schedule</h3>
              <button
                type="button"
                onClick={handleCloseAddSchedule}
                className="text-slate-400 hover:text-slate-700 p-1 rounded-lg hover:bg-slate-100 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Input: New event title */}
            <div>
              <input
                type="text"
                autoFocus
                placeholder="New event title"
                value={scheduleForm.title}
                onChange={(e) => setScheduleForm({ ...scheduleForm, title: e.target.value })}
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent transition"
              />
            </div>

            {/* Row: Date with Calendar Icon */}
            <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl border border-slate-200 text-xs font-medium text-slate-700">
              <CalendarIcon className="w-4 h-4 text-slate-400 shrink-0" />
              <input
                type="date"
                value={scheduleForm.date}
                onChange={(e) => setScheduleForm({ ...scheduleForm, date: e.target.value })}
                className="flex-1 bg-transparent border-0 text-xs font-semibold text-slate-700 focus:outline-none cursor-pointer"
              />
            </div>

            {/* Row: Time Range with Clock Icon & Arrow */}
            <div className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-xs font-medium text-slate-700">
              <Clock className="w-4 h-4 text-slate-400 shrink-0" />
              <input
                type="time"
                value={scheduleForm.startTime}
                onChange={(e) => setScheduleForm({ ...scheduleForm, startTime: e.target.value })}
                className="bg-transparent border-0 text-xs font-semibold text-slate-700 focus:outline-none cursor-pointer w-20"
              />
              <ArrowRight className="w-3.5 h-3.5 text-slate-400 shrink-0 mx-auto" />
              <input
                type="time"
                value={scheduleForm.endTime}
                onChange={(e) => setScheduleForm({ ...scheduleForm, endTime: e.target.value })}
                className="bg-transparent border-0 text-xs font-semibold text-slate-700 focus:outline-none cursor-pointer w-20 text-right"
              />
            </div>

            {/* Row: Add guest */}
            <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl border border-slate-200 text-xs font-medium text-slate-700">
              <Users className="w-4 h-4 text-slate-400 shrink-0" />
              <input
                type="email"
                placeholder="Add guest"
                value={scheduleForm.guest}
                onChange={(e) => setScheduleForm({ ...scheduleForm, guest: e.target.value })}
                className="flex-1 bg-transparent border-0 text-xs text-slate-700 placeholder-slate-400 focus:outline-none"
              />
            </div>

            {/* Row: Meeting link */}
            <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl border border-slate-200 text-xs font-medium">
              <Link2 className="w-4 h-4 text-slate-400 shrink-0" />
              <input
                type="text"
                value={scheduleForm.meetUrl}
                onChange={(e) => setScheduleForm({ ...scheduleForm, meetUrl: e.target.value })}
                className="flex-1 bg-transparent border-0 text-xs text-sky-600 font-medium focus:outline-none truncate"
                placeholder="https://meet.google.com/..."
              />
            </div>

            {/* Row: Add description */}
            <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl border border-slate-200 text-xs font-medium text-slate-700">
              <AlignLeft className="w-4 h-4 text-slate-400 shrink-0" />
              <input
                type="text"
                placeholder="Add description"
                value={scheduleForm.description}
                onChange={(e) => setScheduleForm({ ...scheduleForm, description: e.target.value })}
                className="flex-1 bg-transparent border-0 text-xs text-slate-700 placeholder-slate-400 focus:outline-none"
              />
            </div>

            {/* Row: Pastel Color Circles Palette */}
            <div className="flex items-center gap-2.5 pt-1">
              {COLOR_OPTIONS.map((c) => {
                const isSelected = scheduleForm.colorId === c.id;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setScheduleForm({ ...scheduleForm, colorId: c.id })}
                    style={{ backgroundColor: c.bg, borderColor: c.border }}
                    className={`w-6 h-6 rounded-full border transition cursor-pointer ${
                      isSelected ? "ring-2 ring-sky-500 ring-offset-2 scale-110" : "hover:scale-105"
                    }`}
                    title={c.name}
                  />
                );
              })}
            </div>

            {/* Action Buttons: Cancel and Save */}
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={handleCloseAddSchedule}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 rounded-xl hover:bg-slate-100 transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveSchedule}
                disabled={savingSchedule}
                className="px-5 py-2 text-xs font-bold text-white bg-slate-900 hover:bg-black rounded-xl shadow-xs transition disabled:opacity-50 cursor-pointer"
              >
                {savingSchedule ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        )}

        {/* ========================================================= */}
        {/* EVENT DETAILS MODAL */}
        {/* ========================================================= */}
        {selectedEvent && (
          <div
            className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
            onClick={() => setSelectedEvent(null)}
          >
            <div
              className="bg-white rounded-3xl shadow-2xl max-w-md w-full overflow-hidden border border-slate-200 space-y-0"
              onClick={(e) => e.stopPropagation()}
            >
              <div
                style={{
                  backgroundColor: getColorConfig(selectedEvent.colorId).bg,
                  color: getColorConfig(selectedEvent.colorId).text,
                }}
                className="p-5 flex items-start justify-between border-b border-slate-100"
              >
                <div>
                  <h3 className="text-base font-bold tracking-tight">
                    {selectedEvent.summary || "(No Title)"}
                  </h3>
                  <p className="text-xs font-semibold opacity-80 mt-0.5">
                    {formatEventTimeRange(selectedEvent.start, selectedEvent.end)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedEvent(null)}
                  className="p-1 rounded-lg opacity-70 hover:opacity-100 hover:bg-black/5 transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-5 space-y-4 text-xs text-slate-700">
                {/* Timing */}
                <div className="flex items-center gap-2 text-slate-600">
                  <Clock className="w-4 h-4 text-slate-400 shrink-0" />
                  <span>{formatDateTimeForUser(selectedEvent.start, user?.timezone)}</span>
                </div>

                {/* Google Meet Link */}
                {selectedEvent.meet_url && (
                  <div className="p-3 bg-slate-50 rounded-2xl border border-slate-200 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-800 flex items-center gap-1.5 text-xs">
                        <Video className="w-3.5 h-3.5 text-sky-600" /> Google Meet Video Call
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <a
                        href={selectedEvent.meet_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl transition"
                      >
                        <Video className="w-3 h-3" />
                        <span>Join Meeting</span>
                      </a>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(selectedEvent.meet_url)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 font-semibold text-xs rounded-xl hover:bg-slate-50 transition"
                      >
                        {copiedLink ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                        <span>{copiedLink ? "Copied" : "Copy"}</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* Description */}
                {selectedEvent.description && (
                  <div>
                    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                      Description
                    </label>
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-slate-700 leading-relaxed">
                      {selectedEvent.description}
                    </div>
                  </div>
                )}

                {/* Attendees */}
                {selectedEvent.attendees?.length > 0 && (
                  <div>
                    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1">
                      Guests ({selectedEvent.attendees.length})
                    </label>
                    <div className="space-y-1">
                      {selectedEvent.attendees.map((att, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-xs text-slate-700 font-medium">
                          <Users className="w-3 h-3 text-slate-400" />
                          <span>{att.email || att.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Open in Google Calendar external link */}
                {selectedEvent.html_link && (
                  <div>
                    <a
                      href={selectedEvent.html_link}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs font-bold text-sky-600 hover:text-sky-800 transition"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      <span>View in Google Calendar</span>
                    </a>
                  </div>
                )}
              </div>

              <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => handleDeleteEvent(selectedEvent.id)}
                  className="inline-flex items-center gap-1.5 text-rose-600 hover:text-rose-700 text-xs font-bold"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Delete Event</span>
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedEvent(null)}
                  className="px-4 py-2 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 font-bold text-xs rounded-xl shadow-xs transition"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
