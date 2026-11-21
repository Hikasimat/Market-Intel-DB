import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../services/api';
import { extractErrorMessage } from '../../utils/errorUtils';
import {
  getCachedData,
  getCachedRecord,
  setCachedData,
  invalidateCache,
} from '../../services/cache/cacheService';
import {
  listCacheKey,
  detailCacheKey,
  listCachePrefix,
} from '../../services/cache/cacheKeys';

const RESOURCE = 'lq-pipeline';
const STALE_TIME_MS = 15000; // 15 seconds

function getUserId(thunkAPI) {
  return thunkAPI.getState().auth?.user?.id;
}

// ─── Thunks ───────────────────────────────────────────────────────────────────

/**
 * Fetch the LQ pipeline list with optional filters.
 * Cache-first: returns cached data if available; otherwise calls backend.
 */
export const fetchLqPipeline = createAsyncThunk(
  'lqPipeline/fetchAll',
  async (filters = {}, thunkAPI) => {
    const userId = getUserId(thunkAPI);
    const cacheKey = listCacheKey(userId, RESOURCE, filters);

    // Show cached data immediately while fetching (stale-while-revalidate)
    if (userId) {
      const record = await getCachedRecord(cacheKey);
      if (record) {
        thunkAPI.dispatch({ type: 'lqPipeline/setCachedList', payload: record.data });
        // Do NOT return early — always fetch fresh from server
      }
    }

    try {
      const response = await api.get('/lq-pipeline/', { params: filters });
      if (userId) {
        await setCachedData(cacheKey, response.data);
      }
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(error.response?.data || error.message);
    }
  }
);

/**
 * Fetch a single LQ pipeline item.
 * Cache-first: returns cached entry if available.
 */
export const fetchLqPipelineItem = createAsyncThunk(
  'lqPipeline/fetchOne',
  async (id, thunkAPI) => {
    const userId = getUserId(thunkAPI);
    const cacheKey = detailCacheKey(userId, RESOURCE, id);

    if (userId) {
      const record = await getCachedRecord(cacheKey);
      if (record) {
        thunkAPI.dispatch({ type: 'lqPipeline/setCachedDetail', payload: record.data });
        if (Date.now() - record.cachedAt < STALE_TIME_MS) {
          return record.data; // Cache is fresh, skip background fetch
        }
      }
    }

    try {
      const response = await api.get(`/lq-pipeline/${id}/`);
      if (userId) {
        await setCachedData(cacheKey, response.data);
      }
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(error.response?.data || error.message);
    }
  }
);

// ─── Mutation thunks (update cache after success) ─────────────────────────────

async function updateCacheAfterMutation(thunkAPI, result) {
  const userId = getUserId(thunkAPI);
  if (!userId) return;
  await setCachedData(detailCacheKey(userId, RESOURCE, result.id), result);
  await invalidateCache(listCachePrefix(userId, RESOURCE));
}

export const updateVerification = createAsyncThunk(
  'lqPipeline/updateVerification',
  async ({ id, verification_status }, thunkAPI) => {
    try {
      const response = await api.post(`/lq-pipeline/${id}/verify/`, { verification_status });
      await updateCacheAfterMutation(thunkAPI, response.data);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(error.response?.data || error.message);
    }
  }
);

export const submitQualification = createAsyncThunk(
  'lqPipeline/submitQualification',
  async ({ id, ...qualificationData }, thunkAPI) => {
    try {
      const response = await api.post(`/lq-pipeline/${id}/qualification/`, qualificationData);
      await updateCacheAfterMutation(thunkAPI, response.data);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(error.response?.data || error.message);
    }
  }
);

export const reportIssueToPre = createAsyncThunk(
  'lqPipeline/reportIssue',
  async ({ id, issueData }, thunkAPI) => {
    try {
      const response = await api.post(`/lq-pipeline/${id}/report-issue/`, issueData);
      await updateCacheAfterMutation(thunkAPI, response.data);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(error.response?.data || error.message);
    }
  }
);

export const completePreTask = createAsyncThunk(
  'lqPipeline/completePreTask',
  async (id, thunkAPI) => {
    try {
      const response = await api.post(`/lq-pipeline/${id}/complete-pre-task/`);
      await updateCacheAfterMutation(thunkAPI, response.data);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(error.response?.data || error.message);
    }
  }
);

export const confirmReverification = createAsyncThunk(
  'lqPipeline/confirmReverification',
  async (id, thunkAPI) => {
    try {
      const response = await api.post(`/lq-pipeline/${id}/confirm-reverification/`);
      await updateCacheAfterMutation(thunkAPI, response.data);
      return response.data;
    } catch (error) {
      return thunkAPI.rejectWithValue(error.response?.data || error.message);
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────────────────────

const lqPipelineSlice = createSlice({
  name: 'lqPipeline',
  initialState: {
    items: [],
    selectedItem: null,
    loading: false,
    error: null,
    count: 0,
    page: 1,
    filters: {},
  },
  reducers: {
    clearSelectedItem: (state) => {
      state.selectedItem = null;
    },
    setPage: (state, action) => {
      state.page = action.payload;
    },
    setFilters: (state, action) => {
      state.filters = action.payload;
      state.page = 1;
    },
    setCachedList: (state, action) => {
      state.items = action.payload.results || action.payload;
      state.count = action.payload.count || action.payload.length;
    },
    setCachedDetail: (state, action) => {
      state.selectedItem = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetch all
      .addCase(fetchLqPipeline.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(fetchLqPipeline.fulfilled, (state, action) => {
        state.loading = false;
        state.items = action.payload.results || action.payload;
        state.count = action.payload.count || action.payload.length;
      })
      .addCase(fetchLqPipeline.rejected, (state, action) => { state.loading = false; state.error = extractErrorMessage(action, 'Failed to load outreach pipeline. Please try again.'); })
      // fetch one
      .addCase(fetchLqPipelineItem.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(fetchLqPipelineItem.fulfilled, (state, action) => { state.loading = false; state.selectedItem = action.payload; })
      .addCase(fetchLqPipelineItem.rejected, (state, action) => { state.loading = false; state.error = extractErrorMessage(action, 'Failed to load outreach details. Please try again.'); })
      // actions that update a single item in the list/selectedItem
      .addMatcher(
        (action) => [
          updateVerification.fulfilled.type,
          submitQualification.fulfilled.type,
          reportIssueToPre.fulfilled.type,
          confirmReverification.fulfilled.type,
          completePreTask.fulfilled.type,
        ].includes(action.type),
        (state, action) => {
          state.loading = false;
          if (state.selectedItem && state.selectedItem.id === action.payload.id) {
            state.selectedItem = action.payload;
          }
          const index = state.items.findIndex((item) => item.id === action.payload.id);
          if (index !== -1) {
            state.items[index] = action.payload;
          }
        }
      )
      // common pending for mutation actions
      .addMatcher(
        (action) => [
          updateVerification.pending.type,
          submitQualification.pending.type,
          reportIssueToPre.pending.type,
          confirmReverification.pending.type,
          completePreTask.pending.type,
        ].includes(action.type),
        (state) => { state.loading = true; state.error = null; }
      )
      // common rejected for mutation actions
      .addMatcher(
        (action) => [
          updateVerification.rejected.type,
          submitQualification.rejected.type,
          reportIssueToPre.rejected.type,
          confirmReverification.rejected.type,
          completePreTask.rejected.type,
        ].includes(action.type),
        (state, action) => { state.loading = false; state.error = action.payload; }
      );
  },
});

export const { clearSelectedItem, setPage, setFilters } = lqPipelineSlice.actions;
export default lqPipelineSlice.reducer;
