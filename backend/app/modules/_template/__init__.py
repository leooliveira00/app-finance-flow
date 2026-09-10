"""
Template para criação de um novo módulo de rateio.

COMO USAR:
1. Copie esta pasta `_template/` para um novo nome SEM underscore inicial,
   descrevendo o rateio. Ex.: `app/modules/plano_saude/`.
   (Pastas começando com `_` são ignoradas pelo registry — por isso o
   template nunca é carregado como módulo ativo.)
2. Em `module.py`, defina a classe herdando de `RateioModule`, preencha
   `tipo` e `descricao`, e implemente `validar_inputs` e `processar`.
3. Em `parser.py`, implemente a leitura dos arquivos de entrada.
4. Em `calculator.py`, implemente a lógica de cálculo do rateio.
5. Pronto: o registry descobre e expõe o novo rateio automaticamente,
   sem nenhuma outra alteração na plataforma.

Este pacote serve apenas como guia e não deve ser registrado.
"""
