import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  timeout: 20000,
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const message =
      error?.response?.data?.detail ||
      error?.message ||
      "Unable to reach the simulator API";
    return Promise.reject(new Error(message));
  }
);

export default api;
