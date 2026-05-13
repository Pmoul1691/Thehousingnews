import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const TOKEN_KEY = "ultradian_session_token";

export const setSessionToken = (token) => {
  if (token) {
    try { localStorage.setItem(TOKEN_KEY, token); } catch (_e) {}
  }
};

export const getSessionToken = () => {
  try { return localStorage.getItem(TOKEN_KEY); } catch (_e) { return null; }
};

export const clearSessionToken = () => {
  try { localStorage.removeItem(TOKEN_KEY); } catch (_e) {}
};

const api = axios.create({
  baseURL: API,
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  const token = getSessionToken();
  if (token) {
    config.headers = config.headers || {};
    if (!config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

export default api;
