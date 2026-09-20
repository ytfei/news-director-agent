# syntax=docker/dockerfile:1.7
#
# 主理人 Agent · Web 镜像（静态 SPA + 反向代理 /api）
#
# 前端所有请求走**相对路径** `/api/v1/...`，所以生产环境有两个选择：
#   1) 用这个镜像：nginx 把 /api 反代到后端（默认，开箱即用，无 CORS）
#   2) 把 dist/ 丢到 CDN，由网关反代 /api
#
# 构建期不注入任何 API 地址 —— 这是刻意的：地址一变就要重新构建镜像，
# 是 12-factor 里最常见的部署事故来源。

ARG NODE_VERSION=22

# ---------------------------------------------------------------- deps
FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------- build
FROM deps AS build
WORKDIR /app
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
# npm run build = tsc --noEmit && vite build，类型错误会让镜像构建失败
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM nginx:1.27-alpine AS runtime

# 上游地址默认值：compose 里的服务名叫 api。
# 运行期可用 -e API_UPSTREAM=host:port 覆盖（nginx 官方镜像的 envsubst 模板机制）。
# NGINX_RESOLVER 默认是 Docker 用户自定义网络的嵌入式 DNS；裸机 / k8s 部署需覆盖。
ENV API_UPSTREAM=api:8000 \
    NGINX_RESOLVER="127.0.0.11 valid=10s ipv6=off"

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
