FROM node:22-alpine AS build
WORKDIR /workspace/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
COPY contratos_api_oto/ /workspace/contratos_api_oto/
RUN npm run build
FROM nginx:1.28-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist /usr/share/nginx/html
EXPOSE 80
