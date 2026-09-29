import { MonitorSmartphone } from 'lucide-react';

/**
 * Aviso de tela cheia para telas estreitas (celular). Puramente por breakpoint
 * CSS (`md:hidden`, visível só abaixo de 768px), sem detecção de user-agent:
 * um tablet ou celular em modo paisagem que caiba na largura passa direto.
 *
 * O FinanceFlow processa planilhas e documentos e apresenta tabelas de
 * conferência densas, o que é inviável de operar com conforto numa tela de
 * celular. Em vez de uma UI mobile degradada, orienta o usuário a trocar de
 * dispositivo.
 */
export default function MobileWarning() {
  return (
    <div className="md:hidden fixed inset-0 z-[100] flex flex-col items-center justify-center gap-4 bg-brand-950 px-8 text-center select-none">
      <MonitorSmartphone className="h-12 w-12 text-brand-300" />
      <h1 className="text-lg font-semibold text-white">Acesso disponível apenas em computador</h1>
      <p className="max-w-xs text-sm leading-relaxed text-white/70">
        Para garantir a melhor experiência no processamento e na análise de documentos, o
        FinanceFlow deve ser acessado a partir de um computador desktop ou notebook.
      </p>
    </div>
  );
}
