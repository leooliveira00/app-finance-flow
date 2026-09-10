import { useState } from 'react';

/**
 * Célula de CPF com máscara e "clicar para revelar".
 *
 * Todos os níveis (operador incluído) têm direito ao CPF — o mascaramento aqui é
 * proteção de TELA (evita exposição a quem olha por cima do ombro, prints, etc.),
 * não de autorização. Por isso é tratamento de frontend: o dado chega inteiro da
 * API e só a exibição fica oculta até o clique.
 */
function soDigitos(cpf: string): string {
  return (cpf || '').replace(/\D/g, '');
}

function mascarar(cpf: string): string {
  const d = soDigitos(cpf);
  if (d.length !== 11) return cpf || '';
  return `${d.slice(0, 3)}.***.***-${d.slice(9)}`;
}

function formatar(cpf: string): string {
  const d = soDigitos(cpf);
  if (d.length !== 11) return cpf || '';
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

interface Props {
  cpf: string;
  /** Classes extras (ex.: cor do texto conforme o contexto da tabela). */
  className?: string;
}

export default function CpfCell({ cpf, className = 'text-slate-500' }: Props) {
  const [revelado, setRevelado] = useState(false);
  if (!cpf) return <span className={`font-mono ${className}`}>—</span>;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        setRevelado((v) => !v);
      }}
      title={revelado ? 'Ocultar CPF' : 'Clique para revelar o CPF'}
      className={`font-mono cursor-pointer hover:text-slate-700 transition-colors ${className}`}
    >
      {revelado ? formatar(cpf) : mascarar(cpf)}
    </button>
  );
}
