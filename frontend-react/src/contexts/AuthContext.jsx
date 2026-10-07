import { createContext, useContext, useState, useEffect } from "react";
import { fetchSession } from "../api";

const AuthContext = createContext(null);

function normalizeSession(data) {
  if (!data?.authenticated) return { authenticated: false };
  const roles = [];
  if (data.patient) roles.push("patient");
  if (data.doctor) roles.push("doctor");
  return { ...data, account: { ...data.account, roles } };
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshSession = async () => {
    try {
      const data = await fetchSession();
      setSession(normalizeSession(data));
    } catch (e) {
      setSession({ authenticated: false });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshSession();
  }, []);

  return (
    <AuthContext.Provider value={{ session, refreshSession, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
