import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
  Clock,
  ExternalLink,
  Video,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Users,
  MapPin,
  X,
  Copy,
  Check,
  LogOut,
  CalendarDays,
  List,
} from "lucide-react";
import { useSelector } from "react-redux";
import { useSearchParams } from "react-router-dom";
import { toast } from "react-toastify";
import api from "../services/api";
import { getZonedDate, formatTimeForUser, formatDateTimeForUser } from "../utils/timezone";

const HOUR_HEIGHT = 80;
const START_HOUR = 7;
const END_HOUR = 23;

export default function LqCalendarPage() {
  const { user } = useSelector((state) => state.auth);
  const [searchParams, setSearchParams] = useSearchParams();

  const getZonedNow = () => getZonedDate(null, user?.timezone);
  const [currentDate, setCurrentDate] = useState(() => getZonedDate(null, null));
  const [loading, setLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState({ is_connected: false, is_configured: false, email: "" });
  const [events, setEvents] = useState([]);
  const [localMeetings, setLocalMeetings] = useState([]);
  const [nowMinute, setNowMinute] = useState(0);
  const [viewMode, setViewMode] = useState("grid"); // 'grid' | 'agenda'
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const scrollRef = useRef(null);

  // Sync initial user timezone
  useEffect(() => {
    if (user?.timezone) {
      setCurrentDate(getZonedNow());
    }
  }, [user?.timezone]);

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
  }, [user?.timezone]);

  // Initial load & when week changes
  useEffect(() => {
    fetchStatusAndEvents();
  }, [currentDate]);

  // Auto-scroll to near current hour
  useEffect(() => {
    if (!loading && scrollRef.current && viewMode === "grid") {
      const now = getZonedNow();
      const scrollTo = Math.max(0, now.getHours() - START_HOUR - 1) * HOUR_HEIGHT;
      scrollRef.current.scrollTop = scrollTo;
    }
  }, [loading, viewMode]);

  const weekDays = useMemo(() => {
    const d = new Date(currentDate);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1); // Monday start
    const monday = new Date(d.setDate(diff));
    return Array.from({ length: 7 }, (_, i) => {
      const next = new Date(monday);
      next.setDate(monday.getDate() + i);
      return next;
    });
  }, [currentDate]);

  const fetchStatusAndEvents = async () => {
    setLoading(true);
    try {
      // 1. Fetch Calendar status
      let isConnected = false;
      try {
        const statusRes = await api.get("/auth/google/calendar/status/");
        setCalendarStatus(statusRes.data || {});
        isConnected = Boolean(statusRes.data?.is_connected);
      } catch (err) {
        console.warn("Could not fetch calendar status", err);
      }

      // 2. Fetch local meetings for lead association
      let meetingsMap = {};
      try {
        const meetingsRes = await api.get("/meetings/");
        const mList = meetingsRes.data?.results || meetingsRes.data || [];
        setLocalMeetings(mList);
        mList.forEach((m) => {
          if (m.google_event_id) {
            meetingsMap[m.google_event_id] = m;
          }
        });
      } catch (err) {
        console.warn("Could not fetch local meetings", err);
      }

      // 3. Fetch Google Calendar events if connected
      if (isConnected) {
        const startOfWeek = new Date(weekDays[0]);
        startOfWeek.setHours(0, 0, 0, 0);
        const endOfWeek = new Date(weekDays[6]);
        endOfWeek.setHours(23, 59, 59, 999);

        // Fetch a bit wider to cover timezone edges and agenda views (+14 days)
        const timeMin = new Date(startOfWeek.getTime() - 24 * 3600 * 1000).toISOString();
        const timeMax = new Date(endOfWeek.getTime() + 14 * 24 * 3600 * 1000).toISOString();

        const calRes = await api.get("/auth/google/calendar/events/", {
          params: { time_min: timeMin, time_max: timeMax },
        });

        const rawEvents = calRes.data?.events || [];
        const enriched = rawEvents.map((evt) => {
          const matchedMeeting = meetingsMap[evt.id];
          return {
            ...evt,
            prospect_name: matchedMeeting?.company_name || null,
            key_person_name: matchedMeeting?.key_person_name || null,
            prospect_id: matchedMeeting?.prospect || null,
          };
        });
        setEvents(enriched);
      } else {
        setEvents([]);
      }
    } catch (err) {
      console.error("Failed to load Google Calendar events", err);
    } finally {
      setLoading(false);
      setIsSyncing(false);
    }
  };

  const handleSync = async () => {
    setIsSyncing(true);
    await fetchStatusAndEvents();
    toast.success("Google Calendar refreshed!");
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

  const hours = Array.from({ length: END_HOUR - START_HOUR }, (_, i) => START_HOUR + i);

  const prevWeek = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() - 7);
    setCurrentDate(d);
  };

  const nextWeek = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() + 7);
    setCurrentDate(d);
  };

  const goToday = () => {
    setCurrentDate(getZonedNow());
    setTimeout(() => {
      if (scrollRef.current && viewMode === "grid") {
        const now = getZonedNow();
        const scrollTo = Math.max(0, now.getHours() - START_HOUR - 1) * HOUR_HEIGHT;
        scrollRef.current.scrollTop = scrollTo;
      }
    }, 50);
  };

  const isSameDay = (d1, d2) =>
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate();

  const isToday = (d) => isSameDay(d, getZonedNow());

  const getEventsForSlot = (day, hour) => {
    return events.filter((e) => {
      if (!e.start) return false;
      const eDate = getZonedDate(e.start, user?.timezone);
      return isSameDay(eDate, day) && eDate.getHours() === hour;
    });
  };

  const isCurrentWeek = weekDays.some((d) => isToday(d));
  const nowLineTop =
    nowMinute > 0 && nowMinute < (END_HOUR - START_HOUR) * 60
      ? (nowMinute / 60) * HOUR_HEIGHT
      : null;

  const formatHour = (h) => {
    if (h === 0) return "12 AM";
    if (h === 12) return "12 PM";
    return h > 12 ? `${h - 12} PM` : `${h} AM`;
  };

  return (
    <div className="flex flex-col h-full bg-slate-50 overflow-hidden">
      {/* Top Header Bar */}
      <div className="bg-white border-b border-slate-200/90 px-6 py-4 flex flex-wrap items-center justify-between gap-4 shrink-0 shadow-sm">
        {/* Left: Branding & Status */}
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white flex items-center justify-center shadow-md shadow-indigo-200">
            <CalendarIcon className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-black text-slate-900 tracking-tight">
                Google Calendar
              </h1>
              {calendarStatus.is_connected ? (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  Live Sync
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                  Not Connected
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 font-medium">
              {calendarStatus.is_connected ? (
                <>Connected as <strong className="text-slate-700 font-bold">{calendarStatus.email}</strong> • {events.length} event{events.length !== 1 ? "s" : ""}</>
              ) : (
                "Connect your Google Calendar to sync meetings and Google Meet video calls"
              )}
            </p>
          </div>
        </div>

        {/* Right: Actions & Navigation */}
        <div className="flex flex-wrap items-center gap-3">
          {/* View Toggle */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-bold">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition ${
                viewMode === "grid"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <CalendarDays className="w-3.5 h-3.5" />
              <span>Week</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("agenda")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition ${
                viewMode === "agenda"
                  ? "bg-white text-indigo-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <List className="w-3.5 h-3.5" />
              <span>Agenda</span>
            </button>
          </div>

          {/* Week Navigation */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={goToday}
              className="px-3 py-1.5 text-xs font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 rounded-xl transition cursor-pointer"
            >
              Today
            </button>
            <div className="flex items-center bg-slate-100 rounded-xl p-0.5 border border-slate-200">
              <button
                type="button"
                onClick={prevWeek}
                title="Previous Week"
                className="p-1.5 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-white transition cursor-pointer"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-xs font-bold text-slate-800 px-3 min-w-[130px] text-center">
                {weekDays[0].toLocaleDateString("default", { month: "short", day: "numeric" })} –{" "}
                {weekDays[6].toLocaleDateString("default", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
              <button
                type="button"
                onClick={nextWeek}
                title="Next Week"
                className="p-1.5 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-white transition cursor-pointer"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Sync & External Links */}
          {calendarStatus.is_connected ? (
            <>
              <button
                type="button"
                onClick={handleSync}
                disabled={isSyncing || loading}
                title="Sync with Google Calendar"
                className="p-2 text-slate-600 bg-white border border-slate-200 hover:border-indigo-300 hover:text-indigo-600 rounded-xl shadow-sm transition disabled:opacity-50 cursor-pointer"
              >
                <RefreshCw className={`w-4 h-4 ${isSyncing ? "animate-spin text-indigo-600" : ""}`} />
              </button>
              <a
                href="https://calendar.google.com/"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 hover:border-slate-300 rounded-xl shadow-sm transition"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open Google Calendar</span>
              </a>
              <button
                type="button"
                onClick={handleDisconnectCalendar}
                title="Disconnect Google Calendar"
                className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition cursor-pointer"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={handleConnectCalendar}
              className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-700 hover:to-indigo-800 text-white font-black text-xs rounded-xl shadow-md shadow-indigo-200 transition cursor-pointer"
            >
              <Video className="w-4 h-4" />
              <span>Connect Google Calendar</span>
            </button>
          )}
        </div>
      </div>

      {/* Disconnected Notice Banner */}
      {!calendarStatus.is_connected && !loading && (
        <div className="bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-indigo-500/10 border-b border-indigo-100 px-6 py-4">
          <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-center sm:text-left">
              <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                <Video className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-black text-slate-900">
                  Connect Google Calendar to Enable Google Meet Scheduling
                </h4>
                <p className="text-xs text-slate-600">
                  Sync all customer meetings, invite leads with 1-click, and generate real Google Meet links.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleConnectCalendar}
              className="shrink-0 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-black text-xs rounded-xl shadow transition cursor-pointer"
            >
              Connect Google Calendar Now
            </button>
          </div>
        </div>
      )}

      {/* View Content */}
      {viewMode === "grid" ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Day Headers */}
          <div className="bg-white border-b border-slate-200 shrink-0">
            <div className="grid grid-cols-[72px_repeat(7,1fr)] min-w-full">
              <div className="border-r border-slate-100 flex items-center justify-center p-2 text-[10px] font-extrabold text-slate-400">
                {user?.timezone || "UTC"}
              </div>
              {weekDays.map((day, i) => {
                const today = isToday(day);
                return (
                  <div
                    key={i}
                    className={`py-3 px-2 border-r border-slate-100 text-center transition ${
                      today ? "bg-indigo-50/60" : "bg-transparent"
                    }`}
                  >
                    <div
                      className={`text-[10px] font-extrabold uppercase tracking-wider mb-1 ${
                        today ? "text-indigo-600 font-black" : "text-slate-400"
                      }`}
                    >
                      {day.toLocaleDateString("default", { weekday: "short" })}
                    </div>
                    <div
                      className={`w-9 h-9 mx-auto flex items-center justify-center rounded-xl text-base font-black transition ${
                        today
                          ? "bg-indigo-600 text-white shadow-md shadow-indigo-300"
                          : "text-slate-800"
                      }`}
                    >
                      {day.getDate()}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Scrollable Time Grid */}
          <div ref={scrollRef} className="flex-1 overflow-auto bg-white">
            <div className="relative min-w-full">
              {/* Current Time Indicator Line */}
              {isCurrentWeek && nowLineTop !== null && (
                <div
                  className="absolute left-0 right-0 z-20 flex items-center pointer-events-none"
                  style={{ top: nowLineTop }}
                >
                  <div className="w-[72px] flex justify-end pr-2">
                    <div className="w-2.5 h-2.5 rounded-full bg-rose-500 shadow-md shadow-rose-300 ring-2 ring-white" />
                  </div>
                  <div className="flex-1 h-0.5 bg-rose-500/80" />
                </div>
              )}

              {/* Hourly Slots */}
              {hours.map((hour) => (
                <div
                  key={hour}
                  className="grid grid-cols-[72px_repeat(7,1fr)] border-b border-slate-100"
                  style={{ minHeight: HOUR_HEIGHT }}
                >
                  {/* Time label */}
                  <div className="border-r border-slate-100 flex items-start justify-end p-2 bg-slate-50/50">
                    <span className="text-[11px] font-extrabold text-slate-400">
                      {formatHour(hour)}
                    </span>
                  </div>

                  {/* 7 Day Columns */}
                  {weekDays.map((day) => {
                    const slotEvents = getEventsForSlot(day, hour);
                    const today = isToday(day);
                    return (
                      <div
                        key={`${day.getTime()}-${hour}`}
                        className={`border-r border-slate-100 p-1.5 transition ${
                          today ? "bg-indigo-50/20" : "bg-transparent"
                        }`}
                      >
                        {slotEvents.map((evt) => {
                          const hasMeet = Boolean(evt.meet_url);
                          return (
                            <div
                              key={evt.id}
                              onClick={() => setSelectedEvent(evt)}
                              className={`group relative rounded-xl p-2.5 mb-1.5 text-white transition-all cursor-pointer shadow-sm hover:shadow-md hover:-translate-y-0.5 ${
                                hasMeet
                                  ? "bg-gradient-to-br from-indigo-600 to-indigo-700 border border-indigo-500/40"
                                  : "bg-gradient-to-br from-slate-700 to-slate-800 border border-slate-600/40"
                              }`}
                            >
                              <div className="flex items-start justify-between gap-1">
                                <div className="font-extrabold text-xs truncate leading-tight">
                                  {evt.summary}
                                </div>
                                {hasMeet && (
                                  <span className="shrink-0 inline-flex items-center p-0.5 rounded bg-white/20 text-white" title="Google Meet Video Call">
                                    <Video className="w-3 h-3" />
                                  </span>
                                )}
                              </div>

                              {evt.prospect_name && evt.prospect_name !== evt.summary && (
                                <div className="text-[10px] text-indigo-200 font-bold truncate mt-0.5">
                                  {evt.prospect_name}
                                </div>
                              )}

                              <div className="flex items-center gap-1.5 text-[10px] text-indigo-100 font-medium mt-1.5">
                                <Clock className="w-3 h-3 text-indigo-200 shrink-0" />
                                <span>{formatTimeForUser(evt.start, user?.timezone)}</span>
                              </div>

                              {hasMeet && (
                                <div className="mt-2 pt-1.5 border-t border-white/15 flex items-center justify-between gap-1">
                                  <a
                                    href={evt.meet_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    onClick={(e) => e.stopPropagation()}
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white/20 hover:bg-white text-white hover:text-indigo-700 text-[10px] font-black transition"
                                  >
                                    <Video className="w-2.5 h-2.5" />
                                    <span>Join Meet</span>
                                  </a>
                                  {evt.attendees?.length > 0 && (
                                    <span className="text-[10px] text-indigo-200 font-bold flex items-center gap-0.5">
                                      <Users className="w-2.5 h-2.5" />
                                      {evt.attendees.length}
                                    </span>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Agenda List View */
        <div className="flex-1 overflow-auto p-6 max-w-4xl mx-auto w-full space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-200">
            <h3 className="text-sm font-black text-slate-800 uppercase tracking-wider">
              Upcoming Google Calendar Meetings ({events.length})
            </h3>
            <span className="text-xs font-semibold text-slate-500">
              Times displayed in {user?.timezone || "UTC"}
            </span>
          </div>

          {events.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-3xl border border-slate-200/80 p-8 space-y-3">
              <div className="w-12 h-12 mx-auto rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <CalendarIcon className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-black text-slate-900">No scheduled meetings found</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                {calendarStatus.is_connected
                  ? "Your Google Calendar is connected, but there are no upcoming events in this period."
                  : "Connect your Google Calendar to populate your schedule."}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {events.map((evt) => {
                const hasMeet = Boolean(evt.meet_url);
                return (
                  <div
                    key={evt.id}
                    onClick={() => setSelectedEvent(evt)}
                    className="p-4 bg-white border border-slate-200/90 rounded-2xl hover:border-indigo-300 hover:shadow-md transition cursor-pointer flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
                  >
                    <div className="flex items-start gap-3.5">
                      <div
                        className={`w-10 h-10 rounded-xl flex items-center justify-center text-white shrink-0 ${
                          hasMeet ? "bg-indigo-600 shadow-sm" : "bg-slate-700"
                        }`}
                      >
                        {hasMeet ? <Video className="w-5 h-5" /> : <CalendarIcon className="w-5 h-5" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-black text-slate-900">{evt.summary}</h4>
                          {hasMeet && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-extrabold bg-indigo-50 text-indigo-700 border border-indigo-200">
                              Google Meet
                            </span>
                          )}
                        </div>
                        {evt.prospect_name && (
                          <div className="text-xs font-bold text-slate-600 mt-0.5">
                            Lead: {evt.prospect_name}
                          </div>
                        )}
                        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 font-medium mt-1">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5 text-slate-400" />
                            {formatDateTimeForUser(evt.start, user?.timezone)}
                          </span>
                          {evt.attendees?.length > 0 && (
                            <span className="flex items-center gap-1">
                              <Users className="w-3.5 h-3.5 text-slate-400" />
                              {evt.attendees.length} attendee{evt.attendees.length !== 1 ? "s" : ""}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-center">
                      {hasMeet && (
                        <a
                          href={evt.meet_url}
                          target="_blank"
                          rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-extrabold shadow-sm transition"
                        >
                          <Video className="w-3.5 h-3.5" />
                          <span>Join Meet</span>
                        </a>
                      )}
                      <a
                        href={evt.html_link}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition"
                        title="View in Google Calendar"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Event Details Modal */}
      {selectedEvent && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in"
          onClick={() => setSelectedEvent(null)}
        >
          <div
            className="bg-white rounded-3xl shadow-2xl max-w-lg w-full overflow-hidden border border-slate-200 space-y-0"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="bg-gradient-to-r from-indigo-600 to-indigo-700 p-5 text-white flex items-start justify-between">
              <div className="space-y-1">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-white/20 text-white">
                  <CalendarIcon className="w-3 h-3" /> Google Calendar Event
                </div>
                <h3 className="text-lg font-black tracking-tight">{selectedEvent.summary}</h3>
                {selectedEvent.prospect_name && (
                  <p className="text-xs text-indigo-100 font-bold">
                    Associated Prospect: {selectedEvent.prospect_name}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setSelectedEvent(null)}
                className="text-white/80 hover:text-white p-1 rounded-lg hover:bg-white/10 transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-5 text-xs font-medium text-slate-700">
              {/* Timing */}
              <div className="flex items-start gap-3 p-3.5 bg-slate-50 rounded-2xl border border-slate-200">
                <Clock className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                <div>
                  <div className="font-extrabold text-slate-900 text-xs">
                    {formatDateTimeForUser(selectedEvent.start, user?.timezone)}
                  </div>
                  <div className="text-[11px] text-slate-500 font-semibold mt-0.5">
                    Timezone: {user?.timezone || "UTC"}
                  </div>
                </div>
              </div>

              {/* Google Meet Section */}
              {selectedEvent.meet_url ? (
                <div className="p-4 bg-gradient-to-r from-indigo-50 to-purple-50 rounded-2xl border border-indigo-200/80 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-extrabold text-indigo-950 flex items-center gap-1.5">
                      <Video className="w-4 h-4 text-indigo-600" />
                      Google Meet Video Call
                    </span>
                    <span className="text-[10px] font-black text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-full">
                      Ready
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <a
                      href={selectedEvent.meet_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold text-xs rounded-xl shadow-sm transition"
                    >
                      <Video className="w-3.5 h-3.5" />
                      <span>Join with Google Meet</span>
                    </a>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(selectedEvent.meet_url)}
                      className="inline-flex items-center gap-1.5 px-3 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 font-bold text-xs rounded-xl transition shadow-sm cursor-pointer"
                    >
                      {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copiedLink ? "Copied" : "Copy Link"}</span>
                    </button>
                  </div>

                  <div className="text-[10px] text-slate-500 break-all font-mono">
                    {selectedEvent.meet_url}
                  </div>
                </div>
              ) : (
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-500 text-xs">
                  No video conference attached to this Google Calendar event.
                </div>
              )}

              {/* Description / Agenda */}
              {selectedEvent.description && (
                <div className="space-y-1.5">
                  <label className="text-[11px] font-extrabold text-slate-800 uppercase tracking-wider block">
                    Agenda / Description
                  </label>
                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-slate-700 leading-relaxed whitespace-pre-wrap">
                    {selectedEvent.description}
                  </div>
                </div>
              )}

              {/* Attendees */}
              {selectedEvent.attendees?.length > 0 && (
                <div className="space-y-2">
                  <label className="text-[11px] font-extrabold text-slate-800 uppercase tracking-wider block">
                    Guests / Attendees ({selectedEvent.attendees.length})
                  </label>
                  <div className="max-h-40 overflow-y-auto space-y-1.5 p-2 bg-slate-50 rounded-xl border border-slate-200">
                    {selectedEvent.attendees.map((att, idx) => {
                      const isAccepted = att.response === "accepted";
                      const isDeclined = att.response === "declined";
                      return (
                        <div
                          key={idx}
                          className="flex items-center justify-between text-xs py-1 px-2 rounded-lg bg-white border border-slate-100"
                        >
                          <span className="truncate font-semibold text-slate-800">
                            {att.name || att.email} {att.self && "(You)"}
                          </span>
                          <span
                            className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                              isAccepted
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : isDeclined
                                ? "bg-rose-50 text-rose-700 border border-rose-200"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {isAccepted ? "Accepted" : isDeclined ? "Declined" : "Invited"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
              <a
                href={selectedEvent.html_link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-extrabold text-indigo-700 hover:text-indigo-900 transition"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open in Google Calendar</span>
              </a>
              <button
                type="button"
                onClick={() => setSelectedEvent(null)}
                className="px-4 py-2 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 font-extrabold text-xs rounded-xl shadow-sm transition cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
