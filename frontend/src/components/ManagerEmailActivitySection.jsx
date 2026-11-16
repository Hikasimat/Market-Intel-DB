import React, { useEffect, useState, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  Mail, RefreshCw, Search, Eye, X, Paperclip, Sparkles,
  ChevronLeft, ChevronRight, ArrowUpRight, ArrowDownLeft, AlertCircle, Clock,
} from 'lucide-react';
import {
  fetchManagerEmailActivity,
  fetchManagerEmailThreadDetail,
  refreshManagerEmailSummary,
  clearSelectedEmailThread,
} from '../features/manager/managerSlice';

const statusBadgeClass = (st) => {
  const map = {
    REPLIED: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    WAITING_REPLY: 'bg-amber-100 text-amber-700 border-amber-200',
    FAILED: 'bg-red-100 text-red-700 border-red-200',
    SENDING: 'bg-sky-100 text-sky-700 border-sky-200',
    UNMATCHED: 'bg-slate-100 text-slate-600 border-slate-200',
  };
  return map[st] || 'bg-slate-100 text-slate-600 border-slate-200';
};

const formatTimestamp = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
};

export default function ManagerEmailActivitySection({ selectedDate }) {
  const dispatch = useDispatch();
  const {
    emailActivity,
    emailActivityLoading,
    emailActivityError,
    selectedEmailThread,
    selectedEmailThreadLoading,
    selectedEmailThreadError,
    refreshingSummaryId,
  } = useSelector((state) => state.manager);

  const [preUserId, setPreUserId] = useState('all');
  const [searchInput, setSearchInput] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [useSelectedDate, setUseSelectedDate] = useState(false);
  const [page, setPage] = useState(1);

  const loadThreads = useCallback((forceSync = false) => {
    const params = {
      pre_user_id: preUserId,
      search: appliedSearch,
      status: statusFilter,
      page,
      page_size: 15,
    };
    if (forceSync) params.sync = true;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    if (!dateFrom && !dateTo && useSelectedDate && selectedDate) {
      params.date = selectedDate;
    }
    dispatch(fetchManagerEmailActivity(params));
  }, [dispatch, preUserId, appliedSearch, statusFilter, dateFrom, dateTo, useSelectedDate, selectedDate, page]);

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    setAppliedSearch(searchInput.trim());
  };

  const handleOpenThread = (threadId) => {
    dispatch(fetchManagerEmailThreadDetail(threadId));
  };

  const handleCloseThread = () => {
    dispatch(clearSelectedEmailThread());
  };

  const handleRefreshSummary = (threadId, e) => {
    if (e) e.stopPropagation();
    dispatch(refreshManagerEmailSummary(threadId));
  };

  const preUsers = emailActivity?.pre_users || [];
  const threads = emailActivity?.results || [];
  const stats = emailActivity?.stats || {};
  const totalPages = emailActivity?.total_pages || 1;
  const totalCount = emailActivity?.count || 0;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-100 bg-sky-50 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-black text-sky-900 flex items-center gap-2">
            <Mail className="w-5 h-5 text-sky-600" />
            PRE Email Activity &amp; Conversation Summaries
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Track outreach, inbox threads, incoming replies, and AI summaries across all PRE users ({preUsers.length} active PRE/LQ users).
          </p>
        </div>
        <div className="flex items-center gap-2">
          {stats?.total_threads !== undefined && (
            <div className="hidden sm:flex items-center gap-2 text-xs font-bold">
              <span className="px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-700">
                Total: {stats.total_threads}
              </span>
              <span className="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700">
                Replied: {stats.replied || 0}
              </span>
              <span className="px-2.5 py-1 rounded-full bg-amber-100 text-amber-700">
                Waiting: {stats.waiting_reply || 0}
              </span>
              {stats.failed > 0 && (
                <span className="px-2.5 py-1 rounded-full bg-red-100 text-red-700">
                  Failed: {stats.failed}
                </span>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={() => loadThreads(true)}
            disabled={emailActivityLoading}
            className="px-3 py-1.5 bg-white hover:bg-slate-100 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 transition-colors inline-flex items-center gap-1.5"
            title="Sync incoming replies & refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${emailActivityLoading ? 'animate-spin' : ''}`} />
            Sync &amp; Refresh
          </button>
        </div>
      </div>

      {/* Filters Toolbar */}
      <div className="px-6 py-3.5 bg-slate-50 border-b border-slate-100 flex flex-wrap items-center gap-3">
        <select
          value={preUserId}
          onChange={(e) => { setPreUserId(e.target.value); setPage(1); }}
          aria-label="Filter by PRE user"
          className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
        >
          <option value="all">All PRE Users ({preUsers.length})</option>
          {preUsers.map((u) => (
            <option key={u.id} value={String(u.id)}>
              {u.name} ({u.role}) — {u.thread_count}
            </option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          aria-label="Filter by status"
          className="px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
        >
          <option value="ALL">All Statuses</option>
          <option value="REPLIED">Replied</option>
          <option value="WAITING_REPLY">Waiting Reply</option>
          <option value="FAILED">Failed</option>
          <option value="UNMATCHED">Unmatched</option>
        </select>

        <div className="flex items-center gap-1.5 text-xs">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => { setDateFrom(e.target.value); setUseSelectedDate(false); setPage(1); }}
            aria-label="Date from"
            className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs text-slate-700"
          />
          <span className="text-slate-400">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => { setDateTo(e.target.value); setUseSelectedDate(false); setPage(1); }}
            aria-label="Date to"
            className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs text-slate-700"
          />
        </div>

        <label className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 cursor-pointer">
          <input
            type="checkbox"
            checked={useSelectedDate}
            onChange={(e) => {
              setUseSelectedDate(e.target.checked);
              if (e.target.checked) {
                setDateFrom('');
                setDateTo('');
              }
              setPage(1);
            }}
            className="rounded border-slate-300 text-sky-600"
          />
          Only {selectedDate}
        </label>

        <form onSubmit={handleSearchSubmit} className="flex items-center gap-1.5 ml-auto">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search subject, contact, prospect..."
              className="pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-700 w-56 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>
          <button
            type="submit"
            className="px-3 py-1.5 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg transition-colors"
          >
            Search
          </button>
        </form>
      </div>

      {/* Error */}
      {emailActivityError && (
        <div className="px-6 py-4 bg-red-50 border-b border-red-100 flex items-center gap-2 text-xs text-red-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{typeof emailActivityError === 'string' ? emailActivityError : JSON.stringify(emailActivityError)}</span>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">PRE User</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Prospect / Contact</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Subject &amp; Snippet</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">AI Summary</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Status</th>
              <th className="px-4 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Msgs</th>
              <th className="px-4 py-3 text-left text-xs font-bold text-slate-500 uppercase tracking-wider">Latest Activity</th>
              <th className="px-4 py-3 text-right text-xs font-bold text-slate-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {emailActivityLoading && threads.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-10 text-center text-slate-400 text-sm">
                  Loading PRE email conversations...
                </td>
              </tr>
            ) : threads.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-6 py-10 text-center text-slate-400 text-sm italic">
                  No email conversations match the current filter.
                </td>
              </tr>
            ) : (
              threads.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => handleOpenThread(t.id)}
                  className="hover:bg-sky-50/40 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 align-top whitespace-nowrap">
                    <div className="text-xs font-bold text-slate-800">{t.pre_user?.name || '—'}</div>
                    <div className="text-[11px] text-slate-500 font-mono truncate max-w-[160px]">{t.mailbox_email || t.pre_user?.email || '—'}</div>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <div className="text-xs font-semibold text-slate-800 truncate max-w-[180px]">
                      {t.prospect_name || (t.match_status === 'UNMATCHED' ? 'Unmatched Contact' : '—')}
                    </div>
                    <div className="text-[11px] text-slate-500 truncate max-w-[180px]">
                      {t.correspondent_name ? `${t.correspondent_name} · ` : ''}{t.correspondent_email || '—'}
                    </div>
                  </td>
                  <td className="px-4 py-3 align-top max-w-[240px]">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800 truncate">
                      {t.last_direction === 'INBOUND' ? (
                        <ArrowDownLeft className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" title="Latest message received" />
                      ) : (
                        <ArrowUpRight className="w-3.5 h-3.5 text-sky-600 flex-shrink-0" title="Latest message sent" />
                      )}
                      <span className="truncate">{t.subject || '(No Subject)'}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 line-clamp-2 mt-0.5">{t.last_snippet || '—'}</p>
                  </td>
                  <td className="px-4 py-3 align-top max-w-[300px]">
                    {t.summary_text ? (
                      <div>
                        <p className="text-xs text-slate-700 line-clamp-2">{t.summary_text}</p>
                        {t.next_action && (
                          <p className="text-[11px] text-sky-700 font-semibold mt-0.5 truncate">
                            Next: {t.next_action}
                          </p>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400 italic">
                        {t.summary_status === 'PENDING' ? 'Summary pending...' : 'No summary yet'}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top whitespace-nowrap">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-bold border ${statusBadgeClass(t.status)}`}>
                      {t.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 align-top text-right text-xs font-bold text-slate-700 whitespace-nowrap">
                    {t.message_count}
                  </td>
                  <td className="px-4 py-3 align-top whitespace-nowrap text-xs text-slate-500">
                    {formatTimestamp(t.last_message_at)}
                  </td>
                  <td className="px-4 py-3 align-top text-right whitespace-nowrap">
                    <div className="inline-flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={(e) => handleRefreshSummary(t.id, e)}
                        disabled={refreshingSummaryId === t.id}
                        className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-600 transition-colors"
                        title="Regenerate AI Summary"
                      >
                        <Sparkles className={`w-3.5 h-3.5 ${refreshingSummaryId === t.id ? 'animate-spin text-sky-600' : ''}`} />
                      </button>
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); handleOpenThread(t.id); }}
                        className="px-2.5 py-1 rounded-lg bg-sky-50 hover:bg-sky-100 text-sky-700 text-xs font-bold inline-flex items-center gap-1"
                      >
                        <Eye className="w-3.5 h-3.5" /> View
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="px-6 py-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
        <span>
          Showing page <strong>{page}</strong> of <strong>{totalPages}</strong> ({totalCount} threads)
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1 || emailActivityLoading}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-100 inline-flex items-center gap-1 font-semibold"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Prev
          </button>
          <button
            type="button"
            disabled={page >= totalPages || emailActivityLoading}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg disabled:opacity-40 hover:bg-slate-100 inline-flex items-center gap-1 font-semibold"
          >
            Next <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Conversation Detail Modal */}
      {(selectedEmailThread || selectedEmailThreadLoading || selectedEmailThreadError) && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-start justify-between gap-4 bg-slate-50">
              <div className="min-w-0">
                <h3 className="text-base font-black text-slate-900 truncate">
                  {selectedEmailThread?.subject || 'Email Thread'}
                </h3>
                {selectedEmailThread && (
                  <p className="text-xs text-slate-500 mt-0.5">
                    PRE: <strong>{selectedEmailThread.pre_user?.name}</strong> · Correspondent: <strong>{selectedEmailThread.correspondent_email}</strong>
                    {selectedEmailThread.prospect_name ? ` · Prospect: ${selectedEmailThread.prospect_name}` : ''}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={handleCloseThread}
                className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-500"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {selectedEmailThreadLoading && (
                <div className="text-center py-12 text-slate-400 text-sm">Loading thread messages...</div>
              )}

              {selectedEmailThreadError && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
                  {typeof selectedEmailThreadError === 'string' ? selectedEmailThreadError : JSON.stringify(selectedEmailThreadError)}
                </div>
              )}

              {selectedEmailThread && !selectedEmailThreadLoading && (
                <>
                  {/* AI Summary Box */}
                  <div className="rounded-xl bg-sky-50 border border-sky-200 p-4 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-black text-sky-900 uppercase tracking-wider flex items-center gap-1.5 flex-wrap">
                        <Sparkles className="w-4 h-4 text-sky-600" />
                        AI Conversation Summary ({selectedEmailThread.summary_provider || 'pending'}
                        {selectedEmailThread.summary_model && selectedEmailThread.summary_status === 'READY'
                          ? ` · ${selectedEmailThread.summary_model}`
                          : ''})
                        {selectedEmailThread.summary_status === 'FAILED' && (
                          <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 text-[10px] font-bold">
                            AI Fallback
                          </span>
                        )}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleRefreshSummary(selectedEmailThread.id)}
                        disabled={refreshingSummaryId === selectedEmailThread.id}
                        className="px-2.5 py-1 rounded-lg bg-white hover:bg-sky-100 border border-sky-200 text-sky-700 text-xs font-bold inline-flex items-center gap-1"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${refreshingSummaryId === selectedEmailThread.id ? 'animate-spin' : ''}`} />
                        Refresh Summary
                      </button>
                    </div>
                    {selectedEmailThread.summary_status === 'FAILED' && selectedEmailThread.summary_error && (
                      <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5">
                        AI provider fallback active: {selectedEmailThread.summary_error}
                      </div>
                    )}
                    <p className="text-sm text-slate-800">{selectedEmailThread.summary_text || 'Summary unavailable.'}</p>
                    {selectedEmailThread.next_action && (
                      <p className="text-xs font-semibold text-sky-800">
                        Recommended Next Action: {selectedEmailThread.next_action}
                      </p>
                    )}
                  </div>

                  {/* Chronological Messages */}
                  <div className="space-y-3">
                    {(selectedEmailThread.messages || []).map((m) => (
                      <div
                        key={m.id}
                        className={`rounded-xl border p-4 ${
                          m.direction === 'INBOUND'
                            ? 'bg-emerald-50/40 border-emerald-200'
                            : 'bg-white border-slate-200'
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 mb-2 text-xs">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                              m.direction === 'INBOUND' ? 'bg-emerald-100 text-emerald-700' : 'bg-sky-100 text-sky-700'
                            }`}>
                              {m.direction}
                            </span>
                            <span className="font-bold text-slate-800">{m.sender_name || m.sender_email}</span>
                            <span className="text-slate-400">to {(m.to_emails || []).join(', ') || '—'}</span>
                          </div>
                          <span className="text-slate-400 inline-flex items-center gap-1">
                            <Clock className="w-3 h-3" /> {formatTimestamp(m.sent_at || m.created_at)}
                          </span>
                        </div>
                        <div className="text-xs font-semibold text-slate-700 mb-1">{m.subject}</div>
                        <div className="text-sm text-slate-700 whitespace-pre-wrap break-words">
                          {m.body_text || m.snippet || '(No plain text content)'}
                        </div>
                        {Array.isArray(m.attachments_metadata) && m.attachments_metadata.length > 0 && (
                          <div className="mt-3 pt-2 border-t border-slate-100 flex flex-wrap gap-2">
                            {m.attachments_metadata.map((att, idx) => (
                              <span
                                key={idx}
                                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 text-[11px] font-medium"
                              >
                                <Paperclip className="w-3 h-3" />
                                {att.filename} ({att.size ? `${Math.round(att.size / 1024)} KB` : 'file'})
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

