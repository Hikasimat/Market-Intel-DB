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

const RESOURCE = 'market-events';
const STALE_TIME_MS = 15000; // 15 seconds

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getUserId(thunkAPI) {
  return thunkAPI.getState().auth?.user?.id;
}

// ─── Thunks ───────────────────────────────────────────────────────────────────

/**
 * Fetch market events list.
 * Cache-first: returns cached data immediately if available; otherwise calls backend.
 */
export const fetchMarketEvents = createAsyncThunk(
  'marketEvents/fetchAll',
  async (params = {}, thunkAPI) => {
    const userId = getUserId(thunkAPI);
    const cacheKey = listCacheKey(userId, RESOURCE, params);

    if (userId) {
      const record = await getCachedRecord(cacheKey);
      if (record) {
        thunkAPI.dispatch({ type: 'marketEvents/setCachedList', payload: record.data });
        if (Date.now() - record.cachedAt < STALE_TIME_MS) {
          return record.data; // Cache is fresh, skip background fetch
        }
      }
    }

    try {
      const response = await api.get('/market-events/', { params });
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
 * Fetch a single market event detail.
 * Cache-first: returns cached entry if available.
 */
export const fetchMarketEvent = createAsyncThunk(
  'marketEvents/fetchOne',
  async (id, thunkAPI) => {
    const userId = getUserId(thunkAPI);
    const cacheKey = detailCacheKey(userId, RESOURCE, id);

    if (userId) {
      const record = await getCachedRecord(cacheKey);
      if (record) {
        thunkAPI.dispatch({ type: 'marketEvents/setCachedDetail', payload: record.data });
        if (Date.now() - record.cachedAt < STALE_TIME_MS) {
          return record.data; // Cache is fresh, skip background fetch
        }
      }
    }

    try {
      const response = await api.get(`/market-events/${id}/`);
      if (userId) {
        await setCachedData(cacheKey, response.data);
      }
      return response.data;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const createMarketEvent = createAsyncThunk(
  'marketEvents/create',
  async (data, thunkAPI) => {
    try {
      const response = await api.post('/market-events/', data);
      const userId = getUserId(thunkAPI);
      if (userId) {
        // Cache the new detail entry and invalidate all list caches
        await setCachedData(detailCacheKey(userId, RESOURCE, response.data.id), response.data);
        await invalidateCache(listCachePrefix(userId, RESOURCE));
      }
      return response.data;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const updateMarketEvent = createAsyncThunk(
  'marketEvents/update',
  async ({ id, data }, thunkAPI) => {
    try {
      const response = await api.put(`/market-events/${id}/`, data);
      const userId = getUserId(thunkAPI);
      if (userId) {
        // Update detail cache and invalidate list caches
        await setCachedData(detailCacheKey(userId, RESOURCE, id), response.data);
        await invalidateCache(listCachePrefix(userId, RESOURCE));
      }
      return response.data;
    } catch (err) {
      return thunkAPI.rejectWithValue(err.response?.data || err.message);
    }
  }
);

export const deleteMarketEvent = createAsyncThunk(
  'marketEvents/delete',
  async (id, thunkAPI) => {
    try {
      await api.delete(`/market-events/${id}/`);
      const userId = getUserId(thunkAPI);
      if (userId) {
        // Remove detail cache and invalidate list caches
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

const marketEventSlice = createSlice({
  name: 'marketEvents',
  initialState: {
    items: [],
    selectedMarketEvent: null,
    loading: false,
    error: null,
    count: 0,
    page: 1,
    search: '',
  },
  reducers: {
    clearSelectedMarketEvent: (state) => {
      state.selectedMarketEvent = null;
    },
    setSearch: (state, action) => {
      state.search = action.payload;
      state.page = 1;
    },
    setPage: (state, action) => {
      state.page = action.payload;
    },
    setCachedList: (state, action) => {
      if (action.payload.results !== undefined) {
        state.items = action.payload.results;
        state.count = action.payload.count;
      } else {
        state.items = action.payload;
        state.count = action.payload.length;
      }
    },
    setCachedDetail: (state, action) => {
      state.selectedMarketEvent = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      // Fetch all
      .addCase(fetchMarketEvents.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchMarketEvents.fulfilled, (state, action) => {
        state.loading = false;
        if (action.payload.results !== undefined) {
          state.items = action.payload.results;
          state.count = action.payload.count;
        } else {
          state.items = action.payload;
          state.count = action.payload.length;
        }
      })
      .addCase(fetchMarketEvents.rejected, (state, action) => {
        state.loading = false;
        state.error = extractErrorMessage(action, 'Failed to load market events. Please try again.');
      })
      // Fetch one
      .addCase(fetchMarketEvent.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchMarketEvent.fulfilled, (state, action) => {
        state.loading = false;
        state.selectedMarketEvent = action.payload;
      })
      .addCase(fetchMarketEvent.rejected, (state, action) => {
        state.loading = false;
        state.error = extractErrorMessage(action, 'Failed to load market event details. Please try again.');
      })
      // Create
      .addCase(createMarketEvent.fulfilled, (state, action) => {
        state.items.unshift(action.payload);
        state.count += 1;
      })
      // Update
      .addCase(updateMarketEvent.fulfilled, (state, action) => {
        const index = state.items.findIndex((item) => item.id === action.payload.id);
        if (index !== -1) {
          state.items[index] = action.payload;
        }
        if (state.selectedMarketEvent?.id === action.payload.id) {
          state.selectedMarketEvent = action.payload;
        }
      })
      // Delete
      .addCase(deleteMarketEvent.fulfilled, (state, action) => {
        state.items = state.items.filter((item) => item.id !== action.payload);
        state.count -= 1;
        if (state.selectedMarketEvent?.id === action.payload) {
          state.selectedMarketEvent = null;
        }
      });
  },
});

export const { clearSelectedMarketEvent, setSearch, setPage } = marketEventSlice.actions;
export default marketEventSlice.reducer;
