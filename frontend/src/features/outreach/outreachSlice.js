import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import api from '../../services/api';

export const fetchMailAccounts = createAsyncThunk('outreach/fetchMailAccounts', async (_, { rejectWithValue }) => {
    try {
        const response = await api.get('/mail-account/');
        return response.data.results || response.data || [];
    } catch (error) {
        return rejectWithValue(error.response.data);
    }
});

export const setDefaultAccount = createAsyncThunk('outreach/setDefaultAccount', async (id, { rejectWithValue }) => {
    try {
        const response = await api.post(`/mail-account/${id}/set-default/`);
        return { id, ...response.data };
    } catch (error) {
        return rejectWithValue(error.response.data);
    }
});

export const saveMailAccount = createAsyncThunk('outreach/saveMailAccount', async (data, { rejectWithValue }) => {
    try {
        let response;
        if (data.id) {
            response = await api.patch(`/mail-account/${data.id}/`, data);
        } else {
            response = await api.post('/mail-account/', data);
        }
        return response.data;
    } catch (error) {
        return rejectWithValue(error.response.data);
    }
});

export const fetchCommunications = createAsyncThunk('outreach/fetchCommunications', async (prospectId, { rejectWithValue }) => {
    try {
        const response = await api.get(`/outreach/communications/?prospect=${prospectId}`);
        return response.data.results || response.data;
    } catch (error) {
        return rejectWithValue(error.response?.data || error.message);
    }
});

export const sendOutreachEmail = createAsyncThunk('outreach/sendEmail', async (formData, { rejectWithValue }) => {
    try {
        const response = await api.post('/outreach/emails/', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            }
        });
        return response.data;
    } catch (error) {
        return rejectWithValue(error.response?.data || { error: 'Network Error' });
    }
});

export const recordCall = createAsyncThunk('outreach/recordCall', async (data, { rejectWithValue }) => {
    try {
        const response = await api.post('/outreach/calls/', data);
        return response.data;
    } catch (error) {
        return rejectWithValue(error.response?.data || { error: 'Network Error' });
    }
});

export const syncMail = createAsyncThunk('outreach/syncMail', async (_, { rejectWithValue }) => {
    try {
        const response = await api.post('/outreach/emails/sync-gmail/');
        return response.data;
    } catch (error) {
        return rejectWithValue(error.response?.data || { error: 'Sync failed' });
    }
});
export const syncGmail = syncMail;
export const syncImap = syncMail;

const outreachSlice = createSlice({
    name: 'outreach',
    initialState: {
        mailAccounts: [],
        communications: [],
        status: 'idle', // idle, loading, succeeded, failed
        error: null,
    },
    reducers: {
        clearError(state) {
            state.error = null;
        }
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchMailAccounts.pending, (state) => { state.status = 'loading'; })
            .addCase(fetchMailAccounts.fulfilled, (state, action) => {
                state.status = 'succeeded';
                state.mailAccounts = action.payload;
            })
            .addCase(fetchMailAccounts.rejected, (state, action) => {
                state.status = 'failed';
                state.error = action.payload;
            })
            .addCase(saveMailAccount.fulfilled, (state, action) => {
                const index = state.mailAccounts.findIndex(a => a.id === action.payload.id);
                if (index !== -1) {
                    state.mailAccounts[index] = action.payload;
                } else {
                    state.mailAccounts.push(action.payload);
                }
            })
            .addCase(fetchCommunications.fulfilled, (state, action) => {
                state.communications = action.payload;
            });
    }
});

export const { clearError } = outreachSlice.actions;
export default outreachSlice.reducer;
