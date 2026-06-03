# Commit And Push

## Repositorio

- Remoto: `https://github.com/guilhermebarbosa3-tech/localizador-uc.git`
- Branch de deploy do Streamlit Cloud: `main`
- A branch `master` nao e a branch publicada no app online.

## Regra principal

- Se a mudanca precisa aparecer no app online, ela precisa chegar em `origin/main`.
- Nao confiar em `master` para deploy.
- Nao usar `git push --force`.

## Estado historico importante

- `main` recebeu o merge do trabalho de sincronizacao via PR.
- Correcoes posteriores podem existir em `master` localmente, entao sempre confirme o destino antes de enviar.
- O worktree usado para preparar pushes seguros para `main` fica em:
  `C:\Users\WIN7\OneDrive\Área de Trabalho\les\meu_app_localizador_sync_main`

## Fluxo recomendado

1. Atualizar refs:
   `git fetch origin --prune`
2. Confirmar branch publicada:
   `git branch -a -vv`
3. Se a alteracao precisa ir para producao, trabalhar sobre a arvore baseada em `origin/main`.
4. Validar o arquivo principal:
   `python -m py_compile app.py`
5. Adicionar apenas os arquivos desejados:
   `git add app.py requirements.txt COMMIT_PUSH.md`
6. Criar commit:
   `git commit -m "mensagem objetiva"`
7. Enviar para a branch correta:
   `git push origin HEAD:main`

## Comandos de verificacao

- Ver estado local:
  `git status --short`
- Ver branch atual:
  `git branch --show-current`
- Ver ultimo commit remoto de deploy:
  `git log --oneline --decorate --max-count=5 origin/main`
- Confirmar se um trecho esta em `main`:
  `git show origin/main:app.py`

## O que nao enviar

- `.venv`
- `__pycache__`
- videos
- `.bat`
- `.ps1`
- `.csv` locais temporarios
- planilhas locais
- arquivos de workspace

## Resumo rapido

- Deploy online: `main`
- Nao publicar alteracoes do app apenas em `master`
- Push correto para producao:
  `git push origin HEAD:main`
