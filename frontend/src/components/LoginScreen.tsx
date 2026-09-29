import React, { useState } from 'react';
import { KeyRound, User, ArrowRight } from 'lucide-react';
import * as api from '../api';
import { Usuario } from '../api';
import { Toast } from '../types';
import logoSymbol from '../img/logo-financeflow.png';

interface LoginScreenProps {
  onLogin: (usuario: Usuario) => void;
  addToast: (message: string, type: Toast['type']) => void;
}

export default function LoginScreen({ onLogin, addToast }: LoginScreenProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email || !password) {
      setError('Informe e-mail e senha.');
      return;
    }
    setIsLoading(true);
    try {
      const usuario = await api.login(email.trim(), password);
      onLogin(usuario);
    } catch (err) {
      const msg = err instanceof api.ApiError ? err.message : 'Falha ao conectar ao servidor.';
      setError(msg);
      addToast(msg, 'error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 sm:px-6 lg:px-8 bg-brand-950 relative overflow-hidden select-none">
      {/* Mesmo fundo do menu, com dois halos discretos para o azul não ficar chapado. */}
      <div className="absolute top-0 left-0 w-96 h-96 bg-brand-900 rounded-full filter blur-3xl opacity-60 -translate-x-1/3 -translate-y-1/3" />
      <div className="absolute bottom-0 right-0 w-96 h-96 bg-brand-900 rounded-full filter blur-3xl opacity-50 translate-x-1/3 translate-y-1/3" />

      <div className="sm:mx-auto sm:w-full sm:max-w-md z-10 flex flex-col items-center gap-4">
        <img
          src={logoSymbol}
          alt="FinanceFlow"
          className="h-20 w-auto object-contain drop-shadow-lg"
        />
        <span aria-hidden="true" className="h-px w-20 bg-white/25" />
        {/* Mesmo tratamento do menu. */}
        <span className="text-xl font-medium tracking-[0.3em] pl-[0.3em] text-white">
          FinanceFlow
        </span>
        <p className="text-center text-sm text-white/60">
          Lançamento automatizado de faturas e cobranças no ERP
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md z-10 animate-fade-in">
        <div className="bg-white py-8 px-4 shadow-2xl shadow-brand-950/40 rounded-2xl sm:px-10">
          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <div className="p-3 bg-rose-50 border border-rose-100 rounded-lg text-xs text-rose-700 font-medium animate-fade-in">
                {error}
              </div>
            )}

            <div>
              <label
                htmlFor="email"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
              >
                E-mail
              </label>
              <div className="mt-1.5 relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <User className="h-4 w-4" />
                </div>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder="seu.email@financeflow.local"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-sm transition-all"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-semibold uppercase tracking-wider text-slate-600"
              >
                Senha de acesso
              </label>
              <div className="mt-1.5 relative rounded-xl shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <KeyRound className="h-4 w-4" />
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-sm transition-all"
                />
              </div>
            </div>

            <div>
              <button
                id="btn-login"
                type="submit"
                disabled={isLoading}
                className="w-full flex justify-center items-center gap-2 py-3 px-4 border border-transparent rounded-xl shadow-md text-sm font-semibold text-white bg-brand-900 hover:bg-brand-950 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-500 transition-all cursor-pointer disabled:opacity-75 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <div className="h-5 w-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    Login
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
