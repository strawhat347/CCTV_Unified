import { useState } from 'react';
import { login, registerUser } from '../services/api';
import { ShieldCheck, Lock, User, CheckCircle } from 'lucide-react';

export default function Login({ onLoginSuccess }) {
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('operator');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);
    setLoading(true);
    
    try {
      if (isLogin) {
        await login(username, password);
        onLoginSuccess();
      } else {
        await registerUser(username, password, role);
        setSuccessMsg("Account created! You can now sign in.");
        setIsLogin(true);
        setPassword('');
      }
    } catch (err) {
      setError(err.message || (isLogin ? "Failed to log in" : "Failed to register"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 bg-white text-black">
      <div className="sm:mx-auto sm:w-full sm:max-w-md flex flex-col items-center">
        <div className="p-4 mb-4">
          <ShieldCheck size={48} className="text-black" />
        </div>
        <h2 className="text-center text-3xl font-extrabold text-black">
          CCTV Unified Security
        </h2>
        <p className="mt-2 text-center text-sm text-gray-600">
          Enterprise Access Portal
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 sm:rounded-xl sm:px-10 border border-gray-300 shadow-sm relative overflow-hidden">
          
          <div className="flex mb-6 border-b border-gray-200">
            <button
              type="button"
              className={`flex-1 pb-3 text-sm font-medium ${isLogin ? 'border-b-2 border-black text-black' : 'text-gray-500 hover:text-black'}`}
              onClick={() => { setIsLogin(true); setError(null); setSuccessMsg(null); }}
            >
              Sign In
            </button>
            <button
              type="button"
              className={`flex-1 pb-3 text-sm font-medium ${!isLogin ? 'border-b-2 border-black text-black' : 'text-gray-500 hover:text-black'}`}
              onClick={() => { setIsLogin(false); setError(null); setSuccessMsg(null); }}
            >
              Sign Up
            </button>
          </div>

          <form className="space-y-6 relative z-10" onSubmit={handleSubmit}>
            {error && (
              <div className="bg-red-50 border border-red-500 text-red-700 px-4 py-3 rounded-lg flex items-center gap-2" role="alert">
                <span className="block sm:inline text-sm">{error}</span>
              </div>
            )}
            {successMsg && (
              <div className="bg-green-50 border border-green-500 text-green-700 px-4 py-3 rounded-lg flex items-center gap-2" role="alert">
                <CheckCircle size={16} />
                <span className="block sm:inline text-sm">{successMsg}</span>
              </div>
            )}
            
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-black">
                Username
              </label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <User size={16} className="text-gray-500" />
                </div>
                <input
                  id="username"
                  name="username"
                  type="text"
                  required
                  minLength={3}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="appearance-none block w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg shadow-sm bg-white text-black placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-black focus:border-black transition-all sm:text-sm"
                  placeholder="Enter your operator ID"
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-black">
                Password
              </label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock size={16} className="text-gray-500" />
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="appearance-none block w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg shadow-sm bg-white text-black placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-black focus:border-black transition-all sm:text-sm"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {!isLogin && (
              <div>
                <label htmlFor="role" className="block text-sm font-medium text-black">
                  Request Role
                </label>
                <div className="mt-1">
                  <select
                    id="role"
                    name="role"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="block w-full pl-3 pr-10 py-2.5 text-black bg-white border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-black focus:border-black sm:text-sm"
                  >
                    <option value="operator">Operator (Standard Access)</option>
                    <option value="admin">Admin (Full Access)</option>
                    <option value="auditor">Auditor (Read Only)</option>
                  </select>
                </div>
              </div>
            )}

            <div>
              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-black hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-black transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-4"
              >
                {loading ? (isLogin ? 'Authenticating...' : 'Registering...') : (isLogin ? 'Sign In' : 'Sign Up')}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
