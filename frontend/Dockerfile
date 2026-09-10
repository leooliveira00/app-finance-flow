# syntax=docker/dockerfile:1.7
#
# Frontend do FinanceFlow: build do app Vite servido por nginx
# (node 20-alpine, nginx 1.27-alpine).

# --- Estágio 1: build dos estáticos ---
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
# `npm ci` e NÃO `npm install`: instala exatamente o que está no lockfile e
# falha se ele estiver ausente ou dessincronizado. Sem fallback
# (`|| npm install`), que reintroduziria build não reproduzível e resolveria
# versões novas sem revisão.
RUN npm ci

COPY . .
RUN npm run build

# --- Estágio 2: runtime (nginx) ---
FROM nginx:1.27-alpine AS runtime

# Configuração de SPA (fallback para index.html) + proxy /api/ -> backend.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
