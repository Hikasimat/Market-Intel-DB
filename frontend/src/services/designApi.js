import api from './api';

const base = { email: '/auth/email-templates/', signature: '/auth/email-signatures/' };
const unwrap = (res) => res.data.results || res.data || [];

export const designApi = {
  list: async (kind, search = '') =>
    unwrap(await api.get(base[kind], { params: search ? { search } : {} })),
  get: async (kind, id) => (await api.get(`${base[kind]}${id}/`)).data,
  create: async (kind, payload) => (await api.post(base[kind], payload)).data,
  update: async (kind, id, payload) => (await api.patch(`${base[kind]}${id}/`, payload)).data,
  remove: async (kind, id) => api.delete(`${base[kind]}${id}/`),
  duplicate: async (kind, id) => (await api.post(`${base[kind]}${id}/duplicate/`)).data,
  setDefault: async (kind, id) => (await api.post(`${base[kind]}${id}/set-default/`)).data,
};

export const composePreview = async (payload) =>
  (await api.post('/outreach/emails/compose-preview/', payload)).data;

export const errorMessage = (err) => {
  const d = err?.response?.data;
  if (!d) return err?.message || 'Request failed';
  if (typeof d === 'string') return d;
  if (d.error || d.detail) return d.error || d.detail;
  return Object.entries(d).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : v}`).join(' | ');
};
