import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../services/api';
import { extractErrorMessage } from '../../utils/errorUtils';
import {
  getCachedData,
  getCachedRecord,
  setCachedData,
  removeCachedData,
  invalidateCache,
} from '../../services/cache/cacheService';
import {
  listCacheKey,
  detailCacheKey,
  listCachePrefix,
} from '../../services/cache/cacheKeys';

const RESOURCE = 'prospects';
const STALE_TIME_MS = 15000; // 15 seconds

function getUserId(thunkAPI) {
  return thunkAPI.getState().auth?.user?.id;
}

// ─── Thunks ───────────────────────────────────────────────────────────────────

/**
 * Fetch prospects list with optional filters/pagination.
 * Cache-first: returns cached data if available; otherwise calls backend.
 */
export const fetchProspects = createAsyncThunk(
  'prospects/fetchAll',
  async (params, thunkAPI) => {
    const userId = getUserId(thunkAPI);
    const normalizedParams = params || {};
    const cacheKey = listCacheKey(userId, RESOURCE, normalizedParams);

    if (userId) {
      const record = await getCachedRecord(cacheKey);
      if (record) {
        thunkAPI.dispatch({ type: 'prospects/setCachedList', payload: record.data });
        if (Date.now() - record.cachedAt < STALE_TIME_MS) {
          return record.data; // Cache is fresh, skip background fetch
        }
      }
    }

    try {
      const response = await api.get('/prospects/', { params: normalizedParams });
      if (userId) {
        await setCachedData(cacheKey, response.data);
      }
      return response.data;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

/**
 * Fetch a single prospect by ID.
 * Cache-first: returns cached entry if available.
 */
export const fetchProspectById = createAsyncThunk(
  'prospects/fetchById',
  async (id, thunkAPI) => {
    const userId = getUserId(thunkAPI);
    const cacheKey = detailCacheKey(userId, RESOURCE, id);

    if (userId) {
      const record = await getCachedRecord(cacheKey);
      if (record) {
        thunkAPI.dispatch({ type: 'prospects/setCachedDetail', payload: record.data });
        if (Date.now() - record.cachedAt < STALE_TIME_MS) {
          return record.data; // Cache is fresh, skip background fetch
        }
      }
    }

    try {
      const response = await api.get(`/prospects/${id}/`);
      if (userId) {
        await setCachedData(cacheKey, response.data);
      }
      return response.data;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const createProspect = createAsyncThunk(
  'prospects/create',
  async (data, thunkAPI) => {
    try {
      const response = await api.post('/prospects/', data);
      const userId = getUserId(thunkAPI);
      if (userId) {
        await setCachedData(detailCacheKey(userId, RESOURCE, response.data.id), response.data);
        await invalidateCache(listCachePrefix(userId, RESOURCE));
      }
      return response.data;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const updateProspect = createAsyncThunk(
  'prospects/update',
  async ({ id, data }, thunkAPI) => {
    try {
      const response = await api.put(`/prospects/${id}/`, data);
      const userId = getUserId(thunkAPI);
      if (userId) {
        await setCachedData(detailCacheKey(userId, RESOURCE, id), response.data);
        await invalidateCache(listCachePrefix(userId, RESOURCE));
      }
      return response.data;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const deleteProspect = createAsyncThunk(
  'prospects/delete',
  async (id, thunkAPI) => {
    try {
      await api.delete(`/prospects/${id}/`);
      const userId = getUserId(thunkAPI);
      if (userId) {
        await removeCachedData(detailCacheKey(userId, RESOURCE, id));
        await invalidateCache(listCachePrefix(userId, RESOURCE));
      }
      return id;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────────────────────

const initialState = {
  items: [],
  count: 0,
  next: null,
  previous: null,
  selectedProspect: null,
  loading: false,
  error: null,
  filters: {},
  search: '',
  page: 1,
};

const prospectSlice = createSlice({
  name: 'prospects',
  initialState,
  reducers: {
    setFilters: (state, action) => {
      state.filters = action.payload;
      state.page = 1;
    },
    setSearch: (state, action) => {
      state.search = action.payload;
      state.page = 1;
    },
    setPage: (state, action) => {
      state.page = action.payload;
    },
    clearSelectedProspect: (state) => {
      state.selectedProspect = null;
    },
    setCachedList: (state, action) => {
      state.items = action.payload.results || action.payload;
      state.count = action.payload.count || action.payload.length;
      state.next = action.payload.next;
      state.previous = action.payload.previous;
    },
    setCachedDetail: (state, action) => {
      state.selectedProspect = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchProspects.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchProspects.fulfilled, (state, action) => {
        state.loading = false;
        state.items = action.payload.results || action.payload;
        state.count = action.payload.count || action.payload.length;
        state.next = action.payload.next;
        state.previous = action.payload.previous;
      })
      .addCase(fetchProspects.rejected, (state, action) => {
        state.loading = false;
        state.error = extractErrorMessage(action, 'Failed to load prospects. Please try again.');
      })
      .addCase(fetchProspectById.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchProspectById.fulfilled, (state, action) => {
        state.loading = false;
        state.selectedProspect = action.payload;
      })
      .addCase(fetchProspectById.rejected, (state, action) => {
        state.loading = false;
        state.error = extractErrorMessage(action, 'Failed to fetch prospect details. Please try again.');
      })
      .addCase(createProspect.fulfilled, (state, action) => {
        state.items.unshift(action.payload);
        state.count += 1;
      })
      .addCase(updateProspect.fulfilled, (state, action) => {
        const index = state.items.findIndex((p) => p.id === action.payload.id);
        if (index !== -1) {
          state.items[index] = action.payload;
        }
        if (state.selectedProspect?.id === action.payload.id) {
          state.selectedProspect = action.payload;
        }
      })
      .addCase(deleteProspect.fulfilled, (state, action) => {
        state.items = state.items.filter((p) => p.id !== action.payload);
        state.count -= 1;
      });
  },
});

export const { setFilters, setSearch, setPage, clearSelectedProspect } = prospectSlice.actions;
export default prospectSlice.reducer;
