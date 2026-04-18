'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

export default function AuthPage() {
  const { signIn, signUp, user } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (user) {
    router.replace('/');
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    setLoading(true);
    if (tab === 'signin') {
      const { error } = await signIn(email, password);
      if (error) { setError(error); setLoading(false); return; }
      router.push('/');
    } else {
      const { error } = await signUp(email, password);
      if (error) { setError(error); setLoading(false); return; }
      setMessage('Check your email to confirm your account, then sign in.');
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-slate-900">Real Estate Signal Engine</h1>
          <p className="text-slate-500 text-sm mt-1">Sign in to save searches and manage property lists</p>
        </div>

        <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 space-y-5">
          {/* Tab switcher */}
          <div className="flex rounded-lg border border-gray-700 overflow-hidden text-sm">
            <button
              type="button"
              onClick={() => { setTab('signin'); setError(null); setMessage(null); }}
              className={`flex-1 py-2 font-medium transition-colors ${tab === 'signin' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => { setTab('signup'); setError(null); setMessage(null); }}
              className={`flex-1 py-2 font-medium transition-colors ${tab === 'signup' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              Create Account
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="w-full bg-gray-900/50 border border-gray-700 text-white placeholder-gray-600 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="you@example.com"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 uppercase tracking-wide mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete={tab === 'signin' ? 'current-password' : 'new-password'}
                className="w-full bg-gray-900/50 border border-gray-700 text-white placeholder-gray-600 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"
                placeholder="••••••••"
              />
            </div>

            {error && <p className="text-red-400 text-sm">{error}</p>}
            {message && <p className="text-green-400 text-sm">{message}</p>}

            <button
              type="submit"
              disabled={loading}
              className={`w-full py-2.5 rounded-lg font-semibold text-white text-sm transition-all flex items-center justify-center gap-2 ${
                loading ? 'bg-blue-700/70 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500 active:scale-[0.99]'
              }`}
            >
              {loading && <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
              {tab === 'signin' ? 'Sign In' : 'Create Account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
