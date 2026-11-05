# シエルの体（マイクラの Java 版に入るボット。会話モデルは使わない）。docs/minecraft-design-ja.md
FROM node:22.23.3-bookworm-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY src/ ./src/

USER node
CMD ["node", "src/main.js"]
