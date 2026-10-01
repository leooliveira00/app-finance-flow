// Setup do Vitest: matchers do jest-dom (toBeInTheDocument, toHaveTextContent…)
// e desmontagem do que cada teste renderizou. Os testes importam `describe`/`it`/
// `expect` de 'vitest' explicitamente (sem globals), então o cleanup automático
// da Testing Library não se registra sozinho: fica aqui.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});
