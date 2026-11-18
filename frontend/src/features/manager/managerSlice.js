import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../services/api';

export const fetchManagerDashboard = createAsyncThunk(
  'manager/fetchDashboard',
  async (date, { rejectWithValue }) => {
    try {
      const params = date ? { date } : {};
      const response = await api.get('/manager-dashboard/', { params });
      return response.data;
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const fetchManagerEmailActivity = createAsyncThunk(
  'manager/fetchEmailActivity',
  async (filters = {}, { rejectWithValue }) => {
    try {
      const params = {};
      if (filters.pre_user_id && filters.pre_user_id !== 'all') params.pre_user_id = filters.pre_user_id;
      if (filters.date_from) params.date_from = filters.date_from;
      if (filters.date_to) params.date_to = filters.date_to;
      if (filters.date) params.date = filters.date;
      if (filters.search) params.search = filters.search;
      if (filters.status && filters.status !== 'ALL') params.status = filters.status;
      if (filters.direction && filters.direction !== 'ALL') params.direction = filters.direction;
      if (filters.page) params.page = filters.page;
      if (filters.page_size) params.page_size = filters.page_size;
      if (filters.sync) params.sync = 'true';
      const response = await api.get('/manager-dashboard/email-activity/', { params, timeout: 60000 });
      return response.data;
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const fetchManagerEmailThreadDetail = createAsyncThunk(
  'manager/fetchEmailThreadDetail',
  async (threadId, { rejectWithValue }) => {
    try {
      const response = await api.get(`/manager-dashboard/email-activity/${threadId}/`);
      return response.data;
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const refreshManagerEmailSummary = createAsyncThunk(
  'manager/refreshEmailSummary',
  async (threadId, { rejectWithValue }) => {
    try {
      const response = await api.post(`/manager-dashboard/email-activity/${threadId}/refresh-summary/`);
      return response.data;
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const fetchManagerDailyEmailReport = createAsyncThunk(
  'manager/fetchDailyEmailReport',
  async (params = {}, { rejectWithValue }) => {
    try {
      const query = {};
      if (params.date) query.date = params.date;
      if (params.user_id && params.user_id !== 'all') query.user_id = params.user_id;
      if (params.sync) query.sync = 'true';
      if (params.force) query.force = 'true';
      const response = await api.get('/manager-dashboard/daily-email-report/', { params: query, timeout: 60000 });
      return response.data;
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const refreshManagerUserDailyEmailReport = createAsyncThunk(
  'manager/refreshUserDailyEmailReport',
  async ({ userId, date }, { rejectWithValue }) => {
    try {
      const response = await api.post(`/manager-dashboard/daily-email-report/${userId}/refresh/`, {
        date: date || undefined,
      });
      return response.data;
    } catch (err) {
      return rejectWithValue(err.response?.data || err.message);
    }
  }
);

const managerSlice = createSlice({
  name: 'manager',
  initialState: {
    dashboard: null,
    loading: false,
    error: null,
    emailActivity: {
      results: [],
      pre_users: [],
      stats: null,
      count: 0,
      page: 1,
      page_size: 20,
      total_pages: 1,
    },
    emailActivityLoading: false,
    emailActivityError: null,
    selectedEmailThread: null,
    selectedEmailThreadLoading: false,
    selectedEmailThreadError: null,
    refreshingSummaryId: null,
    dailyEmailReport: {
      date: '',
      totals: null,
      users: [],
    },
    dailyEmailReportLoading: false,
    dailyEmailReportError: null,
    refreshingUserDailyReportId: null,
  },
  reducers: {
    clearDashboard: (state) => {
      state.dashboard = null;
      state.error = null;
    },
    clearSelectedEmailThread: (state) => {
      state.selectedEmailThread = null;
      state.selectedEmailThreadError = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchManagerDashboard.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchManagerDashboard.fulfilled, (state, action) => {
        state.loading = false;
        state.dashboard = action.payload;
      })
      .addCase(fetchManagerDashboard.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload || action.error.message;
      })
      .addCase(fetchManagerEmailActivity.pending, (state) => {
        state.emailActivityLoading = true;
        state.emailActivityError = null;
      })
      .addCase(fetchManagerEmailActivity.fulfilled, (state, action) => {
        state.emailActivityLoading = false;
        state.emailActivity = action.payload;
      })
      .addCase(fetchManagerEmailActivity.rejected, (state, action) => {
        state.emailActivityLoading = false;
        state.emailActivityError = action.payload || action.error.message;
      })
      .addCase(fetchManagerEmailThreadDetail.pending, (state) => {
        state.selectedEmailThreadLoading = true;
        state.selectedEmailThreadError = null;
      })
      .addCase(fetchManagerEmailThreadDetail.fulfilled, (state, action) => {
        state.selectedEmailThreadLoading = false;
        state.selectedEmailThread = action.payload;
      })
      .addCase(fetchManagerEmailThreadDetail.rejected, (state, action) => {
        state.selectedEmailThreadLoading = false;
        state.selectedEmailThreadError = action.payload || action.error.message;
      })
      .addCase(refreshManagerEmailSummary.pending, (state, action) => {
        state.refreshingSummaryId = action.meta.arg;
      })
      .addCase(refreshManagerEmailSummary.fulfilled, (state, action) => {
        state.refreshingSummaryId = null;
        const updated = action.payload;
        if (updated?.id) {
          state.emailActivity.results = (state.emailActivity.results || []).map((t) =>
            t.id === updated.id ? { ...t, ...updated } : t
          );
          if (state.selectedEmailThread?.id === updated.id) {
            state.selectedEmailThread = { ...state.selectedEmailThread, ...updated };
          }
        }
      })
      .addCase(refreshManagerEmailSummary.rejected, (state) => {
        state.refreshingSummaryId = null;
      })
      .addCase(fetchManagerDailyEmailReport.pending, (state) => {
        state.dailyEmailReportLoading = true;
        state.dailyEmailReportError = null;
      })
      .addCase(fetchManagerDailyEmailReport.fulfilled, (state, action) => {
        state.dailyEmailReportLoading = false;
        state.dailyEmailReport = action.payload;
      })
      .addCase(fetchManagerDailyEmailReport.rejected, (state, action) => {
        state.dailyEmailReportLoading = false;
        state.dailyEmailReportError = action.payload || action.error.message;
      })
      .addCase(refreshManagerUserDailyEmailReport.pending, (state, action) => {
        state.refreshingUserDailyReportId = action.meta.arg?.userId ?? null;
      })
      .addCase(refreshManagerUserDailyEmailReport.fulfilled, (state, action) => {
        state.refreshingUserDailyReportId = null;
        const updated = action.payload;
        if (updated?.user_id) {
          state.dailyEmailReport.users = (state.dailyEmailReport.users || []).map((u) =>
            u.user_id === updated.user_id ? { ...u, ...updated } : u
          );
        }
      })
      .addCase(refreshManagerUserDailyEmailReport.rejected, (state) => {
        state.refreshingUserDailyReportId = null;
      });
  },
});

export const { clearDashboard, clearSelectedEmailThread } = managerSlice.actions;
export default managerSlice.reducer;
