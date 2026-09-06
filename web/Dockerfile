FROM node:20-alpine AS build

WORKDIR /app

COPY web/package*.json /app/
ARG NPM_REGISTRY=https://registry.npmjs.org/
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm ci --no-audit --no-fund

COPY web /app

ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}

# web-session 引导密钥（构建期嵌入，生产由 CI secret 注入）
ARG VITE_BOOTSTRAP_SECRET=
ENV VITE_BOOTSTRAP_SECRET=${VITE_BOOTSTRAP_SECRET}

# 前端配置与 feature flag（R5.4）。VITE_* 只有构建期注入这一条路：运行时改 nginx 环境变量
# 不会改变已编译进 bundle 的取值，所以**每一个** VITE_ 开关都必须在这里有对应 ARG，
# 否则它在线上等于写死的默认值 —— 有读者但没人拧得动，比没有开关更糟。
# 本文件与 flagsGuard.test.js 的最后一道断言逐条对齐；新增 flag 时两侧同改。
# 留空/写 false 是有意默认：数据权利入口须等后端镜像确认含 data_rights_routes 后再开。
ARG VITE_DATA_RIGHTS_UI=false
ENV VITE_DATA_RIGHTS_UI=${VITE_DATA_RIGHTS_UI}
ARG VITE_SUPPORT_EMAIL=
ENV VITE_SUPPORT_EMAIL=${VITE_SUPPORT_EMAIL}
# 法人主体信息：留空时法务文本渲染成「正在办理登记」，绝不编造登记号（见 lib/brand.js）。
ARG VITE_LEGAL_ENTITY_NAME=
ENV VITE_LEGAL_ENTITY_NAME=${VITE_LEGAL_ENTITY_NAME}
ARG VITE_LEGAL_ABN=
ENV VITE_LEGAL_ABN=${VITE_LEGAL_ABN}
ARG VITE_LEGAL_JURISDICTION=
ENV VITE_LEGAL_JURISDICTION=${VITE_LEGAL_JURISDICTION}
# 分析采集（R5.1）。默认关闭：关闭态 lib/analytics.js 零副作用，不加载任何第三方代码。
# 启用前必须先改 /legal/dpa 第 4 条与 /legal/cookies 第 7 条 —— 那两条现在写的是「未启用」。
ARG VITE_ANALYTICS_ENABLED=false
ENV VITE_ANALYTICS_ENABLED=${VITE_ANALYTICS_ENABLED}
ARG VITE_ANALYTICS_SDK_URL=
ENV VITE_ANALYTICS_SDK_URL=${VITE_ANALYTICS_SDK_URL}
ARG VITE_ANALYTICS_TOKEN=
ENV VITE_ANALYTICS_TOKEN=${VITE_ANALYTICS_TOKEN}
# 注意：上面这个只能是**客户端 public key**（分析 SDK 的设计前提），它会出现在浏览器
# 打包产物里。任何服务端密钥/写权限 token 都不得走这条路径 —— ARG 值还会留在镜像历史里。
ARG VITE_ANALYTICS_HOST=
ENV VITE_ANALYTICS_HOST=${VITE_ANALYTICS_HOST}
# 会话回放：遮蔽两个开关必须同时为 true，否则 analytics.js 拒绝录制（Spec §159）。
ARG VITE_ANALYTICS_SESSION_REPLAY=false
ENV VITE_ANALYTICS_SESSION_REPLAY=${VITE_ANALYTICS_SESSION_REPLAY}
ARG VITE_ANALYTICS_MASK_ALL_TEXT=false
ENV VITE_ANALYTICS_MASK_ALL_TEXT=${VITE_ANALYTICS_MASK_ALL_TEXT}
ARG VITE_ANALYTICS_MASK_ALL_INPUTS=false
ENV VITE_ANALYTICS_MASK_ALL_INPUTS=${VITE_ANALYTICS_MASK_ALL_INPUTS}
# R3 四项新界面（URL 状态镜像 / SPA 导航 / ⌘K 面板 / 移动抽屉）。默认全 false = 与 R3 之前
# 逐字一致；判据见 web/src/lib/flags.js，门见 flagsGuard.test.js。
ARG VITE_URL_STATE_UI=false
ENV VITE_URL_STATE_UI=${VITE_URL_STATE_UI}
ARG VITE_SPA_NAV_UI=false
ENV VITE_SPA_NAV_UI=${VITE_SPA_NAV_UI}
ARG VITE_COMMAND_PALETTE_UI=false
ENV VITE_COMMAND_PALETTE_UI=${VITE_COMMAND_PALETTE_UI}
ARG VITE_MOBILE_NAV_UI=false
ENV VITE_MOBILE_NAV_UI=${VITE_MOBILE_NAV_UI}

RUN npm run build

FROM nginx:1.27-alpine

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
