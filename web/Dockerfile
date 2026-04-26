FROM node:20-alpine AS build

WORKDIR /app

COPY web/package*.json /app/
ARG NPM_REGISTRY=https://registry.npmjs.org/
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm ci --no-audit --no-fund

COPY web /app

ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}

RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
